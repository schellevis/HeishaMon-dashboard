"""Simulator presets and fault modes (spec §10, Appendix A.1). No sockets."""
import json
import socket
import sys
from pathlib import Path

import pytest

from heishamon_dashboard import catalog as cat
from heishamon_dashboard.profile import derive
from heishamon_dashboard.types import TopicValue

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from presets import PRESETS, PROFILE_CHANGE_MS, resolve_preset  # noqa: E402
from simulator import Simulator, parse_args  # noqa: E402

NOW = 1_760_000_000_000
CATALOG = cat.load(Path(cat.__file__).parent / "catalog.json")

_OT_LEAVES = {
    path.rsplit("/", 1)[-1]
    for path in (item["path"] for item in CATALOG.inputs)
    if path.startswith("opentherm/read/")
}


class FakeClock:
    def __init__(self, now=NOW):
        self.now = now

    def now_ms(self):
        return self.now


def F(v):
    return {"value": v, "unknown": False, "stale": False}


U = {"value": None, "unknown": True, "stale": False}


def full(now=NOW, **kw):
    """Same shape as T05's fully-unknown profile; kw overrides fields."""
    zone = {"active": U, "sensor": U, "heat_control": U, "cool_control": U}
    exp = {
        "computed_at": now, "operating_mode": U, "heating_in_use": U, "cooling_in_use": U, "dhw_in_use": U,
        "zones": U, "heating_control": U, "cooling_control": U,
        "zone": {"z1": dict(zone), "z2": dict(zone)},
        "dhw_installed": U, "buffer_installed": U, "solar": U, "bivalent": U, "glycol": U,
        "optional_pcb_setting": U, "pcb_emulation_active": F(False),
        "has_extra": F(False), "has_1wire": F(False), "has_s0": F(False), "has_opentherm": F(False),
        "model": U, "series": U, "firmware": U, "firmware_assumed": True, "board": U,
    }
    exp.update(kw)
    return exp


def zones(z1, z2):
    return {"z1": z1, "z2": z2}


def z(active, sensor, h, c):
    return {"active": F(active), "sensor": F(sensor), "heat_control": F(h), "cool_control": F(c)}


def preset(mode, zs="z1", hm="curve", cm="curve", s1=0, s2=0, **extra):
    heat, cool, dhw = mode in (0, 2, 4, 6), mode in (1, 5, 7, 8), mode in (3, 4, 5, 6, 8)
    z1a, z2a = zs in ("z1", "both"), zs in ("z2", "both")
    sensors = ["water", "ext_thermostat", "int_thermostat", "thermistor"]
    return dict(
        operating_mode=F(mode), heating_in_use=F(heat), cooling_in_use=F(cool), dhw_in_use=F(dhw),
        zones=F(zs), heating_control=F(hm), cooling_control=F(cm),
        zone=zones(z(z1a, sensors[s1], hm, cm), z(z2a, sensors[s2], hm, cm)), **extra)


def expected_for(name, now=NOW):
    """T05 expectation for each preset name. Independent of the simulator's topic table."""
    modes = {
        "heat_only": 0, "cool_only": 1, "dhw_only": 3, "heat_dhw": 4, "cool_dhw": 5,
        "auto_heat": 2, "auto_heat_dhw": 6, "auto_cool_mode7": 7, "auto_cool_dhw": 8,
    }
    if name in modes:
        return full(now, **preset(modes[name]))
    special = {
        "two_zones_heat_curve_cool_direct": full(now, **preset(4, "both", "curve", "direct")),
        "z1_water_z2_internal_thermostat": full(now, **preset(0, "both", "direct", "curve", 0, 2)),
        "zone2_only_and_thermistor": full(now, **preset(1, "z2", s1=3, s2=1)),
        "no_dhw_tank": full(now, **preset(0), dhw_installed=F(False), buffer_installed=F(False)),
        "with_extra": full(now, has_extra=F(True)),
        "without_extra": full(now),
        "pcb_active": full(now, optional_pcb_setting=F(True), pcb_emulation_active=F(True)),
        "pcb_inactive": full(now, optional_pcb_setting=F(True), pcb_emulation_active=F(False)),
        "no_integrations": full(now),
        "all_integrations": full(
            now, has_extra=F(True), has_1wire=F(True), has_s0=F(True), has_opentherm=F(True)),
        "fw-3.2.3": full(
            now, operating_mode=F(0), heating_in_use=F(True), cooling_in_use=F(False),
            dhw_in_use=F(False), firmware=F("3.2.3"), firmware_assumed=False, model=U, series=U, bivalent=U),
        "unknown-inputs": full(now),
        "profile-change": full(now, **preset(0)),
        "solar_mode_3": full(now, solar=U, glycol=F(True)),
    }
    return special[name]


