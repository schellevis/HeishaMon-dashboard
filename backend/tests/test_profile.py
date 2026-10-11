import copy
import json
from pathlib import Path

import pytest

from heishamon_dashboard import catalog as cat
from heishamon_dashboard.profile import derive
from heishamon_dashboard.types import TopicValue

NOW = 1_760_000_000_000
HEX = "E2 CF 0B 97 05 12 05 34 A1 09"

_data = json.loads((Path(cat.__file__).parent / "catalog.json").read_text())
_data["models"] = [{"hex": HEX, "name": "WH-TEST", "series": "K"}]
CATALOG = cat.parse(_data)


def tv(key, value, age_s=1, valid=True, raw=None):
    kind = "text" if isinstance(value, str) else "enum"
    return TopicValue(key=key, value=value, raw=raw if raw is not None else str(value), kind=kind,
                      valid=valid, last_change=NOW - age_s * 1000, last_seen=NOW - age_s * 1000,
                      retained_only=False)


def vals(**kw):
    return {f"main/{k}": tv(f"main/{k}", v) for k, v in kw.items()}


def F(v):
    return {"value": v, "unknown": False, "stale": False}


U = {"value": None, "unknown": True, "stale": False}
NO = {"main": {}}


def full(**kw):
    """Expected profile for a fully-unknown installation; override fields via kw."""
    zone = {"active": U, "sensor": U, "heat_control": U, "cool_control": U}
    exp = {
        "computed_at": NOW, "operating_mode": U, "heating_in_use": U, "cooling_in_use": U, "dhw_in_use": U,
        "zones": U, "heating_control": U, "cooling_control": U,
        "zone": {"z1": dict(zone), "z2": dict(zone)},
        "dhw_installed": U, "buffer_installed": U, "solar": U, "bivalent": U, "glycol": U,
        "optional_pcb_setting": U, "pcb_emulation_active": F(False),
        "has_extra": F(False), "has_1wire": F(False), "has_s0": F(False), "has_opentherm": F(False),
        "model": U, "series": U, "firmware": U, "firmware_assumed": True, "board": U,
    }
    exp.update(kw)
    return exp


def run(values, presence=None, pcb=None, fw=None, online=True):
    return derive(values, NOW, online, presence or {}, pcb, fw, CATALOG)


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


def inputs(mode, zs, hm, cm, s1=0, s2=0, **more):
    zc = {"z1": 0, "z2": 1, "both": 2}[zs]
    return vals(Operating_Mode_State=mode, Zones_State=zc, Heating_Mode=0 if hm == "curve" else 1,
                Cooling_Mode=0 if cm == "curve" else 1, Z1_Sensor_Settings=s1, Z2_Sensor_Settings=s2, **more)


MODES = {  # preset name -> operating mode
    "heat_only": 0, "cool_only": 1, "dhw_only": 3, "heat_dhw": 4, "cool_dhw": 5,
    "auto_heat": 2, "auto_heat_dhw": 6, "auto_cool_mode7": 7, "auto_cool_dhw": 8,
}


@pytest.mark.parametrize("name,mode", MODES.items())
def test_mode_presets(name, mode):
    got = run(inputs(mode, "z1", "curve", "curve"))
    assert got == full(**preset(mode))


def test_two_zones_heat_curve_cool_direct():
    got = run(inputs(4, "both", "curve", "direct"))
    assert got == full(**preset(4, "both", "curve", "direct"))
    # shared control: both zones inherit the installation-wide value
    assert got["zone"]["z1"]["heat_control"] == got["zone"]["z2"]["heat_control"] == F("curve")
    assert got["zone"]["z1"]["cool_control"] == got["zone"]["z2"]["cool_control"] == F("direct")


def test_z1_water_z2_internal_thermostat():
    got = run(inputs(0, "both", "direct", "curve", s1=0, s2=2))
    assert got == full(**preset(0, "both", "direct", "curve", s1=0, s2=2))
    assert got["zone"]["z1"]["sensor"] == F("water")
    assert got["zone"]["z2"]["sensor"] == F("int_thermostat")


def test_zone2_only_and_thermistor():
    got = run(inputs(1, "z2", "curve", "curve", s1=3, s2=1))
    assert got == full(**preset(1, "z2", s1=3, s2=1))
    assert got["zone"]["z1"]["active"] == F(False) and got["zone"]["z2"]["active"] == F(True)


@pytest.mark.parametrize("dhw,buf", [(0, 0), (1, 0), (0, 1), (1, 1)])
def test_dhw_and_buffer_installed(dhw, buf):
    got = run(inputs(0, "z1", "curve", "curve", DHW_Installed=dhw, Buffer_Installed=buf))
    assert got == full(**preset(0), dhw_installed=F(bool(dhw)), buffer_installed=F(bool(buf)))


def test_extra_present_and_absent():
    on = run({}, presence={"extra": True})
    off = run({}, presence={"extra": False})
    assert on == full(has_extra=F(True))
    assert off == full()


