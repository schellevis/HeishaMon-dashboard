"""In-memory topic values and HeishaMon liveness (spec §4.1, §4.3, §9)."""
from collections.abc import Callable
from typing import Literal

from heishamon_dashboard.catalog import Catalog
from heishamon_dashboard.types import Liveness, Message, Receipt, TopicValue

TOPIC_MAX_BYTES = 256
PAYLOAD_MAX_BYTES = 64 * 1024
UNKNOWN_TOPIC_MAX = 2000
LIVENESS_FLOOR_MS = 30_000
PRESENCE_HOLD_MS = 360_000
PRESENCE_KEYS = ("extra", "optional", "1wire", "s0", "opentherm")

# Rule 5 prefixes. `s0/Watthour/` does not match `s0/WatthourTotal/` (rule 2).
_QUALIFYING_PREFIXES = (
    "main/",
    "extra/",
    "optional/",
    "1wire/",
    "s0/Watt/",
    "s0/Watthour/",
    "opentherm/write/",
)
_ALWAYS_ACCEPTED_PREFIXES = ("1wire/", "s0/", "opentherm/")
_ALWAYS_ACCEPTED_EXACT = frozenset({"stats", "LWT", "ip"})
_WRITABLE_EXACT = frozenset({"s0/WatthourTotal/1", "s0/WatthourTotal/2"})