def run(name, fault_modes=None, now=NOW):
    clock = FakeClock(now)
    log = []

    def publish(topic, payload, retained):
        log.append((topic, str(payload), bool(retained), clock.now_ms()))

    sim = Simulator(name, fault_modes or {}, publish, clock)
    sim.start()
    return sim, clock, log


def _latest(log):
    out = {}
    for topic, payload, retained, ts in log:
        out[topic] = (payload, retained, ts)
    return out


def _values(log):
    values = {}
    for topic, (payload, _retained, ts) in _latest(log).items():
        if not (topic.startswith("main/") or topic == "stats"):
            continue
        if topic == "stats" or not payload.lstrip("-").replace(".", "", 1).isdigit():
            value, kind = payload, "text"
        elif "." in payload:
            value, kind = float(payload), "number"
        else:
            value, kind = int(payload), "number"
        values[topic] = TopicValue(topic, value, payload, kind, True, ts, ts, False)
    return values


def _presence(log):
    flags = {"extra": False, "1wire": False, "s0": False, "opentherm": False}
    for topic, *_ in log:
        for name in flags:
            if topic.startswith(name + "/"):
                flags[name] = True
    return flags


def _pcb_ts(log):
    ts = None
    for topic, _payload, _retained, seen in log:
        if topic.startswith("optional/"):
            ts = seen
    return ts


def _firmware(log):
    version = None
    for topic, payload, *_ in log:
        if topic != "stats":
            continue
        try:
            raw = json.loads(payload).get("version")
        except json.JSONDecodeError:
            raw = None
        version = raw if isinstance(raw, str) else None
    return version


def profile_of(log, now):
    return derive(_values(log), now, True, _presence(log), _pcb_ts(log), _firmware(log), CATALOG)


def payload(log, topic):
    return _latest(log)[topic][0]


def test_preset_names_cover_section_10_and_t05():
    required = {
        "heat_only", "cool_only", "dhw_only", "heat_dhw", "cool_dhw",
        "auto_heat", "auto_heat_dhw", "auto_cool_mode7", "auto_cool_dhw",
        "two_zones_heat_curve_cool_direct", "z1_water_z2_internal_thermostat",
        "zone2_only_and_thermistor", "no_dhw_tank", "with_extra", "without_extra",
        "pcb_active", "pcb_inactive", "no_integrations", "all_integrations",
        "fw-3.2.3", "unknown-inputs", "profile-change", "solar_mode_3",
    }
    assert required <= set(PRESETS)
    assert set(PRESETS) == required
    assert PROFILE_CHANGE_MS == 60_000


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_preset_profile_matches_t05(name):
    _sim, clock, log = run(name)
    assert profile_of(log, clock.now_ms()) == expected_for(name, clock.now_ms())


def test_unknown_inputs_publish_sentinels_and_omit_version():
    _sim, _clock, log = run("unknown-inputs")
    assert payload(log, "main/Operating_Mode_State") == "-1"
    assert payload(log, "main/Zones_State") == "-1"
    assert payload(log, "main/Heating_Mode") == "2"
    assert payload(log, "main/Cooling_Mode") == "-1"
    assert payload(log, "main/DHW_Installed") == "-1"
    assert payload(log, "main/Z1_Sensor_Settings") == "9"
    assert "version" not in json.loads(payload(log, "stats"))


def test_fw_323_topics_version_and_numeric_model():
    _sim, _clock, log = run("fw-3.2.3")
    assert json.loads(payload(log, "stats"))["version"] == "3.2.3"
    assert payload(log, "main/Heat_Pump_Model") == "12"
    for topic, *_ in log:
        assert not topic.startswith("opentherm/read")
        assert not topic.startswith("opentherm/write")
        meta = CATALOG.topic(topic)
        if meta is None:
            continue
        ident = meta["id"]
        if ident.startswith("TOP") and ident[3:].isdigit():
            assert int(ident[3:]) <= 114


