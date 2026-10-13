"""Reads: history, rollups, raw series, breaks, events, commands (spec §4.4, §5).

Every read runs on the reader connection, never on the writer. It takes the store lock only long
enough to copy the RAM state it needs (the buffer slice up to the query end, the outage list, the
pending command/event records) and to pin a read snapshot of the database. The database scan then
runs without the lock, so a slow read never delays `observe()` or a flush. The snapshot is taken
under the same lock a flush holds for its whole transaction, so the RAM copy and the database
always describe the same instant.
"""
import copy
import json
import re
from contextlib import contextmanager
from typing import Any, Callable

from ..coverage import HOUR_MS, MINUTE_MS, Row, covered_segments, raw_intervals
from ..types import Liveness
from .records import command_from_row, command_select
from .rollups import DataView

BREAK_MIN_MS = 10 * 60 * 1000
RAW_MAX_SPAN_MS = 6 * 3600 * 1000
MINUTE_MAX_SPAN_MS = 14 * 86400 * 1000
TEXT_SCAN_FACTOR = 4  # text topics read at most max_points × this many rows


class QueryMixin:
    @contextmanager
    def _snapshot(self, keys=(), hi: int = 0, liveness: Liveness | None = None,
                  grab: Callable[[], Any] | None = None):
        """Yield (DataView, grab()) for one consistent read. `keys` are the topics whose buffered
        samples up to `hi` are copied."""
        with self._read_lock:
            rc = self._rconn
            with self._lock:
                topic_buf: dict[str, list] = {}
                first_mem: dict[str, int] = {}
                for k in keys:
                    dq = self._topic_buf.get(k)
                    if dq:
                        first_mem[k] = dq[0].ts
                        topic_buf[k] = [s for s in dq if s.ts <= hi]
                outages = [(o.rowid, o.start, o.end, o.kind, o.topic) for o in self._outages]
                extra = None
                if (
                    liveness is not None and liveness.device_online == "offline"
                    and liveness.offline_since is not None and self._open_of("offline", None) is None
                ):
                    extra = liveness.offline_since
                view = DataView(
                    rc, dict(self._tid), dict(self._tkey), dict(self._text), self._retention_ms,
                    topic_buf=topic_buf, first_mem=first_mem, outages=outages, extra_offline=extra)
                ram = grab() if grab is not None else None
                rc.execute("BEGIN")
                try:
                    rc.execute("SELECT version FROM schema_version").fetchall()  # pins the snapshot
                except BaseException:
                    rc.execute("ROLLBACK")
                    raise
            try:
                yield view, ram
            finally:
                rc.execute("ROLLBACK")

    # --------------------------------------------------------------- rollups

    def rollups_1m(self, topics: list[str], from_ts: int, to_ts: int, now: int,
                   liveness: Liveness | None = None) -> dict[str, list[Row]]:
        """Full 1-minute aggregates (bucket, first_ts, last_ts, covered_seconds, avg, min, max, last)
        with the read-time recompute. The caller asks for `from - 10 min` itself for lookback."""
        with self._snapshot(topics, to_ts, liveness) as (view, _):
            end = min(to_ts, now)
            return {k: view.minute_rows(k, from_ts, end, now) for k in topics}

    def history(self, topics: list[str], from_ts: int, to_ts: int, max_points: int, now: int,
                liveness: Liveness | None = None) -> dict:
        """Spec §4.4 `History` (minus the HTTP layer). Series kind is "number" for every numeric
        topic; the API layer may refine it to "enum" from the catalog."""
        with self._snapshot(topics, to_ts, liveness) as (view, _):
            end = min(to_ts, now)
            numeric = [k for k in topics if not view.is_text(k)]
            resolution = "raw"
            if numeric:
                span = to_ts - from_ts
                expired = self._retention_ms is not None and from_ts < now - self._retention_ms
                raw_ok = span <= RAW_MAX_SPAN_MS and not expired and all(
                    view.raw_count(k, from_ts, end) <= max_points for k in numeric)
                resolution = "raw" if raw_ok else ("1m" if span <= MINUTE_MAX_SPAN_MS else "1h")
            partial = False
            series: dict[str, dict] = {}
            for key in topics:
                text = view.is_text(key)
                if text or resolution == "raw":
                    s = _raw_series(view, key, from_ts, end, text,
                                    max_points * TEXT_SCAN_FACTOR if text else None)
                else:
                    rows = (view.minute_rows if resolution == "1m" else view.hour_rows)(key, from_ts, end, now)
                    size = MINUTE_MS if resolution == "1m" else HOUR_MS
                    s = {
                        "kind": "number",
                        "points": [[r[0] * size, r[4], r[3]] for r in rows],
                        "coverage": None,
                    }
                if len(s["points"]) > max_points:
                    s["points"] = s["points"][-max_points:]
                    s["truncated"] = True
                if s.get("truncated"):
                    partial = True
                s["breaks"] = _breaks(view, key, from_ts, to_ts, now)
                series[key] = s
            return {"resolution": resolution, "partial": partial, "series": series}

    def rollups_1h(self, topics: list[str], from_ts: int, to_ts: int, now: int,
                   liveness: Liveness | None = None) -> dict[str, list[Row]]:
        """Every 1-hour aggregate in range, unthinned (energy sums all buckets)."""
        with self._snapshot(topics, to_ts, liveness) as (view, _):
            end = min(to_ts, now)
            return {k: view.hour_rows(k, from_ts, end, now) for k in topics}

    # ---------------------------------------------------------------- outages

    def outages_list(self, from_ts: int | None = None, to_ts: int | None = None) -> list[dict]:
        with self._snapshot() as (view, _):
            out = []
            for s, e, kind, topic in view.all_outages(0, 2**62):
                if (to_ts is not None and s >= to_ts) or (from_ts is not None and e is not None and e <= from_ts):
                    continue
                out.append({"start_ts": s, "end_ts": e, "kind": kind, "topic": topic})
            return sorted(out, key=lambda r: (r["start_ts"], r["kind"], r["topic"] or ""))

    # ----------------------------------------------------------------- events

    def events_list(self, from_ts: int | None = None, to_ts: int | None = None,
                    kinds: list[str] | None = None, limit: int = 1000) -> list[dict]:
        def grab():
            return [copy.deepcopy(e) for e in self._events]

        with self._snapshot(grab=grab) as (view, ram):
            rows = [
                {"ts": ts, "kind": kind, "detail": json.loads(detail or "{}")}
                for ts, kind, detail in view.conn.execute(
                    "SELECT ts, kind, detail FROM events ORDER BY ts DESC LIMIT ?", (limit,))
            ]
        rows += ram
        rows = [
            r for r in rows
            if (from_ts is None or r["ts"] >= from_ts) and (to_ts is None or r["ts"] < to_ts)
            and (kinds is None or r["kind"] in kinds)
        ]
        rows.sort(key=lambda r: r["ts"], reverse=True)
        return rows[:limit]

    # --------------------------------------------------------------- commands

    def get_command(self, uuid: str) -> dict | None:
        def grab():
            return copy.deepcopy(self._cmds_new.get(uuid)), copy.deepcopy(self._cmd_upd.get(uuid))

        with self._snapshot(grab=grab) as (view, (new, upd)):
            row = view.conn.execute(command_select() + " WHERE uuid = ?", (uuid,)).fetchone()
        rec = command_from_row(row) if row else None
        if new is not None:
            return new
        if rec is not None and upd is not None:
            rec.update(upd)
        return rec

    def list_commands(self, limit: int = 200) -> list[dict]:
        def grab():
            return copy.deepcopy(self._cmds_new), copy.deepcopy(self._cmd_upd)

        with self._snapshot(grab=grab) as (view, (new, upd)):
            recs = {
                r["uuid"]: r for r in (
                    command_from_row(row) for row in view.conn.execute(
                        command_select() + " ORDER BY submitted_ts DESC LIMIT ?", (limit,))
                )
            }
        for uuid, u in upd.items():
            if uuid in recs:
                recs[uuid].update(u)
        recs.update(new)
        out = sorted(recs.values(), key=lambda r: r.get("submitted_ts") or 0, reverse=True)
        return out[:limit]

    def last_confirmed_setcurves(self, zone: Any, mode: str) -> int | None:
        """`confirmed_ts` of the newest confirmed SetCurves record whose keys include the zone/mode."""
        digit = re.search(r"\d", str(zone))
        if not digit:
            raise ValueError(f"zone {zone!r} has no number")
        pattern = re.compile(rf"z{digit.group()}_{re.escape(mode.lower())}_")

        def grab():
            new = {u: copy.deepcopy(r) for u, r in self._cmds_new.items() if r.get("name") == "SetCurves"}
            return new, copy.deepcopy(self._cmd_upd)

        with self._snapshot(grab=grab) as (view, (new, upd)):
            recs = {
                r["uuid"]: r for r in (
                    command_from_row(row) for row in view.conn.execute(
                        command_select() + " WHERE name = 'SetCurves'")
                )
            }
        for uuid, u in upd.items():
            if uuid in recs:
                recs[uuid].update(u)
        recs.update(new)
        best = None
        for r in recs.values():
            if r.get("confirmed_ts") is None:
                continue
            keys = r.get("keys")
            if isinstance(keys, str):
                keys = json.loads(keys)
            if not keys or not any(pattern.search(str(k).lower()) for k in keys):
                continue
            best = r["confirmed_ts"] if best is None else max(best, r["confirmed_ts"])
        return best


