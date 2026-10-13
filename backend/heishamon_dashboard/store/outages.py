"""Outages: open/close, reserved slots, saturation outage and their flush rows (spec §5.1, §5.3)."""
from dataclasses import dataclass

from .sqlite import locked

OUTAGE_KINDS = ("offline", "restart", "dropped", "ignored")


@dataclass
class Outage:
    start: int
    end: int | None
    kind: str
    topic: str | None
    rowid: int | None = None  # None = not yet persisted
    dirty: bool = False
    saturation: bool = False


class OutageMixin:
    def _init_outages(self) -> None:
        self._outages: list[Outage] = []
        self._drops: dict[str, Outage] = {}
        self._scoped_open: set[str] = set()
        self._ignored_on: set[str] = set()
        self._sat_outage: Outage | None = None

    def _load_open_outages(self) -> None:
        for rowid, start, end, kind, tid in self._conn.execute(
            "SELECT rowid, start_ts, end_ts, kind, topic_id FROM outages WHERE end_ts IS NULL"
        ):
            self._outages.append(Outage(start, None, kind, self._tkey.get(tid), rowid=rowid))
        self._reindex()

    def _clear_outages(self) -> None:
        self._drops.clear()
        self._outages = [o for o in self._outages if o.end is None]
        for o in self._outages:
            o.dirty = False
        self._reindex()

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

    @locked
    def open_outage(self, kind: str, start: int, topic: str | None = None) -> Outage | None:
        """Open an outage unless one of the same kind and scope is already open. Returns None
        when saturation suppresses new outage records."""
        if kind not in OUTAGE_KINDS:
            raise ValueError(f"unknown outage kind {kind!r}")
        existing = self._open_of(kind, topic)
        if existing is not None:
            return existing
        return self._new_outage(kind, start, topic)

    @locked
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

    @locked
    def set_ignored(self, topic: str, on: bool, ts: int) -> None:
        if on:
            self._ignored_on.add(topic)
            self.open_outage("ignored", ts, topic)
        else:
            # the outage stays open until the topic's next received value (dedup bypass)
            self._ignored_on.discard(topic)

    @locked
    def startup(self, now: int) -> None:
        """Open the `restart` outage from the previous run's last durable instant. Outages still
        open in the database stay open (they are closed together at the first live message)."""
        frontier = self.frontier()
        start = now if frontier is None else min(frontier["flush_ts"], now)
        if self._open_of("restart", None) is None:
            self._new_outage("restart", start, None)
        self.append_event(now, "restart", {"previous_flush_ts": None if frontier is None else frontier["flush_ts"]})

    def _write_outages(self, c, now: int) -> list[tuple[Outage, int]]:
        """Inside the flush transaction. Returns the new rowids, applied after COMMIT."""
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
        return assigned
