"""Pure planner and gates tests: no scheduler, no MQTT, no store."""
import json
from pathlib import Path

import pytest

from heishamon_dashboard import catalog as catalog_mod
from heishamon_dashboard.commands.gates import check_gates, check_rate
from heishamon_dashboard.commands.planner import (
    Reject, drop_matching, nest_curve_leaves, plan_command, values_match,
)

CATALOG_PATH = Path(__file__).parent.parent / "heishamon_dashboard" / "catalog.json"
CAT = catalog_mod.parse(json.loads(CATALOG_PATH.read_text(encoding="utf-8")))
DHW = "main/DHW_Target_Temp"
CURVE_HIGH = "main/Z1_Heat_Curve_Target_High_Temp"
CURVE_LOW = "main/Z1_Heat_Curve_Target_Low_Temp"


def F(v, unknown=False, stale=False):
    return {"value": v, "unknown": unknown, "stale": stale}


def profile(**over):
    p = {
        "operating_mode": F(0), "heating_control": F("curve"), "cooling_control": F("curve"),
        "zone": {"z1": {"active": F(True), "sensor": F("water")},
                 "z2": {"active": F(True), "sensor": F("water")}},
        "dhw_installed": F(True), "pcb_emulation_active": F(False),
        "firmware": F("4.2.3"), "firmware_assumed": False,
    }
    p.update(over)
    return p


def plan(name, value, prof=None, current=None, inflight=None):
    cur = current or {}
    return plan_command(CAT, name, value, prof or profile(), cur.get, inflight)


def gates(p, confirm=False, **over):
    kw = dict(connected=True, device_online="online", prefs={}, profile=profile(), budget_ok=True)
    kw.update(over)
    check_gates(p, confirm, **kw)


def code(fn, *a, **kw):
    with pytest.raises(Reject) as e:
        fn(*a, **kw)
    return e.value.code


# ------------------------------------------------------------------ planner

def test_valid_setting_plans_expected_readback():
    p = plan("SetDHWTemp", 50)
    assert p.cls == "setting" and p.payload == "50"
    assert list(p.expected.values()) == [50]


def test_unknown_command_and_bad_type():
    assert code(plan, "NoSuchThing", 1) == "unknown_command"
    assert code(plan, "SetDHWTemp", "abc") != "unknown_command"


def test_out_of_range_rejected():
    assert code(plan, "SetDHWTemp", 500) == "out_of_range"


def test_curve_ordering_uses_readback_and_inflight():
    cur = {CURVE_HIGH: 40, CURVE_LOW: 30}
    ok = plan("SetCurves", {"zone1": {"heat": {"target": {"high": 45}}}}, current=cur)
    assert ok.expected == {CURVE_HIGH: 45}
    assert code(plan, "SetCurves", {"zone1": {"heat": {"target": {"low": 50}}}}, current=cur) == "out_of_range"
    # an unconfirmed in-flight high leaf takes part in the ordering check
    assert code(plan, "SetCurves", {"zone1": {"heat": {"target": {"low": 35}}}},
                current=cur, inflight={CURVE_HIGH: 32}) == "out_of_range"


def test_curve_unknown_readback_is_profile_unknown():
    assert code(plan, "SetCurves", {"zone1": {"heat": {"target": {"high": 45}}}}) == "profile_unknown"


def test_curve_malformed_and_limits():
    assert code(plan, "SetCurves", {"zone9": {}}) == "bad_type"
    assert code(plan, "SetCurves", {"zone1": {"heat": {"target": {"high": 99}}}}) == "out_of_range"
    assert code(plan, "SetCurves", {"zone1": {"heat": {"target": {"high": True}}}}) == "bad_type"


def test_nest_and_drop_matching():
    nested = nest_curve_leaves({CURVE_HIGH: 45, CURVE_LOW: 30})
    assert nested == {"zone1": {"heat": {"target": {"high": 45, "low": 30}}}}
    cur = {CURVE_HIGH: 40, CURVE_LOW: 30}
    p = plan("SetCurves", {"zone1": {"heat": {"target": {"high": 45, "low": 30}}}}, current=cur)
    p, sent = drop_matching(p, lambda _p, t, v: cur.get(t) == v, set())
    assert sent == {CURVE_HIGH: 45}
    assert json.loads(p.payload) == {"zone1": {"heat": {"target": {"high": 45}}}}


def test_values_match_rules():
    assert values_match("equal", 5, 5.0)
    assert not values_match("equal", 5, "5")
    assert values_match("holiday", 1, 2)
    assert not values_match("holiday", 0, 2)


# ------------------------------------------------------------------ gates

def test_gates_connection_and_device():
    p = plan("SetDHWTemp", 50)
    assert code(gates, p, connected=False) == "broker_disconnected"
    assert code(gates, p, device_online="offline") == "device_offline"
    assert code(gates, p, prefs={"write_lock": True}) == "write_lock"
    assert code(gates, p, budget_ok=False) == "storage_unavailable"
    gates(p)


def test_gates_firmware_and_unknown_profile():
    p = plan("SetDHWTemp", 50)
    p.entry = {**p.entry, "min_firmware": "99.0.0"}
    assert code(gates, p) == "firmware_too_old"
    p = plan("SetDHWTemp", 50)
    p.unknown_fields.append("heating_control")
    assert code(gates, p) == "profile_unknown"


def test_gates_confirm_and_read_only():
    p = plan("SetDHWTemp", 50)
    p.risky = True
    assert code(gates, p) == "confirm_required"
    gates(p, confirm=True)
    p.read_only = True
    assert code(gates, p, confirm=True) == "read_only_value"


def test_gates_pcb():
    p = plan("SetDHWTemp", 50)
    p.pcb = True
    assert code(gates, p, confirm=True) == "pcb_disabled"
    assert code(gates, p, confirm=True, prefs={"pcb_enabled": True}) == "pcb_emulation_inactive"
    gates(p, confirm=True, prefs={"pcb_enabled": True}, profile=profile(pcb_emulation_active=F(True)))


def test_rate_limit_window():
    check_rate("X", [1_000, 2_000], now=3_000, rate_max=3, rate_window_s=10)
    with pytest.raises(Reject) as e:
        check_rate("X", [1_000, 2_000, 2_500], now=3_000, rate_max=3, rate_window_s=10)
    assert e.value.code == "rate_limited" and e.value.status == 429
    assert e.value.detail == {"retry_after_s": 8}
    check_rate("X", [1_000, 2_000, 2_500], now=20_000, rate_max=3, rate_window_s=10)