def _raw_series(view: DataView, key: str, a: int, b: int, text: bool, cap: int | None = None) -> dict:
    truncated = False
    samples = view.samples(key, a, b, use_mem=True, inclusive=True,
                           limit=None if cap is None else cap + 1)
    if cap is not None:
        inside = [s for s in samples if s[0] >= a]
        if len(inside) > cap:  # scan capped: keep the newest rows, coverage starts at the first
            truncated = True
            samples = inside[-cap:]
            a = samples[0][0]
    outs = [(s, e) for s, e, _ in view.spans(key, a, b)]
    segs = covered_segments(samples, outs, a, b) if b > a else []
    points = []
    has_at_start = any(s[0] == a for s in samples)
    for ts, valid, val in samples:
        if not valid:
            continue
        if ts < a:
            if not has_at_start:
                points.append([a, val])
        else:
            points.append([ts, val])
    out = {"kind": "text" if text else "number", "points": points, "coverage": raw_intervals(segs)}
    if truncated:
        out["truncated"] = True
    return out


def _breaks(view: DataView, key: str, a: int, b: int, now: int) -> list[list[int]]:
    out = []
    for s, e, _ in view.spans(key, a, b):
        end = now if e is None else e
        if end - s > BREAK_MIN_MS:
            out.append([s, end])
    return sorted(out)