def test_integration_markers_and_no_ip_topic():
    _sim, _clock, extra = run("with_extra")
    assert any(t.startswith("extra/") for t, *_ in extra)
    _sim, _clock, bare = run("no_integrations")
    assert not any(t.startswith(("extra/", "1wire/", "s0/", "opentherm/", "optional/")) for t, *_ in bare)
    _sim, _clock, allp = run("all_integrations")
    for prefix in ("extra/", "1wire/", "s0/", "opentherm/write/"):
        assert any(t.startswith(prefix) for t, *_ in allp)
    for _sim, _clock, log in (run(name) for name in PRESETS):
        assert all(topic != "ip" and not topic.startswith("ip/") for topic, *_ in log)


def test_published_topics_come_from_the_catalog_or_spec_paths():
    for name in PRESETS:
        _sim, _clock, log = run(name)
        for topic, *_rest in log:
            if topic in ("LWT", "stats"):
                continue
            if CATALOG.topic(topic) is not None or CATALOG.input(topic) is not None:
                continue
            if topic == "1wire/0000000000000000":
                continue
            if topic.startswith("opentherm/write/"):
                assert topic.rsplit("/", 1)[-1] in _OT_LEAVES
                continue
            raise AssertionError(f"{name} published unknown topic {topic}")


def test_retained_snapshot_lwt_and_full_republish():
    sim, clock, log = run("heat_only")
    values = [(t, r) for t, _p, r, _ts in log if t != "LWT"]
    assert values and all(r is True for _t, r in values)
    lwt = [(p, r) for t, p, r, _ts in log if t == "LWT"]
    assert lwt == [("Online", False)]

    clock.now = NOW + 4_999
    sim.tick()
    assert [p for t, p, _r, _ts in log if t == "LWT"] == ["Online"]

    clock.now = NOW + 5_000
    sim.tick()
    assert [(p, r) for t, p, r, _ts in log if t == "LWT"] == [("Online", False), ("Online", False)]

    before = sum(1 for t, *_ in log if t == "main/Outside_Temp")
    clock.now = NOW + 299_999
    sim.tick()
    assert sum(1 for t, *_ in log if t == "main/Outside_Temp") == before
    clock.now = NOW + 300_000
    sim.tick()
    outside = [(p, r) for t, p, r, _ts in log if t == "main/Outside_Temp"]
    assert len(outside) == before + 1
    assert all(r is True for _p, r in outside)


def test_profile_change_switches_mode_and_curve():
    sim, clock, log = run("profile-change")
    assert profile_of(log, clock.now_ms()) == expected_for("profile-change", clock.now_ms())
    outside = sum(1 for t, *_ in log if t == "main/Outside_Temp")
    clock.now = NOW + 59_999
    sim.tick()
    assert payload(log, "main/Operating_Mode_State") == "0"
    clock.now = NOW + PROFILE_CHANGE_MS
    sim.tick()
    assert payload(log, "main/Operating_Mode_State") == "1"
    assert payload(log, "main/Heating_Mode") == "1"
    assert sum(1 for t, *_ in log if t == "main/Outside_Temp") == outside
    assert profile_of(log, clock.now_ms()) == full(clock.now_ms(), **preset(1, hm="direct"))
    sim.tick()
    assert sum(1 for t, p, *_ in log if t == "main/Operating_Mode_State" and p == "1") == 1


def _after(log, n):
    return log[n:]


def test_fault_echo_drop_and_drop_first():
    sim, clock, log = run("heat_only", {"SetOperationMode": "drop", "SetZones": "drop_first"})
    n = len(log)
    sim.command("SetDHWTemp", "50")
    echoed = _after(log, n)
    assert echoed == [("main/DHW_Target_Temp", "50", True, clock.now_ms())]

    n = len(log)
    sim.command("SetOperationMode", "4")
    clock.now = NOW + 100_000
    sim.tick()
    assert not any(t == "main/Operating_Mode_State" and p == "4" for t, p, *_ in _after(log, n))

    n = len(log)
    sim.command("SetZones", "2")
    assert not any(t == "main/Zones_State" and p == "2" for t, p, *_ in _after(log, n))
    sim.command("SetZones", "2")
    assert ("main/Zones_State", "2", True, clock.now_ms()) in _after(log, n)
    sim.command("SetZones", "1")
    assert ("main/Zones_State", "1", True, clock.now_ms()) in log


