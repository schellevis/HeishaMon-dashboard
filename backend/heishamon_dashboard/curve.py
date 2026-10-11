"""Heating-curve maths and the measured-data overlay (spec §3, §8, A.4).

A curve is `{"cold": {"outside": int, "target": int}, "warm": {"outside": int, "target": int}}`.
The cold end pairs `*_Outside_Low` with `*_Target_High`; the warm end pairs `*_Outside_High` with
`*_Target_Low` (the crosswise naming of §3).
"""
import re
from statistics import median
from typing import Any

from .types import Liveness

LIMITS = {
    "heat": {"outside": (-20, 30), "target": (15, 75)},
    "cool": {"outside": (15, 30), "target": (5, 20)},
}
# Operating_Mode_State values per tab (Appendix A.4 "overlay mode sets").
MODE_SETS = {"heat": {0, 2, 4, 6}, "cool": {1, 5, 7, 8}}
# Z1/Z2_Sensor_Settings values meaning a room sensor is configured (thermostat or thermistor).
ROOM_SENSOR_VALUES = {1, 2, 3}

MINUTE_MS = 60_000
WINDOW_MIN = 15
WINDOW_MS = WINDOW_MIN * MINUTE_MS
LOOKBACK_MIN = 10
MIN_ELIGIBLE = 12
MIN_MEDIAN_WINDOWS = 3
VALVE_ROOM, VALVE_DHW = 0, 1

# (curve end, field) -> (key part, SetCurves json path)
_LEAVES = {
    ("cold", "target"): ("Target_High", ("target", "high")),
    ("warm", "target"): ("Target_Low", ("target", "low")),
    ("warm", "outside"): ("Outside_High", ("outside", "high")),
    ("cold", "outside"): ("Outside_Low", ("outside", "low")),
}


def _zone_num(zone: Any) -> int:
    m = re.search(r"\d", str(zone))
    if not m:
        raise ValueError(f"zone {zone!r} has no number")
    return int(m.group())


def _mode(mode: str) -> str:
    m = str(mode).lower()
    if m not in LIMITS:
        raise ValueError(f"mode {mode!r} must be heat or cool")
    return m


def leaf_key(zone: Any, mode: str, end: str, field: str) -> str:
    """Catalog-style leaf name, e.g. Z1_Heat_Curve_Target_High_Temp."""
    part = _LEAVES[(end, field)][0]
    return f"Z{_zone_num(zone)}_{_mode(mode).capitalize()}_Curve_{part}_Temp"


def curve_points(values: dict, zone: Any, mode: str) -> dict | None:
    """Cold/warm end from published values (keys with or without the `main/` prefix); None if any is missing."""
    bare = {str(k).split("/")[-1]: v for k, v in values.items()}
    curve: dict = {"cold": {}, "warm": {}}
    for (end, field) in _LEAVES:
        v = bare.get(leaf_key(zone, mode, end, field))
        if v is None:
            return None
        curve[end][field] = v
    return curve


def model_target(curve: dict, shift: float, outside: float) -> float:
    """Water target the model expects: straight line between the ends, flat beyond them (a model
    assumption, unconfirmed), plus the curve-mode shift."""
    c, w = curve["cold"], curve["warm"]
    if outside <= c["outside"] or w["outside"] <= c["outside"]:
        base = c["target"]
    elif outside >= w["outside"]:
        base = w["target"]
    else:
        frac = (outside - c["outside"]) / (w["outside"] - c["outside"])
        base = c["target"] + frac * (w["target"] - c["target"])
    return base + shift


