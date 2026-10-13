"""The RAM sample buffer: dedupe-bumped samples, size caps, drop-oldest (spec §5.1)."""
from collections import deque
from typing import NamedTuple

from ..types import Receipt
from .sqlite import locked


class Sample(NamedTuple):
    key: str
    ts: int
    valid: bool
    num: float | None
    txt: str | None
    size: int


class BufferMixin:
    def _init_buffer(self, buffer_max_entries: int, buffer_max_bytes: int) -> None:
        self._max_entries = buffer_max_entries
        self._max_bytes = buffer_max_bytes
        self._buf: deque[Sample] = deque()
        self._topic_buf: dict[str, deque[Sample]] = {}
        self._bytes = 0
        self._last_ts: dict[str, int] = {}

    def _clear_buffer(self) -> None:
        self._buf.clear()
        self._topic_buf.clear()
        self._bytes = 0

    @property
    def sample_count(self) -> int:
        return len(self._buf)

    @property
    def sample_bytes(self) -> int:
        return self._bytes

    @locked
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
        s = Sample(key, ts, valid, num, txt, size)
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

    def _write_samples(self, c) -> None:
        c.executemany(
            "INSERT OR REPLACE INTO samples (topic_id, ts, num, txt, valid) VALUES (?, ?, ?, ?, ?)",
            [(self._tid[s.key], s.ts, s.num, s.txt, int(s.valid)) for s in self._buf],
        )