def test_fault_delay_partial_and_listen_only():
    sim, clock, log = run("heat_only", {"SetDHWTemp": "delay:10", "SetCurves": "partial"})
    n = len(log)
    sim.command("SetDHWTemp", "48")
    clock.now = NOW + 9_999
    sim.tick()
    assert not any(t == "main/DHW_Target_Temp" and p == "48" for t, p, *_ in _after(log, n))
    clock.now = NOW + 10_000
    sim.tick()
    assert ("main/DHW_Target_Temp", "48", True, clock.now_ms()) in _after(log, n)

    body = {
        "zone1": {"heat": {"target": {"high": 55, "low": 35}, "outside": {"high": 15, "low": -10}}}
    }
    leaves = {
        "main/Z1_Heat_Curve_Target_High_Temp": "55",
        "main/Z1_Heat_Curve_Target_Low_Temp": "35",
        "main/Z1_Heat_Curve_Outside_High_Temp": "15",
        "main/Z1_Heat_Curve_Outside_Low_Temp": "-10",
    }
    n = len(log)
    sim.command("SetCurves", json.dumps(body))
    got = {t: p for t, p, retained, _ts in _after(log, n) if t in leaves}
    assert all(retained is True for t, _p, retained, _ts in _after(log, n) if t in leaves)
    assert got == {k: v for k, v in leaves.items() if k != "main/Z1_Heat_Curve_Outside_Low_Temp"}
    assert "main/Z1_Heat_Curve_Outside_Low_Temp" not in got

    sim2, clock2, log2 = run("heat_only", {"*": "listen_only"})
    n = len(log2)
    sim2.command("SetDHWTemp", "50")
    sim2.command("SetOperationMode", "4")
    sim2.command("SetCurves", json.dumps(body))
    assert _after(log2, n) == []
    clock2.now = NOW + 5_000
    sim2.tick()
    assert [item for item in _after(log2, n) if item[0] == "LWT"] == [("LWT", "Online", False, clock2.now_ms())]


def test_per_command_listen_only_drops_that_command_only():
    sim, _clock, log = run("heat_only", {"SetDHWTemp": "listen_only"})
    n = len(log)
    sim.command("SetDHWTemp", "50")
    sim.command("SetOperationMode", "4")
    assert not any(t == "main/DHW_Target_Temp" for t, *_ in _after(log, n))
    assert ("main/Operating_Mode_State", "4", True, NOW) in _after(log, n)


def test_library_does_not_open_sockets(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("socket opened")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    sim, _clock, log = run("cool_only")
    sim.command("SetDHWTemp", "45")
    sim.tick()
    assert any(t == "LWT" for t, *_ in log)


def test_cli_parses_without_connecting():
    args = parse_args(["--host", "broker.example", "--port", "1883", "--preset", "heat_only", "--base", "hp"])
    assert (args.host, args.port, args.preset, args.base) == ("broker.example", 1883, "heat_only", "hp")
    defaulted = parse_args(["--host", "127.0.0.1", "--port", "1", "--preset", "fw-3.2.3"])
    assert defaulted.base == "panasonic_heat_pump"
    assert resolve_preset("PCB on").name == "pcb_active"
    assert resolve_preset("auto (cool 7)").name == "auto_cool_mode7"
    assert resolve_preset("Heat+DHW").name == "heat_dhw"
    assert resolve_preset("two-zone").name == "two_zones_heat_curve_cool_direct"
    assert resolve_preset("fw-3.2.3").name == "fw-3.2.3"


def test_unknown_command_is_ignored():
    sim, _clock, log = run("heat_only")
    n = len(log)
    sim.command("NotACommand", "1")
    assert log[n:] == []


def test_simulator_readback_retained():
    """Value read-backs are retained like HeishaMon's; the LWT stays non-retained."""
    sim, _clock, log = run("heat_dhw")
    n = len(log)
    sim.command("SetDHWTemp", "50")
    after = _after(log, n)
    assert after and all(retained is True for _t, _p, retained, _ts in after)
    assert ("main/DHW_Target_Temp", "50", True, NOW) in after
    assert _latest(log)["main/DHW_Target_Temp"][:2] == ("50", True)
