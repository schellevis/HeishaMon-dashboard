"""RAM-buffered SQLite store (spec §5).

Everything is buffered in RAM and written in one transaction per flush. Coverage, outages,
rollups and the protected-record budget follow §5.1-§5.4. Timestamps are unix ms UTC.
"""
import functools
import json
import os
import re
import sqlite3
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any, NamedTuple

from . import db
from .coverage import (
    HOUR_MS, MINUTE_MS, Row, aggregate_rows, bucket_rows, covered_segments, raw_intervals,
)
from .types import Liveness, Receipt

OUTAGE_KINDS = ("offline", "restart", "dropped", "ignored")
RESERVED_SLOTS = 66  # 64 terminal command updates + 2 saturation records (spec §5.1)
DETAIL_MAX_BYTES = 2048
BREAK_MIN_MS = 10 * 60 * 1000
RAW_MAX_SPAN_MS = 6 * 3600 * 1000
MINUTE_MAX_SPAN_MS = 14 * 86400 * 1000
_COMMAND_COLS = (
    "submitted_ts", "published_ts", "name", "payload", "retained", "class", "prev_value",
    "status", "confirmed_ts", "attempts", "detail", "keys",
)


class StorageUnavailable(RuntimeError):
    """The protected-record budget is saturated; new commands are refused (503 storage_unavailable)."""


class _Sample(NamedTuple):
    key: str
    ts: int
    valid: bool
    num: float | None
    txt: str | None
    size: int


@dataclass
class Outage:
    start: int
    end: int | None
    kind: str
    topic: str | None
    rowid: int | None = None  # None = not yet persisted
    dirty: bool = False
    saturation: bool = False


@dataclass
class FlushResult:
    ok: bool
    flush_ts: int
    samples: int = 0
    horizon: int | None = None
    error: str | None = None


