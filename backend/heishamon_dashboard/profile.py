"""Installation profile derivation (spec §4.3, Appendix A.4). Pure: no state import, no I/O."""
import json
from typing import Mapping

from .catalog import Catalog
from . import rules
from .firmware import parse_firmware
from .types import TopicValue

STALE_MS = 660_000
PCB_LIVE_MS = 360_000

_MODES = rules.load().operating_modes
_HEATING, _COOLING, _DHW = _MODES["heating"], _MODES["cooling"], _MODES["dhw"]
_ZONES = {0: "z1", 1: "z2", 2: "both"}
_CONTROL = {0: "curve", 1: "direct"}
_SENSOR = {0: "water", 1: "ext_thermostat", 2: "int_thermostat", 3: "thermistor"}
_BOOL = {0: False, 1: True}
_SOLAR = {0: "off", 1: "buffer", 2: "dhw"}
_LIQUID = {0: False, 1: True}


def _f(value=None, unknown=True, stale=False) -> dict:
    return {"value": None if unknown else value, "unknown": unknown, "stale": stale}


def _valid_set(catalog: Catalog, key: str) -> set[int] | None:
    """Integers the catalog enum accepts for a topic (sentinel and 'Unknown' entries excluded)."""
    topic = catalog.topic(key)
    if topic is None or not topic.get("enum"):
        return None
    bad = set(topic.get("sentinels") or [])
    out = set()
    for k, v in topic["enum"].items():
        if int(k) in bad or v["en"].strip().lower() == "unknown":
            continue
        out.add(int(k))
    return out


def derive(
    values: Mapping[str, TopicValue],
    now_ms: int,
    device_online,
    presence: Mapping[str, bool],
    pcb_last_live_ts: int | None,
    firmware: str | None,
    catalog: Catalog,
) -> dict:
    online = device_online is True or device_online == "online"

    def stale_of(tv: TopicValue) -> bool:
        return online and now_ms - tv.last_seen > STALE_MS

    def enum_in(key: str, mapping: dict, bool_like: bool = False) -> dict:
        tv = values.get(key)
        if tv is None or not tv.valid or not isinstance(tv.value, (int, float)):
            return _f(stale=tv is not None and stale_of(tv))
        stale = stale_of(tv)
        n = int(tv.value)
        allowed = _valid_set(catalog, key)
        if n != tv.value or n not in mapping or (allowed is not None and n not in allowed):
            return _f(stale=stale)
        return _f(mapping[n], False, stale)

    def derived(src: dict, fn) -> dict:
        if src["unknown"]:
            return _f(stale=src["stale"])
        return _f(fn(src["value"]), False, src["stale"])

    mode = enum_in("main/Operating_Mode_State", {i: i for i in range(9)})
    zones = enum_in("main/Zones_State", _ZONES)
    hctl = enum_in("main/Heating_Mode", _CONTROL)
    cctl = enum_in("main/Cooling_Mode", _CONTROL)

    def zone(n: int) -> dict:
        wanted = ("z1", "both") if n == 1 else ("z2", "both")
        return {
            "active": derived(zones, lambda v: v in wanted),
            "sensor": enum_in(f"main/Z{n}_Sensor_Settings", _SENSOR),
            "heat_control": dict(hctl),
            "cool_control": dict(cctl),
        }

    # model / series: exact match on the hex format (after whitespace/case normalisation) only;
    # numeric (pre-3.9) payloads give null
    model = _f()
    series = _f()
    tv = values.get("main/Heat_Pump_Model")
    if tv is not None:
        stale = stale_of(tv)
        model, series = _f(stale=stale), _f(stale=stale)
        hit = catalog.model(tv.raw)
        if hit is not None and tv.valid:
            model = _f(hit["name"], False, stale)
            series = _f(hit["series"], False, stale)

    ver, assumed = parse_firmware(firmware)
    stats = values.get("stats")
    stats_stale = stats is not None and stale_of(stats)
    fw = _f(firmware, False, stats_stale) if firmware and not assumed else _f(stale=stats_stale)
    board = _f(stale=stats_stale)
    if stats is not None:
        try:
            b = json.loads(stats.raw).get("board")
        except (ValueError, AttributeError):
            b = None
        if isinstance(b, str) and b:
            board = _f(b, False, stats_stale)

    def present(name: str) -> dict:
        return _f(bool(presence.get(name, False)), False, False)

    pcb_live = pcb_last_live_ts is not None and 0 <= now_ms - pcb_last_live_ts <= PCB_LIVE_MS

    return {
        "computed_at": now_ms,
        "operating_mode": mode,
        "heating_in_use": derived(mode, lambda v: v in _HEATING),
        "cooling_in_use": derived(mode, lambda v: v in _COOLING),
        "dhw_in_use": derived(mode, lambda v: v in _DHW),
        "zones": zones,
        "heating_control": hctl,
        "cooling_control": cctl,
        "zone": {"z1": zone(1), "z2": zone(2)},
        "dhw_installed": enum_in("main/DHW_Installed", _BOOL),
        "buffer_installed": enum_in("main/Buffer_Installed", _BOOL),
        "solar": enum_in("main/Solar_Mode", _SOLAR),
        "bivalent": enum_in("main/Bivalent_Control", _BOOL),
        "glycol": enum_in("main/Liquid_Type", _LIQUID),
        "optional_pcb_setting": enum_in("main/Optional_PCB", _BOOL),
        "pcb_emulation_active": _f(pcb_live, False, False),
        "has_extra": present("extra"),
        "has_1wire": present("1wire"),
        "has_s0": present("s0"),
        "has_opentherm": present("opentherm"),
        "model": model,
        "series": series,
        "firmware": fw,
        "firmware_assumed": assumed,
        "board": board,
    }
