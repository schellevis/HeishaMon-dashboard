"""Heating-curve maths and overlay (spec §3, §8)."""
from heishamon_dashboard.curve import (
    curve_points, level_step, model_target, overlay, setcurves_diff, slope_step, validate_draft,
)

H = 1_791_000_000_000 // 3_600_000 * 3_600_000  # a UTC hour boundary (ms)
MIN = 60_000


def curve(co, ct, wo, wt):
    return {"cold": {"outside": co, "target": ct}, "warm": {"outside": wo, "target": wt}}


def test_crosswise_mapping():
    vals = {
        "main/Z2_Heat_Curve_Target_High_Temp": 45, "main/Z2_Heat_Curve_Target_Low_Temp": 30,
        "main/Z2_Heat_Curve_Outside_High_Temp": 15, "main/Z2_Heat_Curve_Outside_Low_Temp": -5,
        "main/Z2_Cool_Curve_Target_High_Temp": 1,
    }
    assert curve_points(vals, "z2", "heat") == curve(-5, 45, 15, 30)
    assert curve_points(vals, "z1", "heat") is None
    assert curve_points(vals, "z2", "cool") is None


def test_model_target_flat_ends_and_shift():
    c = curve(-10, 50, 10, 30)
    assert model_target(c, 0, -20) == 50
    assert model_target(c, 0, 20) == 30
    assert model_target(c, 0, 0) == 40
    assert model_target(c, 2, 0) == 42


def test_validate_ordering_and_limits():
    assert validate_draft(curve(-5, 40, 15, 40), "heat") == []  # equal targets allowed
    assert validate_draft(curve(5, 40, 5, 30), "heat") == ["outside_order"]  # equal outside refused
    assert validate_draft(curve(-5, 30, 15, 31), "heat") == ["target_order"]
    assert "limit:cold.target" in validate_draft(curve(-5, 76, 15, 30), "heat")
    assert "limit:warm.outside" in validate_draft(curve(-5, 40, 31, 30), "heat")
    assert validate_draft(curve(16, 20, 30, 5), "cool") == []
    assert "limit:cold.outside" in validate_draft(curve(14, 20, 30, 5), "cool")
    assert "limit:cold.target" in validate_draft(curve(16, 21, 30, 5), "cool")


def test_slope_and_level_whole_step_refusal():
    c = curve(-5, 75, 15, 30)
    assert slope_step(c, "heat", 1) is None  # cold end would be 76
    assert slope_step(c, "heat", -1) == curve(-5, 74, 15, 31)
    low = curve(-5, 40, 15, 15)
    assert level_step(low, "heat", -1) is None  # warm end would be 14
    assert level_step(low, "heat", 1) == curve(-5, 41, 15, 16)
    flat = curve(-5, 40, 15, 40)
    assert slope_step(flat, "heat", -1) is None  # would break target ordering
    assert slope_step(flat, "heat", 1) == curve(-5, 41, 15, 39)


def test_setcurves_diff_partial():
    cur = curve(-5, 45, 15, 30)
    d = setcurves_diff(cur, curve(-5, 47, 15, 28), "z1", "heat")
    assert d["json"] == {"zone1": {"heat": {"target": {"high": 47, "low": 28}}}}
    assert d["keys"] == {"Z1_Heat_Curve_Target_High_Temp": 47, "Z1_Heat_Curve_Target_Low_Temp": 28}
    d = setcurves_diff(cur, curve(-6, 45, 15, 30), "z2", "cool")
    assert d["json"] == {"zone2": {"cool": {"outside": {"low": -6}}}}
    assert setcurves_diff(cur, cur) == {"json": {}, "keys": {}}


