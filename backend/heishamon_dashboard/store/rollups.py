"""Minute/hour rollup maths over one SQLite connection, plus the materialise step of the flush.

`DataView` is the shared read model. The writer uses one over its own connection with no RAM state
(everything is already in the DB inside the flush transaction). A read builds one over the reader
connection with a frozen copy of the RAM buffer slice and the outage list (see `queries.py`).
"""
import sqlite3
from typing import Iterable

from ..coverage import HOUR_MS, MINUTE_MS, Row, aggregate_rows, bucket_rows, covered_segments

# (rowid | None, start, end | None, kind, topic) as copied from the in-memory `Outage` records
OutageRec = tuple[int | None, int, int | None, str, str | None]


def floor(ts: int, size: int) -> int:
    return ts - ts % size


class DataView:
    def __init__(
        self,
        conn: sqlite3.Connection,
        tid: dict[str, int],
        tkey: dict[int, str],
        text: dict[str, bool],
        retention_ms: int | None,
        *,
        topic_buf: dict[str, list] | None = None,
        first_mem: dict[str, int] | None = None,
        outages: Iterable[OutageRec] = (),
        extra_offline: int | None = None,
    ) -> None:
        self.conn = conn
        self.tid = tid
        self.tkey = tkey
        self.text = text
        self.retention_ms = retention_ms
        self.topic_buf = topic_buf or {}  # key -> Samples with ts <= the query end, oldest first
        self.first_mem = first_mem or {}  # key -> ts of the oldest buffered sample (unclipped)
        self.outages = list(outages)
        self.extra_offline = extra_offline  # synthetic open offline outage from liveness

    # ---------------------------------------------------------------- topics

    def is_text(self, key: str) -> bool:
        known = self.text.get(key)
        if known is not None:
            return known
        tid = self.tid.get(key)
        found = False
        if tid is not None:
            found = self.conn.execute(
                "SELECT 1 FROM samples WHERE topic_id = ? AND txt IS NOT NULL LIMIT 1", (tid,)
            ).fetchone() is not None
        self.text[key] = found
        return found

    # --------------------------------------------------------------- outages

    def all_outages(self, a: int, b: int) -> list[tuple[int, int | None, str, str | None]]:
        """All outages overlapping [a, b), DB rows overlaid with the in-memory records."""
        rows: dict[int, tuple] = {}
        for rowid, s, e, kind, tid in self.conn.execute(
            "SELECT rowid, start_ts, end_ts, kind, topic_id FROM outages "
            "WHERE start_ts < ? AND (end_ts IS NULL OR end_ts > ?)", (b, a)
        ):
            rows[rowid] = (s, e, kind, self.tkey.get(tid) if tid is not None else None)
        extra = []
        for rowid, start, end, kind, topic in self.outages:
            if rowid is not None:
                rows.pop(rowid, None)
            if start < b and (end is None or end > a):
                extra.append((start, end, kind, topic))
        return list(rows.values()) + extra

    def spans(self, key: str, a: int, b: int, use_mem: bool = True) -> list[tuple[int, int | None, str]]:
        tid = self.tid.get(key)
        if use_mem:
            raw = self.all_outages(a, b)
            if self.extra_offline is not None:
                raw.append((self.extra_offline, None, "offline", None))
            return [(s, e, k) for s, e, k, t in raw if t is None or t == key]
        out = []
        for s, e, kind, t in self.conn.execute(
            "SELECT start_ts, end_ts, kind, topic_id FROM outages "
            "WHERE start_ts < ? AND (end_ts IS NULL OR end_ts > ?)", (b, a)
        ):
            if t is None or t == tid:
                out.append((s, e, kind))
        return out

    # --------------------------------------------------------------- rollups

    def first_ts(self, key: str, use_mem: bool) -> int | None:
        cands = []
        tid = self.tid.get(key)
        if tid is not None:
            row = self.conn.execute("SELECT MIN(ts) FROM samples WHERE topic_id = ?", (tid,)).fetchone()
            if row[0] is not None:
                cands.append(row[0])
            row = self.conn.execute(
                "SELECT MIN(start_ts) FROM outages WHERE topic_id = ?", (tid,)).fetchone()
            if row[0] is not None:
                cands.append(row[0])
        if use_mem:
            first = self.first_mem.get(key)
            if first is not None:
                cands.append(first)
            cands += [start for _, start, _, _, topic in self.outages if topic == key]
        return min(cands) if cands else None

    def mu(self, key: str) -> int | None:
        tid = self.tid.get(key)
        if tid is None:
            return None
        row = self.conn.execute(
            "SELECT materialized_until FROM rollup_state WHERE topic_id = ?", (tid,)).fetchone()
        return row[0] if row else None

    def recompute_start(self, key: str, now: int, use_mem: bool) -> int | None:
        mu = self.mu(key)
        if mu is None:
            first = self.first_ts(key, use_mem)
            if first is None:
                return None
            start = floor(first, MINUTE_MS)
        else:
            start = floor(mu, MINUTE_MS)
        if self.retention_ms is not None:  # rollups before the raw cutoff are never recomputed
            start = max(start, floor(now - self.retention_ms, MINUTE_MS))
        return start

    def samples(self, key: str, a: int, b: int, use_mem: bool = True, inclusive: bool = False,
                limit: int | None = None) -> list[tuple]:
        """(ts, valid, value) for samples in [a, b) (or [a, b]), preceded by the carry-in sample.
        With `limit`, at most that many in-range rows are read (the newest, selected in SQL); when
        that trims anything the carry-in is dropped too, because it no longer precedes the rows."""
        tid = self.tid.get(key)
        found: dict[int, tuple] = {}
        carry = None
        if tid is not None:
            row = self.conn.execute(
                "SELECT ts, valid, num, txt FROM samples WHERE topic_id = ? AND ts < ? ORDER BY ts DESC LIMIT 1",
                (tid, a)).fetchone()
            if row:
                carry = (row[0], bool(row[1]), row[3] if row[3] is not None else row[2])
            op = "<=" if inclusive else "<"
            order, cap = ("ts DESC LIMIT ?", (limit,)) if limit is not None else ("ts", ())
            for ts, valid, num, txt in self.conn.execute(
                f"SELECT ts, valid, num, txt FROM samples WHERE topic_id = ? AND ts >= ? AND ts {op} ? "
                f"ORDER BY {order}", (tid, a, b) + cap):
                found[ts] = (ts, bool(valid), txt if txt is not None else num)
        if use_mem:
            for s in self.topic_buf.get(key, ()):
                val = (s.ts, s.valid, s.txt if s.txt is not None else s.num)
                if s.ts < a:
                    if carry is None or s.ts > carry[0]:
                        carry = val
                elif s.ts < b or (inclusive and s.ts == b):
                    found[s.ts] = val
        out = [found[t] for t in sorted(found)]
        if limit is not None and len(out) > limit:
            return out[-limit:]
        return ([carry] if carry else []) + out

    def compute_minutes(self, key: str, a: int, b: int, use_mem: bool) -> list[Row]:
        samples = self.samples(key, a, b, use_mem)
        outs = [(s, e) for s, e, _ in self.spans(key, a, b, use_mem)]
        return bucket_rows(covered_segments(samples, outs, a, b), a, b)

    def write_rows(self, table: str, tid: int, rows: list[Row]) -> None:
        self.conn.executemany(
            f"INSERT OR REPLACE INTO {table} (topic_id, bucket, first_ts, last_ts, covered_seconds, avg, min, max, last) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(tid, *r) for r in rows],
        )

    def db_rows(self, table: str, tid: int, b0: int, b1: int) -> list[Row]:
        return [
            tuple(r) for r in self.conn.execute(
                f"SELECT bucket, first_ts, last_ts, covered_seconds, avg, min, max, last FROM {table} "
                "WHERE topic_id = ? AND bucket >= ? AND bucket < ? ORDER BY bucket", (tid, b0, b1))
        ]

    # ------------------------------------------------------------ read paths

    def minute_rows(self, key: str, from_ms: int, to_ms: int, now: int) -> list[Row]:
        a = floor(from_ms, MINUTE_MS)
        start_re = self.recompute_start(key, now, use_mem=True)
        if start_re is None or a >= to_ms:
            return []
        rows: list[Row] = []
        tid = self.tid.get(key)
        if a < start_re and tid is not None:
            lim = min(start_re // MINUTE_MS, (to_ms + MINUTE_MS - 1) // MINUTE_MS)
            rows += self.db_rows("rollup_1m", tid, a // MINUTE_MS, lim)
        ca = max(a, start_re)
        if ca < to_ms:
            rows += self.compute_minutes(key, ca, to_ms, use_mem=True)
        return rows

    def hour_rows(self, key: str, from_ms: int, to_ms: int, now: int) -> list[Row]:
        a = floor(from_ms, HOUR_MS)
        start_re = self.recompute_start(key, now, use_mem=True)
        if start_re is None or a >= to_ms:
            return []
        sh = floor(start_re, HOUR_MS)
        rows: list[Row] = []
        tid = self.tid.get(key)
        if a < sh and tid is not None:
            lim = min(sh // HOUR_MS, (to_ms + HOUR_MS - 1) // HOUR_MS)
            rows += self.db_rows("rollup_1h", tid, a // HOUR_MS, lim)
        ca = max(a, sh)
        if ca < to_ms:
            rows += aggregate_rows(self.minute_rows(key, ca, to_ms, now), 60)
        return rows

    def raw_count(self, key: str, a: int, b: int) -> int:
        n = 1
        tid = self.tid.get(key)
        if tid is not None:
            n += self.conn.execute(
                "SELECT COUNT(*) FROM samples WHERE topic_id = ? AND ts >= ? AND ts <= ?", (tid, a, b)).fetchone()[0]
        return n + sum(1 for s in self.topic_buf.get(key, ()) if a <= s.ts <= b)


def materialize(view: DataView, key: str, now: int, horizon: int | None) -> None:
    """Recompute every bucket from the previous horizon to `now` inside the flush transaction
    (everything is already in the DB at this point; `view` is the writer's)."""
    start = view.recompute_start(key, now, use_mem=False)
    if start is None:
        return
    tid = view.tid[key]
    prev = view.mu(key)
    if start < now:
        rows = view.compute_minutes(key, start, now, use_mem=False)
        view.write_rows("rollup_1m", tid, rows)
        h0 = floor(start, HOUR_MS) // MINUTE_MS
        h1 = ((now - 1) // HOUR_MS + 1) * 60
        mrows = [
            (b, f, l, cs, avg, mn, mx, last) for b, f, l, cs, avg, mn, mx, last in view.conn.execute(
                "SELECT bucket, first_ts, last_ts, covered_seconds, avg, min, max, last FROM rollup_1m "
                "WHERE topic_id = ? AND bucket >= ? AND bucket < ? ORDER BY bucket", (tid, h0, h1))
        ]
        view.write_rows("rollup_1h", tid, aggregate_rows(mrows, 60))
    if horizon is None:
        new_mu = prev
    else:
        new_mu = horizon if prev is None else max(prev, horizon)
    if new_mu is not None:
        view.conn.execute(
            "INSERT OR REPLACE INTO rollup_state (topic_id, materialized_until) VALUES (?, ?)", (tid, new_mu))