def _median(values: list[int]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def _writable(topic: str) -> bool:
    return (
        topic.startswith("commands/")
        or topic in _WRITABLE_EXACT
        or topic.startswith("opentherm/read/")
    )


def _live_qualifying_topic(topic: str) -> bool:
    if topic == "stats":
        return True
    return any(topic.startswith(prefix) for prefix in _QUALIFYING_PREFIXES)


def _presence_key(topic: str) -> str | None:
    if topic.startswith("extra/"):
        return "extra"
    if topic.startswith("optional/"):
        return "optional"
    if topic.startswith("1wire/"):
        return "1wire"
    if topic.startswith("s0/"):
        return "s0"
    # opentherm/read/# is dashboard-writable and never counts as OpenTherm presence.
    # opentherm/write/# and the pre-3.5 opentherm/<name> namespace do.
    if topic.startswith("opentherm/read/") or topic == "opentherm/read":
        return None
    if topic.startswith("opentherm/"):
        return "opentherm"
    return None


def _parse_number(raw: str) -> int | float | None:
    text = raw.strip()
    if not text:
        return None
    try:
        if text.isdigit() or (text[0] == "-" and text[1:].isdigit()):
            return int(text)
        value = float(text)
    except (ValueError, IndexError):
        return None
    if value != value or value in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return value


def _is_sentinel(value: int | float, sentinels: list) -> bool:
    return any(value == sentinel for sentinel in sentinels)


class State:
    """Current values plus device-online status. The caller drives time via `tick`."""

    def __init__(self, catalog: Catalog):
        self._catalog = catalog
        self.values: dict[str, TopicValue] = {}
        self.device_online: Literal["unknown", "online", "offline"] = "unknown"
        self.last_qualifying_ts: int | None = None
        self.offline_since: int | None = None
        self.seq: int = 0
        self.ingest_dropped: int = 0
        self.heartbeat_intervals: list[int] = []
        self._last_online_ts: int | None = None
        self._last_live: dict[str, int] = {}
        self._presence_ts: dict[str, int | None] = {key: None for key in PRESENCE_KEYS}
        self._reconnect_ts: int | None = None
        self._uncatalogued: set[str] = set()
        self._now: int | None = None
        self._on_offline: list[Callable[[int], None]] = []
        self._on_online: list[Callable[[int], None]] = []

    def on_offline(self, callback: Callable[[int], None]) -> Callable[[int], None]:
        """Register `callback(start_ts)` for a transition into offline."""
        self._on_offline.append(callback)
        return callback

    def on_online(self, callback: Callable[[int], None]) -> Callable[[int], None]:
        """Register `callback(ts)` for a transition into online."""
        self._on_online.append(callback)
        return callback

    @property
    def liveness_timeout_ms(self) -> int:
        """`max(30 s, 3 × median of the last 10 LWT=Online intervals)`."""
        if not self.heartbeat_intervals:
            return LIVENESS_FLOOR_MS
        return max(LIVENESS_FLOOR_MS, int(3 * _median(self.heartbeat_intervals)))

    def liveness(self) -> Liveness:
        return Liveness(
            device_online=self.device_online,
            last_qualifying_ts=self.last_qualifying_ts,
            offline_since=self.offline_since if self.device_online == "offline" else None,
        )

    def broker_reconnect(self, now: int) -> None:
        """Broker session restarted. Device stays unknown until a qualifying message.

        Presence (spec §4.3) stays until `PRESENCE_HOLD_MS` passes with no further
        message in that subtree.
        """
        self._now = now
        self._reconnect_ts = now
        self.device_online = "unknown"
        self.offline_since = None

    def tick(self, now: int) -> None:
        """Apply the liveness timeout and presence hold against `now` (unix ms)."""
        self._now = now
        if (
            self.device_online == "online"
            and self.last_qualifying_ts is not None
            and now >= self.last_qualifying_ts + self.liveness_timeout_ms
        ):
            self._enter_offline(self.last_qualifying_ts)
        elif (
            self.device_online == "unknown"
            and self._reconnect_ts is not None
            and self.last_qualifying_ts is not None
            and now >= self._reconnect_ts + self.liveness_timeout_ms
        ):
            # no qualifying live message since the reconnect: same backdate as from online
            self._enter_offline(self.last_qualifying_ts)

    def presence(self) -> dict[str, bool]:
        """§4.3 presence. Keys: extra, optional, 1wire, s0, opentherm."""
        return {key: self._present(key) for key in PRESENCE_KEYS}

    def last_live_ts(self, prefix: str) -> int | None:
        """Latest timestamp of a non-retained message whose topic starts with `prefix`."""
        found: int | None = None
        for topic, ts in self._last_live.items():
            if topic.startswith(prefix) and (found is None or ts > found):
                found = ts
        return found

    def consume_ingest_dropped(self) -> int:
        """Return the per-flush drop count and reset it."""
        count = self.ingest_dropped
        self.ingest_dropped = 0
        return count

    def ingest(self, message: Message) -> Receipt | None:
        """Parse one message. Oversized topics/payloads are dropped and counted."""
        if (
            len(message.topic.encode("utf-8")) > TOPIC_MAX_BYTES
            or len(message.payload.encode("utf-8")) > PAYLOAD_MAX_BYTES
        ):
            self.ingest_dropped += 1
            return None

        meta = self._catalog.topic(message.topic)
        if meta is None and message.topic not in self.values and not self._always_accepted(message.topic):
            if len(self._uncatalogued) >= UNKNOWN_TOPIC_MAX:
                self.ingest_dropped += 1
                return None
            self._uncatalogued.add(message.topic)
        self._now = message.ts
        value, kind, valid = self._interpret(message.payload, meta)
        previous = self.values.get(message.topic)
        changed = previous is None or previous.raw != message.payload
        retained_only = message.retained if previous is None else (
            previous.retained_only and message.retained
        )
        last_change = message.ts if changed or previous is None else previous.last_change
        self.values[message.topic] = TopicValue(
            key=message.topic,
            value=value,
            raw=message.payload,
            kind=kind,
            valid=valid,
            last_change=last_change,
            last_seen=message.ts,
            retained_only=retained_only,
        )
        if not message.retained:
            current = self._last_live.get(message.topic)
            if current is None or message.ts >= current:
                self._last_live[message.topic] = message.ts

        key = _presence_key(message.topic)
        if key is not None:
            previous_ts = self._presence_ts[key]
            if previous_ts is None or message.ts >= previous_ts:
                self._presence_ts[key] = message.ts

        qualifying = self._apply_liveness(message)
        self.seq += 1
        return Receipt(
            topic=message.topic,
            raw=message.payload,
            value=value,
            valid=valid,
            retained=message.retained,
            ts=message.ts,
            qualifying=qualifying,
            changed=changed,
        )

    @staticmethod
    def _always_accepted(topic: str) -> bool:
        return topic in _ALWAYS_ACCEPTED_EXACT or topic.startswith(_ALWAYS_ACCEPTED_PREFIXES)

    def _interpret(self, raw: str, meta: dict | None) -> tuple[int | float | str | None, str, bool]:
        if meta is None:
            return raw, "text", True
        kind = meta["kind"]
        sentinels = meta.get("sentinels") or []
        if kind == "text":
            number = _parse_number(raw)
            if number is not None and _is_sentinel(number, sentinels):
                return number, "text", False
            return raw, "text", True
        number = _parse_number(raw)
        if number is None:
            return raw, kind, False
        if _is_sentinel(number, sentinels):
            return number, kind, False
        return number, kind, True

    def _apply_liveness(self, message: Message) -> bool:
        """§4.1 ordered rule list. Returns whether the message is qualifying."""
        if message.retained:
            return False
        if _writable(message.topic):
            return False
        if message.topic == "LWT":
            payload = message.payload.strip()
            if payload == "Offline":
                self._enter_offline(message.ts)
                return False
            if payload == "Online":
                self._note_heartbeat(message.ts)
                self._enter_online(message.ts)
                return True
            return False
        if _live_qualifying_topic(message.topic):
            self._enter_online(message.ts)
            return True
        return False

    def _note_heartbeat(self, ts: int) -> None:
        if self._last_online_ts is not None:
            interval = ts - self._last_online_ts
            if interval > 0:
                self.heartbeat_intervals.append(interval)
                if len(self.heartbeat_intervals) > 10:
                    del self.heartbeat_intervals[:-10]
        self._last_online_ts = ts

    def _enter_online(self, ts: int) -> None:
        was = self.device_online
        self.device_online = "online"
        self.last_qualifying_ts = ts
        self.offline_since = None
        if was != "online":
            for callback in self._on_online:
                callback(ts)

    def _enter_offline(self, start_ts: int) -> None:
        if self.device_online == "offline":
            return
        self.device_online = "offline"
        self.offline_since = start_ts
        for callback in self._on_offline:
            callback(start_ts)

    def _present(self, key: str) -> bool:
        last = self._presence_ts[key]
        if last is None:
            return False
        reconnect = self._reconnect_ts
        if reconnect is None or last >= reconnect:
            return True
        now = self._now if self._now is not None else last
        return now < reconnect + PRESENCE_HOLD_MS
