from dataclasses import dataclass
from typing import Literal, Mapping, Protocol

Kind = Literal["number", "enum", "text"]


@dataclass(frozen=True)
class Message:  # one received MQTT message, already split from <base>/
    topic: str  # e.g. "main/Outside_Temp", "LWT", "stats"
    payload: str
    retained: bool
    ts: int  # unix ms UTC, assigned at receipt


@dataclass
class TopicValue:  # spec §4.4 TopicValue, python side
    key: str
    value: float | str | None
    raw: str
    kind: Kind
    valid: bool  # False for sentinel / unparseable (spec §5.2 samples.valid)
    last_change: int
    last_seen: int
    retained_only: bool


@dataclass(frozen=True)
class Receipt:  # EVERY received message after parsing (not deduplicated) — plan review B4
    topic: str
    raw: str
    value: float | str | None
    valid: bool
    retained: bool
    ts: int
    qualifying: bool  # counted as liveness by the §4.1 rule list
    changed: bool  # differs from the previous stored value (ordinary history dedup)


@dataclass(frozen=True)
class Liveness:  # snapshot passed to Store.flush / Store.history — plan review B5
    device_online: Literal["unknown", "online", "offline"]
    last_qualifying_ts: int | None
    offline_since: int | None  # backdated outage start while offline


class Clock(Protocol):
    def now_ms(self) -> int: ...


__all__ = [
    "Kind", "Message", "TopicValue", "Receipt", "Liveness", "Clock", "Mapping",
]