class FakeStore:
    def __init__(self, series, boundary=None):
        self.series, self.boundary = series, boundary

    def rollups_1m(self, topics, from_ts, to_ts, now, liveness=None):
        return {t: [r for r in self.series.get(t, []) if from_ts // MIN <= r[0] < to_ts // MIN] for t in topics}

    def last_confirmed_setcurves(self, zone, mode):
        return self.boundary


def row(b, avg, cov=60, mn=None, mx=None, last=None):
    return (b, b * MIN, (b + 1) * MIN, cov, avg, avg if mn is None else mn,
            avg if mx is None else mx, avg if last is None else last)


def build(first, last, over=None, **fields):
    """Series for minutes [first, last); `over[(name, minute_index)]` replaces one row."""
    base = {"main/Outside_Temp": 2.0, "main/Main_Outlet_Temp": 35.0, "main/Z1_Water_Target_Temp": 33.0,
            "main/Operating_Mode_State": 0, "main/ThreeWay_Valve_State": 0, "main/Defrosting_State": 0,
            "main/Compressor_Freq": 40, "main/Heat_Power_Production": 3000.0,
            "main/Heat_Power_Consumption": 1000.0, "main/Z1_Sensor_Settings": 0}
    base.update(fields)
    base_b = H // MIN
    series = {k: [row(base_b + i, v) for i in range(first, last)] for k, v in base.items()}
    for (key, i), r in (over or {}).items():
        series[key] = [r if x[0] == base_b + i else x for x in series[key]]
    return series


def run(series, boundary=None, **kw):
    return overlay(FakeStore(series, boundary), "z1", "heat", H, H + 60 * MIN, H + 120 * MIN, **kw)


def test_overlay_minute_rules_and_windows():
    b = H // MIN
    over = {
        ("main/Compressor_Freq", 10): row(b + 10, 0, mn=0, mx=0),
        ("main/ThreeWay_Valve_State", 30): row(b + 30, 1, mn=0, mx=1),
        ("main/Defrosting_State", 45): row(b + 45, 0.2, mn=0, mx=1),
        ("main/Outside_Temp", 50): row(b + 50, 99.0, cov=59),
        ("main/Z1_Water_Target_Temp", 55): row(b + 55, 48.0),  # raises the window means
    }
    r = run(build(-10, 60, over))
    assert r["zone"] == "z1" and r["mode"] == "heat" and r["boundary_ts"] is None
    # only the last quarter has >= 12 eligible minutes: 15 - minute 45 (defrost) - minute 50 (coverage) = 13
    assert [w["start_ts"] for w in r["windows"]] == [H + 45 * MIN]
    w = r["windows"][0]
    assert w["eligible_minutes"] == 13
    assert w["outside"] == 2.0 and w["water"] == 35.0
    assert abs(w["target"] - (12 * 33.0 + 48.0) / 13) < 1e-9
    assert abs(w["water_minus_target"] - (35.0 - w["target"])) < 1e-9
    assert w["cop"] == 3.0 and w["freq"] == 40 and w["side"] is None and w["room_minus_setpoint"] is None
    assert r["median"] == []
    assert r["histogram"] == [{"band_lo": 2, "hours": 13 / 60}]


def test_overlay_exclusion_windows_exact():
    """Compressor off in minute 10 excludes 10..20; DHW in minute 30 excludes 30..40."""
    b = H // MIN
    over = {
        ("main/Compressor_Freq", 10): row(b + 10, 0, mn=0, mx=0),
        ("main/ThreeWay_Valve_State", 30): row(b + 30, 1, mn=1, mx=1),
    }
    r = run(build(-10, 60, over))
    # quarter 0: minutes 0..9 = 10; quarter 1: minutes 21..29 = 9; quarter 2: minutes 41..44 = 4
    assert [w["start_ts"] for w in r["windows"]] == [H + 45 * MIN]
    assert r["windows"][0]["eligible_minutes"] == 15


def test_overlay_lookback_before_range_start_is_required():
    # no rows before the range: the first 10 minutes fail condition 6, so quarter 0 has 5 eligible minutes
    r = run(build(0, 60))
    assert [w["start_ts"] for w in r["windows"]] == [H + 15 * MIN, H + 30 * MIN, H + 45 * MIN]


def test_overlay_mode_sets():
    heat_only = build(-10, 60, **{"main/Operating_Mode_State": 7})
    assert run(heat_only)["windows"] == []
    assert len(run(build(-10, 60, **{"main/Operating_Mode_State": 6}))["windows"]) == 4
    cool = build(-10, 60, **{"main/Operating_Mode_State": 8, "main/Cool_Power_Production": 2000.0,
                             "main/Cool_Power_Consumption": 1000.0, "main/Z1_Cool_Request_Temp": 18})
    r = overlay(FakeStore(cool), "z1", "cool", H, H + 60 * MIN, H + 120 * MIN)
    assert len(r["windows"]) == 4 and r["windows"][0]["cop"] == 2.0
    # a mode change inside a minute (min != max) excludes it
    b = H // MIN
    mixed = build(-10, 60, {("main/Operating_Mode_State", 20): row(b + 20, 1, mn=0, mx=2)})
    assert [w["eligible_minutes"] for w in run(mixed)["windows"]] == [15, 14, 15, 15]


def test_cop_zero_denominator_is_none():
    r = run(build(-10, 60, **{"main/Heat_Power_Consumption": 0.0}))
    assert len(r["windows"]) == 4 and all(w["cop"] is None for w in r["windows"])


def test_extra_power_preferred_when_present():
    s = build(-10, 60)
    b = H // MIN
    s["extra/Heat_Power_Production_Extra"] = [row(b + i, 2400.0) for i in range(-10, 60)]
    s["extra/Heat_Power_Consumption_Extra"] = [row(b + i, 800.0) for i in range(-10, 60)]
    assert run(s)["windows"][0]["cop"] == 3.0
    s["extra/Heat_Power_Production_Extra"] = [row(b + i, 1600.0) for i in range(-10, 60)]
    assert run(s)["windows"][0]["cop"] == 2.0


def test_boundary_sides():
    s = build(-10, 60)
    r = run(s, boundary=H + 20 * MIN)
    assert r["boundary_ts"] == H + 20 * MIN
    assert [w["side"] for w in r["windows"]] == ["before", "boundary", "after", "after"]
    assert run(s, boundary=H + 15 * MIN)["windows"][1]["side"] == "after"
    assert run(s, boundary=H + 30 * MIN)["windows"][1]["side"] == "before"


def test_room_minus_setpoint_only_with_room_sensor():
    s = build(-10, 60, **{"main/Room_Thermostat_Temp": 20.5, "main/Z1_Heat_Request_Temp": 21.0})
    assert run(s)["windows"][0]["room_minus_setpoint"] is None  # sensor setting 0 = water
    s["main/Z1_Sensor_Settings"] = [row(H // MIN + i, 1) for i in range(-10, 60)]
    assert run(s)["windows"][0]["room_minus_setpoint"] == -0.5


def test_median_two_vs_three_windows():
    def two(outsides):
        s = build(-10, 60)
        b = H // MIN
        s["main/Outside_Temp"] = [row(b + i, outsides[max(i, 0) // 15]) for i in range(-10, 60)]
        s["main/Main_Outlet_Temp"] = [row(b + i, 30.0 + 2 * (max(i, 0) // 15)) for i in range(-10, 60)]
        return run(s)

    # windows 0 and 1 in band [2,4), 2 and 3 in band [6,8): two per band -> no median line
    r = two([2.0, 3.0, 6.0, 7.0])
    assert r["median"] == []
    assert r["histogram"] == [{"band_lo": 2, "hours": 0.5}, {"band_lo": 6, "hours": 0.5}]
    # three in band [2,4): the plain median of 30, 32, 34
    r = two([2.0, 3.0, 3.9, 7.0])
    assert r["median"] == [{"band_lo": 2, "value": 32.0, "n": 3}]
    assert [h["band_lo"] for h in r["histogram"]] == [2, 6]