def _locked(fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return fn(self, *args, **kwargs)
    return wrapper


def _trunc(text: str | None) -> str | None:
    if text is None:
        return None
    raw = text.encode("utf-8")
    if len(raw) <= DETAIL_MAX_BYTES:
        return text
    return raw[:DETAIL_MAX_BYTES].decode("utf-8", errors="ignore")


def _detail_json(detail: Any) -> str:
    text = json.dumps(detail if detail is not None else {}, separators=(",", ":"))
    if len(text.encode("utf-8")) <= DETAIL_MAX_BYTES:
        return text
    return json.dumps({"truncated": True, "text": _trunc(text)[: DETAIL_MAX_BYTES - 64]})


def _floor(ts: int, size: int) -> int:
    return ts - ts % size


class Store:
    def __init__(
        self,
        db_path: str,
        *,
        buffer_max_entries: int = 200_000,
        buffer_max_bytes: int = 268_435_456,
        audit_buffer_max: int = 10_000,
        raw_retention_days: int | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._path = db_path
        self._conn = db.connect(db_path)
        self._max_entries = buffer_max_entries
        self._max_bytes = buffer_max_bytes
        self._audit_max = audit_buffer_max
        self._retention_ms = None if raw_retention_days is None else raw_retention_days * 86_400_000
        # sample buffer
        self._buf: deque[_Sample] = deque()
        self._topic_buf: dict[str, deque[_Sample]] = {}
        self._bytes = 0
        self._last_ts: dict[str, int] = {}
        self._text: dict[str, bool] = {}
        self._needs_flush = False
        self._failing = False
        self._last_error: str | None = None
        self._last_flush_ts: int | None = None
        # protected records
        self._cmds_new: dict[str, dict] = {}
        self._cmd_upd: dict[str, dict] = {}
        self._events: list[dict] = []
        self._agg: dict[str, dict] = {}
        self._events_dropped: dict | None = None
        self._outages: list[Outage] = []
        self._drops: dict[str, Outage] = {}
        self._scoped_open: set[str] = set()
        self._sat = False
        self._sat_outage: Outage | None = None
        self._extra: Outage | None = None
        self._tid: dict[str, int] = {}
        self._tkey: dict[int, str] = {}
        self._load_topics()
        self._ignored_on = {
            k for k, v in (self.prefs_get().get("topic_visibility") or {}).items() if v == "ignored"
        }
        for rowid, start, end, kind, tid in self._conn.execute(
            "SELECT rowid, start_ts, end_ts, kind, topic_id FROM outages WHERE end_ts IS NULL"
        ):
            self._outages.append(Outage(start, None, kind, self._tkey.get(tid), rowid=rowid))
        self._reindex()

    @classmethod
    def from_config(cls, cfg, filename: str = "heishamon.db") -> "Store":
        os.makedirs(cfg.data_dir, exist_ok=True)
        return cls(
            os.path.join(cfg.data_dir, filename),
            buffer_max_entries=cfg.buffer_max_entries,
            buffer_max_bytes=cfg.buffer_max_bytes,
            audit_buffer_max=cfg.audit_buffer_max,
            raw_retention_days=cfg.raw_retention_days,
        )

    @_locked
    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------ status

    @property
    def needs_flush(self) -> bool:
        return self._needs_flush

    @property
    def failing(self) -> bool:
        return self._failing

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def last_flush_ts(self) -> int | None:
        return self._last_flush_ts

    @property
    def sample_count(self) -> int:
        return len(self._buf)

    @property
    def sample_bytes(self) -> int:
        return self._bytes

    @property
    def saturated(self) -> bool:
        return self._sat

    @_locked
    def audit_count(self) -> int:
        return (
            len(self._cmds_new) + len(self._cmd_upd) + len(self._events)
            + sum(1 for o in self._outages if o.rowid is None)
        )

    def protected_budget_ok(self) -> bool:
        return not self._sat

    def db_bytes(self) -> int:
        try:
            return os.path.getsize(self._path)
        except OSError:
            return 0

    # --------------------------------------------------------------- topics

    def _load_topics(self) -> None:
        self._tid = {k: i for i, k in self._conn.execute("SELECT id, key FROM topics")}
        self._tkey = {i: k for k, i in self._tid.items()}

    def _is_text(self, key: str) -> bool:
        known = self._text.get(key)
        if known is not None:
            return known
        tid = self._tid.get(key)
        found = False
        if tid is not None:
            found = self._conn.execute(
                "SELECT 1 FROM samples WHERE topic_id = ? AND txt IS NOT NULL LIMIT 1", (tid,)
            ).fetchone() is not None
        self._text[key] = found
        return found

    # --------------------------------------------------------------- outages

    def _reindex(self) -> None:
        self._scoped_open = {
            o.topic for o in self._outages
            if o.end is None and o.topic is not None and o.kind in ("dropped", "ignored")
        }

    def _new_outage(self, kind: str, start: int, topic: str | None, reserved: bool = False) -> Outage | None:
        if self._sat and not reserved:
            return None
        o = Outage(start, None, kind, topic)
        self._outages.append(o)
        self._reindex()
        if not reserved:
            self._maybe_saturate(start)
        return o

    def _open_of(self, kind: str, topic: str | None) -> Outage | None:
        for o in self._outages:
            if o.end is None and o.kind == kind and o.topic == topic:
                return o
        return None

    @_locked
    def open_outage(self, kind: str, start: int, topic: str | None = None) -> Outage | None:
        """Open an outage unless one of the same kind and scope is already open. Returns None
        when saturation suppresses new outage records."""
        if kind not in OUTAGE_KINDS:
            raise ValueError(f"unknown outage kind {kind!r}")
        existing = self._open_of(kind, topic)
        if existing is not None:
            return existing
        return self._new_outage(kind, start, topic)

    @_locked
    def close_outage(self, kind: str, end: int, topic: str | None = None) -> bool:
        o = self._open_of(kind, topic)
        if o is None:
            return False
        self._close(o, end)
        return True

    def _close(self, o: Outage, end: int) -> None:
        o.end = max(end, o.start + 1)  # never closed at or before its own start
        o.dirty = True
        self._reindex()

    @_locked
    def set_ignored(self, topic: str, on: bool, ts: int) -> None:
        if on:
            self._ignored_on.add(topic)
            self.open_outage("ignored", ts, topic)
        else:
            # the outage stays open until the topic's next received value (dedup bypass)
            self._ignored_on.discard(topic)

    @_locked
    def outages_list(self, from_ts: int | None = None, to_ts: int | None = None) -> list[dict]:
        out = []
        for s, e, kind, topic in self._all_outages(0, 2**62):
            if (to_ts is not None and s >= to_ts) or (from_ts is not None and e is not None and e <= from_ts):
                continue
            out.append({"start_ts": s, "end_ts": e, "kind": kind, "topic": topic})
        return sorted(out, key=lambda r: (r["start_ts"], r["kind"], r["topic"] or ""))

    def _all_outages(self, a: int, b: int) -> list[tuple[int, int | None, str, str | None]]:
        """All outages overlapping [a, b), DB rows overlaid with the in-memory records."""
        rows: dict[int, tuple] = {}
        for rowid, s, e, kind, tid in self._conn.execute(
            "SELECT rowid, start_ts, end_ts, kind, topic_id FROM outages "
            "WHERE start_ts < ? AND (end_ts IS NULL OR end_ts > ?)", (b, a)
        ):
            rows[rowid] = (s, e, kind, self._tkey.get(tid) if tid is not None else None)
        extra = []
        for o in self._outages:
            if o.rowid is not None:
                rows.pop(o.rowid, None)
            if o.start < b and (o.end is None or o.end > a):
                extra.append((o.start, o.end, o.kind, o.topic))
        return list(rows.values()) + extra

    def _spans(self, key: str, a: int, b: int, use_mem: bool = True) -> list[tuple[int, int | None, str]]:
        tid = self._tid.get(key)
        if use_mem:
            raw = self._all_outages(a, b)
            if self._extra is not None:
                raw.append((self._extra.start, None, "offline", None))
            return [(s, e, k) for s, e, k, t in raw if t is None or t == key]
        out = []
        for s, e, kind, t in self._conn.execute(
            "SELECT start_ts, end_ts, kind, topic_id FROM outages "
            "WHERE start_ts < ? AND (end_ts IS NULL OR end_ts > ?)", (b, a)
        ):
            if t is None or t == tid:
                out.append((s, e, kind))
        return out

    @_locked
    def startup(self, now: int) -> None:
        """Open the `restart` outage from the previous run's last durable instant. Outages still
        open in the database stay open (they are closed together at the first live message)."""
        frontier = self.frontier()
        start = now if frontier is None else min(frontier["flush_ts"], now)
        if self._open_of("restart", None) is None:
            self._new_outage("restart", start, None)
        self.append_event(now, "restart", {"previous_flush_ts": None if frontier is None else frontier["flush_ts"]})

    # ---------------------------------------------------------------- budget

    def _maybe_saturate(self, ts: int) -> None:
        if self._sat or self.audit_count() < self._audit_max - RESERVED_SLOTS:
            return
        self._sat = True
        self._sat_outage = self._new_outage("dropped", ts, None, reserved=True)
        self._sat_outage.saturation = True

    # ---------------------------------------------------------------- events

    def _note_dropped_event(self, ts: int, kind: str) -> None:
        ev = self._events_dropped
        if ev is None:
            ev = {"ts": ts, "kind": "events_dropped", "detail": {"count": 0, "kinds": {}}}
            self._events_dropped = ev
            self._events.append(ev)  # reserved slot
        ev["detail"]["count"] += 1
        ev["detail"]["kinds"][kind] = ev["detail"]["kinds"].get(kind, 0) + 1

    @_locked
    def append_event(self, ts: int, kind: str, detail: dict | None = None) -> bool:
        if self._sat:
            self._note_dropped_event(ts, kind)
            return False
        self._events.append({"ts": ts, "kind": kind, "detail": detail if detail is not None else {}})
        self._maybe_saturate(ts)
        return True

    def _agg_event(self, kind: str, ts: int, make: dict, mutate) -> None:
        """One buffered event per kind and flush cycle, updated in place."""
        ev = self._agg.get(kind)
        if ev is not None:
            mutate(ev["detail"])
            return
        if self._sat:
            self._note_dropped_event(ts, kind)
            return
        ev = {"ts": ts, "kind": kind, "detail": make}
        self._events.append(ev)
        self._agg[kind] = ev
        self._maybe_saturate(ts)

    @_locked
    def events_list(self, from_ts: int | None = None, to_ts: int | None = None,
                    kinds: list[str] | None = None, limit: int = 1000) -> list[dict]:
        rows = [
            {"ts": ts, "kind": kind, "detail": json.loads(detail or "{}")}
            for ts, kind, detail in self._conn.execute("SELECT ts, kind, detail FROM events ORDER BY ts DESC LIMIT ?", (limit,))
        ]
        rows += [dict(e) for e in self._events]
        rows = [
            r for r in rows
            if (from_ts is None or r["ts"] >= from_ts) and (to_ts is None or r["ts"] < to_ts)
            and (kinds is None or r["kind"] in kinds)
        ]
        rows.sort(key=lambda r: r["ts"], reverse=True)
        return rows[:limit]

    # -------------------------------------------------------------- commands

    @_locked
    def append_command(self, record: dict) -> None:
        if self._sat:
            raise StorageUnavailable("protected-record budget is full")
        rec = dict(record)
        rec["detail"] = _trunc(rec.get("detail"))
        self._cmds_new[rec["uuid"]] = rec
        self._maybe_saturate(rec.get("submitted_ts") or 0)

    @_locked
    def update_command(self, uuid: str, fields: dict) -> None:
        fields = dict(fields)
        if "detail" in fields:
            fields["detail"] = _trunc(fields["detail"])
        if uuid in self._cmds_new:
            self._cmds_new[uuid].update(fields)
        elif uuid in self._cmd_upd:
            self._cmd_upd[uuid].update(fields)
        else:
            self._cmd_upd[uuid] = fields  # uses a reserved slot at the boundary

    @staticmethod
    def _command_from_row(row: sqlite3.Row | tuple) -> dict:
        d = dict(zip(("uuid",) + _COMMAND_COLS, row))
        d["retained"] = bool(d["retained"])
        d["keys"] = json.loads(d["keys"]) if d["keys"] else None
        return d

    def _command_select(self) -> str:
        return "SELECT uuid, " + ", ".join(f'"{c}"' for c in _COMMAND_COLS) + " FROM commands"

    @_locked
    def get_command(self, uuid: str) -> dict | None:
        row = self._conn.execute(self._command_select() + " WHERE uuid = ?", (uuid,)).fetchone()
        rec = self._command_from_row(row) if row else None
        if uuid in self._cmds_new:
            return dict(self._cmds_new[uuid])
        if rec is not None and uuid in self._cmd_upd:
            rec.update(self._cmd_upd[uuid])
        return rec

    @_locked
    def list_commands(self, limit: int = 200) -> list[dict]:
        recs = {
            r["uuid"]: r for r in (
                self._command_from_row(row) for row in self._conn.execute(
                    self._command_select() + " ORDER BY submitted_ts DESC LIMIT ?", (limit,))
            )
        }
        for uuid, upd in self._cmd_upd.items():
            if uuid in recs:
                recs[uuid].update(upd)
        for uuid, rec in self._cmds_new.items():
            recs[uuid] = dict(rec)
        out = sorted(recs.values(), key=lambda r: r.get("submitted_ts") or 0, reverse=True)
        return out[:limit]

    @_locked
    def last_confirmed_setcurves(self, zone: Any, mode: str) -> int | None:
        """`confirmed_ts` of the newest confirmed SetCurves record whose keys include the zone/mode."""
        digit = re.search(r"\d", str(zone))
        if not digit:
            raise ValueError(f"zone {zone!r} has no number")
        pattern = re.compile(rf"z{digit.group()}_{re.escape(mode.lower())}_")
        recs = {
            r["uuid"]: r for r in (
                self._command_from_row(row) for row in self._conn.execute(
                    self._command_select() + " WHERE name = 'SetCurves'")
            )
        }
        for uuid, upd in self._cmd_upd.items():
            if uuid in recs:
                recs[uuid].update(upd)
        for uuid, rec in self._cmds_new.items():
            if rec.get("name") == "SetCurves":
                recs[uuid] = dict(rec)
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

    # --------------------------------------------------------------- samples

    @_locked
    def observe(self, r: Receipt) -> None:
        if r.qualifying and not r.retained:
            for o in self._outages:
                if o.end is None and o.topic is None and o.kind in ("offline", "restart") and not o.saturation:
                    self._close(o, r.ts)
        key = r.topic
        if key in self._ignored_on:
            return
        pending = key in self._scoped_open
        if not r.changed and not pending:
            return
        self._add_sample(r)
        if pending:
            for o in self._outages:
                if o.end is None and o.topic == key and o.kind in ("dropped", "ignored"):
                    self._close(o, r.ts)

    def _add_sample(self, r: Receipt) -> None:
        key = r.topic
        is_text = isinstance(r.value, str)
        if r.value is not None:
            self._text[key] = is_text
        ts = r.ts
        last = self._last_ts.get(key)
        if last is None:
            tid = self._tid.get(key)
            last = -1
            if tid is not None:
                row = self._conn.execute("SELECT MAX(ts) FROM samples WHERE topic_id = ?", (tid,)).fetchone()
                last = row[0] if row and row[0] is not None else -1
        if ts <= last:
            ts = last + 1  # collision bump, order-preserving (spec §5.2)
        self._last_ts[key] = ts
        valid = bool(r.valid) and r.value is not None
        num = float(r.value) if valid and not is_text else None
        txt = r.value if valid and is_text else None
        size = 64 + len(key) + (len(txt) if txt else 0)
        s = _Sample(key, ts, valid, num, txt, size)
        self._buf.append(s)
        self._topic_buf.setdefault(key, deque()).append(s)
        self._bytes += size
        self._enforce_caps(r.ts)

    def _over(self, factor: int = 1) -> bool:
        return len(self._buf) > self._max_entries * factor or self._bytes > self._max_bytes * factor

    def _enforce_caps(self, ts: int) -> None:
        if len(self._buf) >= self._max_entries or self._bytes >= self._max_bytes:
            self._needs_flush = True
        while self._buf and self._over() and (self._failing or self._over(2)):
            self._drop_oldest(ts)

    def _drop_oldest(self, ts: int) -> None:
        s = self._buf.popleft()
        dq = self._topic_buf[s.key]
        dq.popleft()
        if not dq:
            del self._topic_buf[s.key]
        self._bytes -= s.size

        def mutate(d: dict) -> None:
            d["count"] += 1
            d["first_ts"] = min(d["first_ts"], s.ts)
            d["last_ts"] = max(d["last_ts"], s.ts)

        self._agg_event("buffer_overflow", ts, {"count": 1, "first_ts": s.ts, "last_ts": s.ts}, mutate)
        o = self._drops.get(s.key)
        if o is None:
            o = self._new_outage("dropped", s.ts, s.key)
            if o is None:
                # saturated: the global outage covers it; make sure it reaches back to this sample
                so = self._sat_outage
                if so is not None and s.ts < so.start:
                    so.start = s.ts
                    so.dirty = True
                return
            self._drops[s.key] = o
        kept = self._topic_buf.get(s.key)
        o.end = kept[0].ts if kept else None
        o.dirty = True
        self._reindex()

    # ----------------------------------------------------------------- prefs

    @_locked
    def prefs_get(self) -> dict:
        return {k: json.loads(v) for k, v in self._conn.execute("SELECT key, value FROM prefs")}

    @_locked
    def prefs_put(self, prefs: dict) -> None:
        """Written immediately in its own small transaction (spec §5.1)."""
        c = self._conn
        c.execute("BEGIN IMMEDIATE")
        try:
            for k, v in prefs.items():
                c.execute("INSERT OR REPLACE INTO prefs (key, value) VALUES (?, ?)", (k, json.dumps(v)))
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise

    # -------------------------------------------------------------- frontier

    @_locked
    def frontier(self) -> dict | None:
        row = self._conn.execute(
            "SELECT flush_ts, device_online, last_qualifying_ts FROM frontier WHERE id = 1"
        ).fetchone()
        if row is None:
            return None
        online = {1: "online", 0: "offline"}.get(row[1], "unknown")
        return {"flush_ts": row[0], "device_online": online, "last_qualifying_ts": row[2]}

    # ----------------------------------------------------------------- flush

    @_locked
    def flush(self, now: int, liveness: Liveness) -> FlushResult:
        was_sat = self._sat
        sat_outage = self._sat_outage
        prev_end = sat_outage.end if sat_outage else None
        try:
            result = self._flush_tx(now, liveness)
        except Exception as exc:  # disk full, I/O error, ...
            if self._conn.in_transaction:
                try:
                    self._conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
            if sat_outage is not None:
                sat_outage.end = prev_end
                sat_outage.dirty = prev_end is not None
            self._load_topics()
            self._failing = True
            self._last_error = f"{type(exc).__name__}: {exc}"
            err = self._last_error
            self._agg_event(
                "flush_failed", now, {"count": 1, "last_error": err, "last_ts": now},
                lambda d: d.update(count=d["count"] + 1, last_error=err, last_ts=now),
            )
            return FlushResult(False, now, error=err)
        self._after_commit(now, liveness, was_sat, result)
        return result

    def _horizon(self, now: int, liveness: Liveness) -> int | None:
        if liveness.device_online == "offline":
            return now
        h = liveness.last_qualifying_ts
        return None if h is None else min(h, now)

    def _flush_tx(self, now: int, liveness: Liveness) -> FlushResult:
        c = self._conn
        c.execute("BEGIN IMMEDIATE")
        # topics
        keys = {s.key for s in self._buf} | {o.topic for o in self._outages if o.topic}
        for k in sorted(keys):
            if k not in self._tid:
                c.execute("INSERT OR IGNORE INTO topics (key) VALUES (?)", (k,))
                tid = c.execute("SELECT id FROM topics WHERE key = ?", (k,)).fetchone()[0]
                self._tid[k] = tid
                self._tkey[tid] = k
        # samples
        c.executemany(
            "INSERT OR REPLACE INTO samples (topic_id, ts, num, txt, valid) VALUES (?, ?, ?, ?, ?)",
            [(self._tid[s.key], s.ts, s.num, s.txt, int(s.valid)) for s in self._buf],
        )
        # commands
        for rec in self._cmds_new.values():
            keys_json = rec.get("keys")
            if keys_json is not None and not isinstance(keys_json, str):
                keys_json = json.dumps(keys_json, separators=(",", ":"))
            c.execute(
                "INSERT OR REPLACE INTO commands (uuid, " + ", ".join(f'"{x}"' for x in _COMMAND_COLS)
                + ") VALUES (?" + ", ?" * len(_COMMAND_COLS) + ")",
                (rec["uuid"],) + tuple(
                    keys_json if col == "keys" else (int(rec[col]) if col == "retained" and rec.get(col) is not None else rec.get(col))
                    for col in _COMMAND_COLS
                ),
            )
        for uuid, upd in self._cmd_upd.items():
            cols = [col for col in upd if col in _COMMAND_COLS]
            if not cols:
                continue
            vals = []
            for col in cols:
                v = upd[col]
                if col == "keys" and v is not None and not isinstance(v, str):
                    v = json.dumps(v, separators=(",", ":"))
                if col == "retained" and v is not None:
                    v = int(v)
                vals.append(v)
            c.execute(
                "UPDATE commands SET " + ", ".join(f'"{col}" = ?' for col in cols) + " WHERE uuid = ?",
                (*vals, uuid),
            )
        # outages
        if self._sat_outage is not None and self._sat_outage.end is None:
            self._sat_outage.end = max(now, self._sat_outage.start + 1)
            self._sat_outage.dirty = True
        assigned: list[tuple[Outage, int]] = []
        for o in self._outages:
            tid = self._tid[o.topic] if o.topic else None
            if o.rowid is None:
                cur = c.execute(
                    "INSERT INTO outages (start_ts, end_ts, kind, topic_id) VALUES (?, ?, ?, ?)",
                    (o.start, o.end, o.kind, tid))
                assigned.append((o, cur.lastrowid))
            elif o.dirty:
                c.execute("UPDATE outages SET start_ts = ?, end_ts = ? WHERE rowid = ?", (o.start, o.end, o.rowid))
        # events
        c.executemany(
            "INSERT INTO events (ts, kind, detail) VALUES (?, ?, ?)",
            [(e["ts"], e["kind"], _detail_json(e["detail"])) for e in self._events]
            + [(now, "flush", _detail_json({"samples": len(self._buf)}))],
        )
        # rollups
        horizon = self._horizon(now, liveness)
        for key in list(self._tid):
            if self._is_text(key):
                continue
            self._materialize(key, now, horizon)
        c.execute(
            "INSERT OR REPLACE INTO frontier (id, flush_ts, device_online, last_qualifying_ts) VALUES (1, ?, ?, ?)",
            (now, {"online": 1, "offline": 0}.get(liveness.device_online), liveness.last_qualifying_ts),
        )
        self._purge(now)
        c.execute("COMMIT")
        for o, rowid in assigned:
            o.rowid = rowid
        return FlushResult(True, now, samples=len(self._buf), horizon=horizon)

    def _after_commit(self, now: int, liveness: Liveness, was_sat: bool, result: FlushResult) -> None:
        self._buf.clear()
        self._topic_buf.clear()
        self._bytes = 0
        self._cmds_new.clear()
        self._cmd_upd.clear()
        self._events.clear()
        self._agg.clear()
        self._events_dropped = None
        self._drops.clear()
        self._outages = [o for o in self._outages if o.end is None]
        for o in self._outages:
            o.dirty = False
        self._sat = False
        self._sat_outage = None
        self._needs_flush = False
        self._failing = False
        self._last_error = None
        self._last_flush_ts = now
        self._reindex()
        if was_sat and liveness.device_online == "offline" and self._open_of("offline", None) is None:
            self._new_outage("offline", now, None)

    # --------------------------------------------------------------- rollups

    def _first_ts(self, key: str, use_mem: bool) -> int | None:
        cands = []
        tid = self._tid.get(key)
        if tid is not None:
            row = self._conn.execute("SELECT MIN(ts) FROM samples WHERE topic_id = ?", (tid,)).fetchone()
            if row[0] is not None:
                cands.append(row[0])
            row = self._conn.execute(
                "SELECT MIN(start_ts) FROM outages WHERE topic_id = ?", (tid,)).fetchone()
            if row[0] is not None:
                cands.append(row[0])
        if use_mem:
            dq = self._topic_buf.get(key)
            if dq:
                cands.append(dq[0].ts)
            cands += [o.start for o in self._outages if o.topic == key]
        return min(cands) if cands else None

    def _mu(self, key: str) -> int | None:
        tid = self._tid.get(key)
        if tid is None:
            return None
        row = self._conn.execute(
            "SELECT materialized_until FROM rollup_state WHERE topic_id = ?", (tid,)).fetchone()
        return row[0] if row else None

    def _recompute_start(self, key: str, now: int, use_mem: bool) -> int | None:
        mu = self._mu(key)
        if mu is None:
            first = self._first_ts(key, use_mem)
            if first is None:
                return None
            start = _floor(first, MINUTE_MS)
        else:
            start = _floor(mu, MINUTE_MS)
        if self._retention_ms is not None:  # rollups before the raw cutoff are never recomputed
            start = max(start, _floor(now - self._retention_ms, MINUTE_MS))
        return start

    def _samples(self, key: str, a: int, b: int, use_mem: bool = True, inclusive: bool = False) -> list[tuple]:
        """(ts, valid, value) for samples in [a, b) (or [a, b]), preceded by the carry-in sample."""
        tid = self._tid.get(key)
        found: dict[int, tuple] = {}
        carry = None
        if tid is not None:
            row = self._conn.execute(
                "SELECT ts, valid, num, txt FROM samples WHERE topic_id = ? AND ts < ? ORDER BY ts DESC LIMIT 1",
                (tid, a)).fetchone()
            if row:
                carry = (row[0], bool(row[1]), row[3] if row[3] is not None else row[2])
            op = "<=" if inclusive else "<"
            for ts, valid, num, txt in self._conn.execute(
                f"SELECT ts, valid, num, txt FROM samples WHERE topic_id = ? AND ts >= ? AND ts {op} ? ORDER BY ts",
                (tid, a, b)):
                found[ts] = (ts, bool(valid), txt if txt is not None else num)
        if use_mem:
            for s in self._topic_buf.get(key, ()):
                val = (s.ts, s.valid, s.txt if s.txt is not None else s.num)
                if s.ts < a:
                    if carry is None or s.ts > carry[0]:
                        carry = val
                elif s.ts < b or (inclusive and s.ts == b):
                    found[s.ts] = val
        out = [found[t] for t in sorted(found)]
        return ([carry] if carry else []) + out

    def _compute_minutes(self, key: str, a: int, b: int, use_mem: bool) -> list[Row]:
        samples = self._samples(key, a, b, use_mem)
        outs = [(s, e) for s, e, _ in self._spans(key, a, b, use_mem)]
        return bucket_rows(covered_segments(samples, outs, a, b), a, b)

    def _write_rows(self, table: str, tid: int, rows: list[Row]) -> None:
        self._conn.executemany(
            f"INSERT OR REPLACE INTO {table} (topic_id, bucket, first_ts, last_ts, covered_seconds, avg, min, max, last) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(tid, *r) for r in rows],
        )

    def _materialize(self, key: str, now: int, horizon: int | None) -> None:
        """Recompute every bucket from the previous horizon to `now` inside the flush transaction
        (everything is already in the DB at this point)."""
        start = self._recompute_start(key, now, use_mem=False)
        if start is None:
            return
        tid = self._tid[key]
        prev = self._mu(key)
        if start < now:
            rows = self._compute_minutes(key, start, now, use_mem=False)
            self._write_rows("rollup_1m", tid, rows)
            h0 = _floor(start, HOUR_MS) // MINUTE_MS
            h1 = ((now - 1) // HOUR_MS + 1) * 60
            mrows = [
                (b, f, l, cs, avg, mn, mx, last) for b, f, l, cs, avg, mn, mx, last in self._conn.execute(
                    "SELECT bucket, first_ts, last_ts, covered_seconds, avg, min, max, last FROM rollup_1m "
                    "WHERE topic_id = ? AND bucket >= ? AND bucket < ? ORDER BY bucket", (tid, h0, h1))
            ]
            self._write_rows("rollup_1h", tid, aggregate_rows(mrows, 60))
        if horizon is None:
            new_mu = prev
        else:
            new_mu = horizon if prev is None else max(prev, horizon)
        if new_mu is not None:
            self._conn.execute(
                "INSERT OR REPLACE INTO rollup_state (topic_id, materialized_until) VALUES (?, ?)", (tid, new_mu))

    def _purge(self, now: int) -> None:
        if self._retention_ms is None:
            return
        cutoff = now - self._retention_ms
        for key, tid in self._tid.items():
            eff = cutoff
            if not self._is_text(key):
                mu = self._mu(key)
                eff = min(cutoff, _floor(mu, MINUTE_MS)) if mu is not None else -1
            if eff <= 0:
                continue
            # keep one anchor per topic: the newest sample before the cutoff
            self._conn.execute(
                "DELETE FROM samples WHERE topic_id = ? AND ts < ? AND ts < "
                "(SELECT MAX(ts) FROM samples WHERE topic_id = ? AND ts < ?)", (tid, eff, tid, eff))

    # ----------------------------------------------------------------- reads

    def _minute_rows(self, key: str, from_ms: int, to_ms: int, now: int) -> list[Row]:
        a = _floor(from_ms, MINUTE_MS)
        start_re = self._recompute_start(key, now, use_mem=True)
        if start_re is None or a >= to_ms:
            return []
        rows: list[Row] = []
        tid = self._tid.get(key)
        if a < start_re and tid is not None:
            lim = min(start_re // MINUTE_MS, (to_ms + MINUTE_MS - 1) // MINUTE_MS)
            rows += self._db_rows("rollup_1m", tid, a // MINUTE_MS, lim)
        ca = max(a, start_re)
        if ca < to_ms:
            rows += self._compute_minutes(key, ca, to_ms, use_mem=True)
        return rows

    def _db_rows(self, table: str, tid: int, b0: int, b1: int) -> list[Row]:
        return [
            tuple(r) for r in self._conn.execute(
                f"SELECT bucket, first_ts, last_ts, covered_seconds, avg, min, max, last FROM {table} "
                "WHERE topic_id = ? AND bucket >= ? AND bucket < ? ORDER BY bucket", (tid, b0, b1))
        ]

    def _hour_rows(self, key: str, from_ms: int, to_ms: int, now: int) -> list[Row]:
        a = _floor(from_ms, HOUR_MS)
        start_re = self._recompute_start(key, now, use_mem=True)
        if start_re is None or a >= to_ms:
            return []
        sh = _floor(start_re, HOUR_MS)
        rows: list[Row] = []
        tid = self._tid.get(key)
        if a < sh and tid is not None:
            lim = min(sh // HOUR_MS, (to_ms + HOUR_MS - 1) // HOUR_MS)
            rows += self._db_rows("rollup_1h", tid, a // HOUR_MS, lim)
        ca = max(a, sh)
        if ca < to_ms:
            rows += aggregate_rows(self._minute_rows(key, ca, to_ms, now), 60)
        return rows

    def _with_liveness(self, liveness: Liveness | None) -> None:
        self._extra = None
        if (
            liveness is not None and liveness.device_online == "offline"
            and liveness.offline_since is not None and self._open_of("offline", None) is None
        ):
            self._extra = Outage(liveness.offline_since, None, "offline", None)

    @_locked
    def rollups_1m(self, topics: list[str], from_ts: int, to_ts: int, now: int,
                   liveness: Liveness | None = None) -> dict[str, list[Row]]:
        """Full 1-minute aggregates (bucket, first_ts, last_ts, covered_seconds, avg, min, max, last)
        with the read-time recompute. The caller asks for `from - 10 min` itself for lookback."""
        self._with_liveness(liveness)
        try:
            end = min(to_ts, now)
            return {k: self._minute_rows(k, from_ts, end, now) for k in topics}
        finally:
            self._extra = None

    @_locked
    def history(self, topics: list[str], from_ts: int, to_ts: int, max_points: int, now: int,
                liveness: Liveness | None = None) -> dict:
        """Spec §4.4 `History` (minus the HTTP layer). Series kind is "number" for every numeric
        topic; the API layer may refine it to "enum" from the catalog."""
        self._with_liveness(liveness)
        try:
            end = min(to_ts, now)
            numeric = [k for k in topics if not self._is_text(k)]
            resolution = "raw"
            if numeric:
                span = to_ts - from_ts
                expired = self._retention_ms is not None and from_ts < now - self._retention_ms
                raw_ok = span <= RAW_MAX_SPAN_MS and not expired and all(
                    self._raw_count(k, from_ts, end) <= max_points for k in numeric)
                resolution = "raw" if raw_ok else ("1m" if span <= MINUTE_MAX_SPAN_MS else "1h")
            partial = False
            series: dict[str, dict] = {}
            for key in topics:
                text = self._is_text(key)
                if text or resolution == "raw":
                    s = self._raw_series(key, from_ts, end, text)
                else:
                    rows = (self._minute_rows if resolution == "1m" else self._hour_rows)(key, from_ts, end, now)
                    size = MINUTE_MS if resolution == "1m" else HOUR_MS
                    s = {
                        "kind": "number",
                        "points": [[r[0] * size, r[4], r[3]] for r in rows],
                        "coverage": None,
                    }
                if len(s["points"]) > max_points:
                    s["points"] = s["points"][-max_points:]
                    partial = True
                s["breaks"] = self._breaks(key, from_ts, to_ts, now)
                series[key] = s
            return {"resolution": resolution, "partial": partial, "series": series}
        finally:
            self._extra = None

    def _raw_count(self, key: str, a: int, b: int) -> int:
        n = 1
        tid = self._tid.get(key)
        if tid is not None:
            n += self._conn.execute(
                "SELECT COUNT(*) FROM samples WHERE topic_id = ? AND ts >= ? AND ts <= ?", (tid, a, b)).fetchone()[0]
        return n + sum(1 for s in self._topic_buf.get(key, ()) if a <= s.ts <= b)

    def _raw_series(self, key: str, a: int, b: int, text: bool) -> dict:
        samples = self._samples(key, a, b, use_mem=True, inclusive=True)
        outs = [(s, e) for s, e, _ in self._spans(key, a, b)]
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
        return {"kind": "text" if text else "number", "points": points, "coverage": raw_intervals(segs)}

    def _breaks(self, key: str, a: int, b: int, now: int) -> list[list[int]]:
        out = []
        for s, e, _ in self._spans(key, a, b):
            end = now if e is None else e
            if end - s > BREAK_MIN_MS:
                out.append([s, end])
        return sorted(out)