def test_no_integrations_and_all_integrations():
    assert run({}, presence={}) == full()
    allp = {"extra": True, "1wire": True, "s0": True, "opentherm": True}
    assert run({}, presence=allp) == full(
        has_extra=F(True), has_1wire=F(True), has_s0=F(True), has_opentherm=F(True))


@pytest.mark.parametrize("age,expect", [(0, True), (359, True), (360, True), (361, False)])
def test_pcb_emulation_window(age, expect):
    got = run(vals(Optional_PCB=1), pcb=NOW - age * 1000)
    assert got == full(optional_pcb_setting=F(True), pcb_emulation_active=F(expect))


def test_pcb_setting_on_without_live_and_never_live():
    assert run(vals(Optional_PCB=0), pcb=None) == full(optional_pcb_setting=F(False))


def test_solar_glycol_bivalent():
    got = run(vals(Solar_Mode=2, Liquid_Type=1, Bivalent_Control=1))
    assert got == full(solar=F("dhw"), glycol=F(True), bivalent=F(True))
    got = run(vals(Solar_Mode=1, Liquid_Type=0, Bivalent_Control=0))
    assert got == full(solar=F("buffer"), glycol=F(False), bivalent=F(False))
    assert run(vals(Solar_Mode=0))["solar"] == F("off")


def test_solar_mode_3_is_unknown_and_liquid_glycol():
    got = run(vals(Solar_Mode=3, Liquid_Type=1))
    assert got == full(solar=U, glycol=F(True))


def test_fw_3_2_3_numeric_model_no_bivalent():
    values = vals(**{"Heat_Pump_Model": "12"}, Operating_Mode_State=0)
    values["stats"] = tv("stats", json.dumps({"version": "3.2.3"}), raw=json.dumps({"version": "3.2.3"}))
    got = run(values, fw="3.2.3")
    assert got == full(operating_mode=F(0), heating_in_use=F(True), cooling_in_use=F(False),
                       dhw_in_use=F(False), firmware=F("3.2.3"), firmware_assumed=False,
                       model=U, series=U, bivalent=U)


def test_fw_assumed_when_unknown():
    got = run({}, fw="Local build")
    assert got["firmware"] == U and got["firmware_assumed"] is True


def test_model_exact_match_and_board():
    values = vals(Heat_Pump_Model=HEX)
    values["main/Heat_Pump_Model"].raw = HEX
    stats = json.dumps({"version": "4.2.3", "board": "esp32"})
    values["stats"] = tv("stats", stats, raw=stats)
    got = run(values, fw="v4.2.3")
    assert got == full(model=F("WH-TEST"), series=F("K"), firmware=F("v4.2.3"),
                       firmware_assumed=False, board=F("esp32"))


def test_model_no_match_gives_null_series():
    values = vals(Heat_Pump_Model="AA BB CC DD EE FF 00 11 22 33")
    got = run(values)
    assert got["model"] == U and got["series"] == U


def test_empty_catalog_models_gives_null_series():
    empty = cat.parse({**_data, "models": []})
    values = vals(Heat_Pump_Model=HEX)
    values["main/Heat_Pump_Model"].raw = HEX
    got = derive(values, NOW, True, {}, None, None, empty)
    assert got["series"] == U


def test_unknown_inputs_sentinel_and_missing():
    values = vals(Operating_Mode_State=-1, Zones_State=-1, Heating_Mode=2, Cooling_Mode=-1,
                  DHW_Installed=-1, Z1_Sensor_Settings=9)
    assert run(values) == full()
    assert run({}) == full()


def test_invalid_flag_is_unknown():
    values = {"main/Operating_Mode_State": tv("main/Operating_Mode_State", -1, valid=False)}
    assert run(values) == full()


def test_stale_input_while_online():
    values = inputs(4, "z1", "curve", "curve")
    values["main/Heating_Mode"] = tv("main/Heating_Mode", 0, age_s=661)
    got = run(values)
    stale = {"value": "curve", "unknown": False, "stale": True}
    exp = preset(4)
    exp["heating_control"] = stale
    exp["zone"] = copy.deepcopy(exp["zone"])
    exp["zone"]["z1"]["heat_control"] = stale
    exp["zone"]["z2"]["heat_control"] = stale
    assert got == full(**exp)


def test_stale_boundary_and_offline():
    v660 = {"main/Solar_Mode": tv("main/Solar_Mode", 1, age_s=660)}
    assert run(v660)["solar"] == F("buffer")
    v661 = {"main/Solar_Mode": tv("main/Solar_Mode", 1, age_s=661)}
    assert run(v661)["solar"] == {"value": "buffer", "unknown": False, "stale": True}
    assert run(v661, online=False)["solar"] == F("buffer")


def test_stale_derived_fields_follow_source():
    values = {"main/Operating_Mode_State": tv("main/Operating_Mode_State", 5, age_s=700)}
    got = run(values)
    s = lambda v: {"value": v, "unknown": False, "stale": True}
    assert got["operating_mode"] == s(5)
    assert (got["heating_in_use"], got["cooling_in_use"], got["dhw_in_use"]) == (s(False), s(True), s(True))
