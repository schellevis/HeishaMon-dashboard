"""Derived values (spec §4.1 `derived`): live COP, energy from rollups, and event detection."""
from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from typing import Callable, Mapping

from .store import MINUTE_MAX_SPAN_MS, Store
from .types import Liveness, Receipt, TopicValue

MODES = ("heat", "cool", "dhw")
PERIODS = ("day", "month", "year")

_MAIN = {
    "heat": ("main/Heat_Power_Production", "main/Heat_Power_Consumption"),
    "cool": ("main/Cool_Power_Production", "main/Cool_Power_Consumption"),
    "dhw": ("main/DHW_Power_Production", "main/DHW_Power_Consumption"),
}
_EXTRA = {
    "heat": ("extra/Heat_Power_Production_Extra", "extra/Heat_Power_Consumption_Extra"),
    "cool": ("extra/Cool_Power_Production_Extra", "extra/Cool_Power_Consumption_Extra"),
    "dhw": ("extra/DHW_Power_Production_Extra", "extra/DHW_Power_Consumption_Extra"),
}


def has_extra(profile) -> bool:
    """True when the profile reports the extra/ data block (a bare bool is accepted too)."""
    if profile is None:
        return False
    flag = profile.get("has_extra") if isinstance(profile, Mapping) else profile
    if isinstance(flag, Mapping):
        return flag.get("value") is True and not flag.get("unknown", False)
    return flag is True


def power_topics(profile) -> tuple[dict[str, tuple[str, str]], bool]:
    """(mode -> (production topic, consumption topic), estimate flag).
    extra/ is preferred; main/ is coarse (~200 W steps), so results are flagged as estimates."""
    if has_extra(profile):
        return _EXTRA, False
    return _MAIN, True


def _watts(values: Mapping[str, TopicValue], key: str) -> float | None:
    tv = values.get(key)
    if tv is None or not tv.valid or isinstance(tv.value, bool) or not isinstance(tv.value, (int, float)):
        return None
    return float(tv.value)


def live_cop(values: Mapping[str, TopicValue], profile) -> dict:
    """Per-mode COP = production / consumption, None unless both are valid and consumption > 0."""
    topics, estimate = power_topics(profile)
    out: dict = {}
    for mode, (prod_key, cons_key) in topics.items():
        prod, cons = _watts(values, prod_key), _watts(values, cons_key)
        out[mode] = prod / cons if prod is not None and cons is not None and cons > 0 else None
    out["estimate"] = estimate
    return out


def _period_label(ts_ms: int, period: str, tz: tzinfo) -> str:
    d = datetime.fromtimestamp(ts_ms / 1000, tz)
    if period == "day":
        return d.strftime("%Y-%m-%d")
    if period == "month":
        return d.strftime("%Y-%m")
    return d.strftime("%Y")


def energy_joules(store: Store, from_ts: int, to_ts: int, period: str, now: int, profile=None,
                  liveness: Liveness | None = None, tz: tzinfo = timezone.utc) -> dict:
    """{label: {mode: {"production_j", "consumption_j"}}}; Σ avg × covered_seconds over rollups."""
    if period not in PERIODS:
        raise ValueError(f"period must be one of {PERIODS}")
    topics, _ = power_topics(profile)
    keys = [k for pair in topics.values() for k in pair]
    if to_ts - from_ts > MINUTE_MAX_SPAN_MS:  # long ranges: 1-hour rollups
        hist = store.history(keys, from_ts, to_ts, 10**9, now, liveness)
        if hist["resolution"] == "raw":  # cannot happen for such spans; guard anyway
            raise RuntimeError("expected rollup resolution")
        buckets = {k: [(p[0], p[1], p[2]) for p in hist["series"][k]["points"]] for k in keys}
    else:  # shorter ranges: the same sum over 1-minute rows
        rows = store.rollups_1m(keys, from_ts, to_ts, now, liveness)
        buckets = {k: [(r[0] * 60_000, r[4], r[3]) for r in rows[k]] for k in keys}
    out: dict = {}
    for mode, (prod_key, cons_key) in topics.items():
        for field, key in (("production_j", prod_key), ("consumption_j", cons_key)):
            for start, avg, covered in buckets[key]:
                if avg is None or not covered or start < from_ts or start >= to_ts:
                    continue
                slot = out.setdefault(_period_label(start, period, tz), {}).setdefault(
                    mode, {"production_j": 0.0, "consumption_j": 0.0})
                slot[field] += avg * covered
    return out


def energy(store: Store, from_ts: int, to_ts: int, period: str, now: int, profile=None,
           liveness: Liveness | None = None, tz: tzinfo = timezone.utc) -> dict:
    """kWh per day/month/year per mode: {"estimate": bool, "periods": {label: {mode: {...kwh}}}}.
    Modes without data are omitted."""
    joules = energy_joules(store, from_ts, to_ts, period, now, profile, liveness, tz)
    periods = {
        label: {m: {"production_kwh": v["production_j"] / 3_600_000,
                    "consumption_kwh": v["consumption_j"] / 3_600_000} for m, v in modes.items()}
        for label, modes in sorted(joules.items())
    }
    return {"estimate": power_topics(profile)[1], "periods": periods}


class EventDetector:
    """Turns state changes into spec §5.2 events, once per transition.
    The first value seen for a topic (and any retained one) only sets the baseline."""

    def __init__(self, append_event: Callable[[int, str, dict | None], object]):
        self._append = append_event
        self._last: dict[str, float | str] = {}
        self._device: str | None = None
        self._broker: bool | None = None

    def on_receipt(self, r: Receipt) -> None:
        if not r.valid or r.value is None:
            return
        key = r.topic
        if key == "main/Defrosting_State":
            prev, cur = self._last.get(key), r.value
            self._last[key] = cur
            if r.retained or prev is None or prev == cur:
                return
            if cur == 1:
                self._append(r.ts, "defrost_start", {})
            elif cur == 0 and prev == 1:
                self._append(r.ts, "defrost_end", {})
            return
        kind = {"main/Error": "error_change", "main/Operating_Mode_State": "mode_change",
                "main/ThreeWay_Valve_State": "valve_change"}.get(key)
        if kind is None:
            return
        prev, cur = self._last.get(key), r.value
        self._last[key] = cur
        if r.retained or prev is None or prev == cur:
            return
        self._append(r.ts, kind, {"from": prev, "to": cur})

    def on_device_online(self, ts: int) -> None:
        if self._device != "online":
            first = self._device is None
            self._device = "online"
            if not first:  # the first online after start is not a transition
                self._append(ts, "device_online", {})

    def on_device_offline(self, ts: int) -> None:
        if self._device != "offline":
            self._device = "offline"
            self._append(ts, "device_offline", {})

    def on_broker_connected(self, ts: int) -> None:
        if self._broker is not True:
            self._broker = True
            self._append(ts, "broker_connected", {})

    def on_broker_disconnected(self, ts: int) -> None:
        if self._broker is True:
            self._broker = False
            self._append(ts, "broker_disconnected", {})
