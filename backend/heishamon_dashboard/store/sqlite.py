"""SQLite plumbing: the two connections, topic ids, the single flush transaction and purge."""
import functools
import os
import sqlite3
import threading
from dataclasses import dataclass

from .. import db
from ..coverage import MINUTE_MS
from ..types import Liveness
from .rollups import DataView, floor, materialize


def locked(fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return fn(self, *args, **kwargs)
    return wrapper


@dataclass
class FlushResult:
    ok: bool
    flush_ts: int
    samples: int = 0
    horizon: int | None = None
    error: str | None = None


class SqliteMixin:
    def _init_sqlite(self, db_path: str, raw_retention_days: int | None) -> None:
        self._lock = threading.RLock()  # guards all RAM state and the writer connection
        self._read_lock = threading.RLock()  # serialises readers on their one connection
        self._path = db_path
        self._conn = db.connect(db_path)  # the one writer
        self._rconn = db.connect_reader(db_path)  # `query_only`, used by every history read
        self._retention_ms = None if raw_retention_days is None else raw_retention_days * 86_400_000
        self._needs_flush = False
        self._failing = False
        self._last_error: str | None = None
        self._last_flush_ts: int | None = None
        self._tid: dict[str, int] = {}
        self._tkey: dict[int, str] = {}
        self._text: dict[str, bool] = {}
        self._load_topics()
        # the writer's own view of the rollup maths: shares the topic maps, never sees RAM state
        self._wview = DataView(self._conn, self._tid, self._tkey, self._text, self._retention_ms)

    def close(self) -> None:
        with self._read_lock, self._lock:
            self._rconn.close()
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

    def db_bytes(self) -> int:
        try:
            return os.path.getsize(self._path)
        except OSError:
            return 0

    # --------------------------------------------------------------- topics

    def _load_topics(self) -> None:
        # in place: the writer view and the read snapshots hold references to these dicts
        tid = {k: i for i, k in self._conn.execute("SELECT id, key FROM topics")}
        self._tid.clear()
        self._tid.update(tid)
        self._tkey.clear()
        self._tkey.update({i: k for k, i in tid.items()})

    def _is_text(self, key: str) -> bool:
        return self._wview.is_text(key)

    # -------------------------------------------------------------- frontier

    @locked
    def frontier(self) -> dict | None:
        row = self._conn.execute(
            "SELECT flush_ts, device_online, last_qualifying_ts FROM frontier WHERE id = 1"
        ).fetchone()
        if row is None:
            return None
        online = {1: "online", 0: "offline"}.get(row[1], "unknown")
        return {"flush_ts": row[0], "device_online": online, "last_qualifying_ts": row[2]}

    # ----------------------------------------------------------------- flush

    @locked
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
        self._write_samples(c)
        self._write_commands(c)
        assigned = self._write_outages(c, now)
        self._write_events(c, now)
        # rollups
        horizon = self._horizon(now, liveness)
        for key in list(self._tid):
            if self._is_text(key):
                continue
            materialize(self._wview, key, now, horizon)
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
        self._clear_buffer()
        self._clear_records()
        self._clear_outages()
        self._needs_flush = False
        self._failing = False
        self._last_error = None
        self._last_flush_ts = now
        if was_sat and liveness.device_online == "offline" and self._open_of("offline", None) is None:
            self._new_outage("offline", now, None)

    def _purge(self, now: int) -> None:
        if self._retention_ms is None:
            return
        cutoff = now - self._retention_ms
        for key, tid in self._tid.items():
            eff = cutoff
            if not self._is_text(key):
                mu = self._wview.mu(key)
                eff = min(cutoff, floor(mu, MINUTE_MS)) if mu is not None else -1
            if eff <= 0:
                continue
            # keep one anchor per topic: the newest sample before the cutoff
            self._conn.execute(
                "DELETE FROM samples WHERE topic_id = ? AND ts < ? AND ts < "
                "(SELECT MAX(ts) FROM samples WHERE topic_id = ? AND ts < ?)", (tid, eff, tid, eff))