def validate_draft(draft: dict, mode: str) -> list[str]:
    """Error codes for a draft curve; empty when valid (ordering invariant and §8 limits)."""
    lim = LIMITS[_mode(mode)]
    errors: list[str] = []
    for end in ("cold", "warm"):
        for field in ("outside", "target"):
            v = draft[end][field]
            if isinstance(v, bool) or not isinstance(v, int):
                errors.append(f"not_integer:{end}.{field}")
            elif not lim[field][0] <= v <= lim[field][1]:
                errors.append(f"limit:{end}.{field}")
    if not errors:
        if draft["cold"]["outside"] + 1 > draft["warm"]["outside"]:
            errors.append("outside_order")
        if draft["cold"]["target"] < draft["warm"]["target"]:
            errors.append("target_order")
    return errors


def _stepped(curve: dict, mode: str, cold_d: int, warm_d: int) -> dict | None:
    new = {
        "cold": {"outside": curve["cold"]["outside"], "target": curve["cold"]["target"] + cold_d},
        "warm": {"outside": curve["warm"]["outside"], "target": curve["warm"]["target"] + warm_d},
    }
    return None if validate_draft(new, mode) else new


def slope_step(curve: dict, mode: str, delta: int) -> dict | None:
    """Cold target +delta, warm target -delta (+1 steepens). None when refused as a whole."""
    return _stepped(curve, mode, delta, -delta)


def level_step(curve: dict, mode: str, delta: int) -> dict | None:
    """Both targets +delta. None when refused as a whole."""
    return _stepped(curve, mode, delta, delta)


def setcurves_diff(current: dict, draft: dict, zone: Any = "z1", mode: str = "heat") -> dict:
    """Partial SetCurves JSON with only the changed leaves, plus `keys` (leaf name -> expected value)."""
    n, m = _zone_num(zone), _mode(mode)
    body: dict = {}
    keys: dict[str, int] = {}
    for (end, field), (_, (grp, hl)) in _LEAVES.items():
        new = draft[end][field]
        if new == current[end][field]:
            continue
        body.setdefault(f"zone{n}", {}).setdefault(m, {}).setdefault(grp, {})[hl] = new
        keys[leaf_key(n, m, end, field)] = new
    return {"json": body, "keys": keys}


# ------------------------------------------------------------------ overlay

def _topics(zone: Any, mode: str, own_water_sensor: bool, extra_power: bool) -> dict[str, str]:
    n, m = _zone_num(zone), _mode(mode).capitalize()
    suffix = "_Extra" if extra_power else ""
    return {
        "outside": "main/Outside_Temp",
        "water": f"main/Z{n}_Water_Temp" if own_water_sensor else "main/Main_Outlet_Temp",
        "target": f"main/Z{n}_Water_Target_Temp",
        "opmode": "main/Operating_Mode_State",
        "valve": "main/ThreeWay_Valve_State",
        "defrost": "main/Defrosting_State",
        "freq": "main/Compressor_Freq",
        "prod": f"{'extra' if extra_power else 'main'}/{m}_Power_Production{suffix}",
        "cons": f"{'extra' if extra_power else 'main'}/{m}_Power_Consumption{suffix}",
        "sensor": f"main/Z{n}_Sensor_Settings",
        "room": "main/Room_Thermostat_Temp" if n == 1 else "main/Second_Room_Thermostat_Temp",
        "setpoint": f"main/Z{n}_{m}_Request_Temp",
    }


def _full(row) -> bool:
    return row is not None and row[3] == 60 and row[4] is not None


def overlay(store, zone: Any, mode: str, from_ts: int, to_ts: int, now: int,
            liveness: Liveness | None = None, *, own_water_sensor: bool = False,
            extra_power: bool | None = None) -> dict:
    """Spec §4.4 `Overlay`, evaluated per minute from `rollups_1m` (§8). Times are ms.

    `own_water_sensor` selects Z1/Z2_Water_Temp instead of Main_Outlet_Temp. `extra_power=None`
    uses the `extra/` power pair when it has any data in range, else the coarse `main/` pair.
    """
    z, md = f"z{_zone_num(zone)}", _mode(mode)
    lo = (from_ts // MINUTE_MS) - LOOKBACK_MIN
    t0 = lo * MINUTE_MS
    if extra_power is None:
        probe = _topics(z, md, own_water_sensor, True)
        got = store.rollups_1m([probe["prod"], probe["cons"]], t0, to_ts, now, liveness)
        extra_power = any(r[3] > 0 for rows in got.values() for r in rows)
    tp = _topics(z, md, own_water_sensor, extra_power)
    data = store.rollups_1m(list(tp.values()), t0, to_ts, now, liveness)
    rows = {name: {r[0]: r for r in data.get(key, [])} for name, key in tp.items()}
    boundary = store.last_confirmed_setcurves(z, md)
    modes = MODE_SETS[md]
    required = ("outside", "water", "target", "opmode", "valve", "defrost", "freq", "prod", "cons")

    def compressor_ok(b):  # condition 4 with full coverage (used by condition 6 too)
        r = rows["freq"].get(b)
        return _full(r) and r[5] > 0

    def dhw_at(b):
        r = rows["valve"].get(b)
        return r is not None and r[3] > 0 and VALVE_DHW in (r[5], r[6])

    def eligible(b):
        if not all(_full(rows[n].get(b)) for n in required):
            return False
        if rows["defrost"][b][6] != 0:
            return False
        v = rows["valve"][b]
        if v[5] != VALVE_ROOM or v[6] != VALVE_ROOM:
            return False
        if not compressor_ok(b):
            return False
        o = rows["opmode"][b]
        if o[5] != o[6] or o[5] not in modes:
            return False
        for p in range(b - LOOKBACK_MIN, b):
            if not compressor_ok(p) or dhw_at(p):
                return False
        return True

    first_w = -(-from_ts // WINDOW_MS)
    last_w = (min(to_ts, now) - 1) // WINDOW_MS if min(to_ts, now) > 0 else -1
    windows = []
    for w in range(first_w, last_w + 1):
        start = w * WINDOW_MS
        if start < from_ts or start >= to_ts:
            continue
        mins = [b for b in range(w * WINDOW_MIN, (w + 1) * WINDOW_MIN) if eligible(b)]
        if len(mins) < MIN_ELIGIBLE:
            continue
        mean = lambda name: sum(rows[name][b][4] for b in mins) / len(mins)  # noqa: E731
        outside, water, target = mean("outside"), mean("water"), mean("target")
        prod = sum(rows["prod"][b][4] for b in mins)
        cons = sum(rows["cons"][b][4] for b in mins)
        room_diff = None
        sensor = rows["sensor"].get(mins[-1])
        if sensor is not None and sensor[7] in ROOM_SENSOR_VALUES:
            both = [b for b in mins if _full(rows["room"].get(b)) and _full(rows["setpoint"].get(b))]
            if both:
                room_diff = sum(rows["room"][b][4] - rows["setpoint"][b][4] for b in both) / len(both)
        side = None
        if boundary is not None:
            side = "boundary" if start < boundary < start + WINDOW_MS else (
                "before" if boundary >= start + WINDOW_MS else "after")
        windows.append({
            "start_ts": start, "outside": outside, "water": water, "target": target,
            "water_minus_target": water - target, "cop": prod / cons if cons > 0 else None,
            "freq": mean("freq"), "room_minus_setpoint": room_diff, "side": side,
            "eligible_minutes": len(mins),
        })

    bands: dict[int, list[dict]] = {}
    for win in windows:
        bands.setdefault(int(win["outside"] // 2) * 2, []).append(win)
    return {
        "zone": z, "mode": md, "boundary_ts": boundary, "windows": windows,
        "median": [{"band_lo": k, "value": median(x["water"] for x in v), "n": len(v)}
                   for k, v in sorted(bands.items()) if len(v) >= MIN_MEDIAN_WINDOWS],
        "histogram": [{"band_lo": k, "hours": sum(x["eligible_minutes"] for x in v) / 60}
                      for k, v in sorted(bands.items())],
    }
