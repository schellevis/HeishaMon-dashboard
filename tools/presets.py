"""Installation presets for the HeishaMon simulator (spec §10).

Topic payloads are plain text. Profile-relevant topics are only those each preset
needs so `profile.derive` matches the T05 expectation for that name. Other main/
topics are filled by the simulator from the catalog.
"""
from __future__ import annotations

from dataclasses import dataclass, field

PROFILE_CHANGE_MS = 60_000

# Topics that feed profile.derive. The simulator does not invent values for these.
PROFILE_KEYS = frozenset({
    "main/Operating_Mode_State",
    "main/Zones_State",
    "main/Heating_Mode",
    "main/Cooling_Mode",
    "main/Z1_Sensor_Settings",
    "main/Z2_Sensor_Settings",
    "main/DHW_Installed",
    "main/Buffer_Installed",
    "main/Solar_Mode",
    "main/Liquid_Type",
    "main/Bivalent_Control",
    "main/Optional_PCB",
    "main/Heat_Pump_Model",
})


@dataclass(frozen=True)
class Preset:
    name: str
    topics: dict[str, str] = field(default_factory=dict)
    extra: tuple[tuple[str, str], ...] = ()
    stats: dict | None = None
    phases: tuple[tuple[int, dict[str, str]], ...] = ()
    max_top: int | None = None
    firmware_ceiling: tuple[int, int, int] | None = None
    block_opentherm_rw: bool = False


def mode_topics(mode, zs="z1", hm="curve", cm="curve", s1=0, s2=0):
    zones = {"z1": 0, "z2": 1, "both": 2}[zs]
    return {
        "main/Operating_Mode_State": str(mode),
        "main/Zones_State": str(zones),
        "main/Heating_Mode": "0" if hm == "curve" else "1",
        "main/Cooling_Mode": "0" if cm == "curve" else "1",
        "main/Z1_Sensor_Settings": str(s1),
        "main/Z2_Sensor_Settings": str(s2),
    }


def _mode(name, mode, zs="z1", hm="curve", cm="curve", s1=0, s2=0, **topics):
    merged = mode_topics(mode, zs, hm, cm, s1, s2)
    merged.update(topics)
    return Preset(name, merged)


_EXTRA = (("extra/Heat_Power_Consumption_Extra", "0"),)
_INTEGRATIONS = (
    ("extra/Heat_Power_Consumption_Extra", "0"),
    ("1wire/0000000000000000", "21.5"),
    ("s0/WatthourTotal/1", "0"),
    ("opentherm/write/outsideTemp", "5"),
)

PRESETS: dict[str, Preset] = {
    "heat_only": _mode("heat_only", 0),
    "cool_only": _mode("cool_only", 1),
    "dhw_only": _mode("dhw_only", 3),
    "heat_dhw": _mode("heat_dhw", 4),
    "cool_dhw": _mode("cool_dhw", 5),
    "auto_heat": _mode("auto_heat", 2),
    "auto_heat_dhw": _mode("auto_heat_dhw", 6),
    "auto_cool_mode7": _mode("auto_cool_mode7", 7),
    "auto_cool_dhw": _mode("auto_cool_dhw", 8),
    "two_zones_heat_curve_cool_direct": _mode(
        "two_zones_heat_curve_cool_direct", 4, "both", "curve", "direct"),
    "z1_water_z2_internal_thermostat": _mode(
        "z1_water_z2_internal_thermostat", 0, "both", "direct", "curve", 0, 2),
    "zone2_only_and_thermistor": _mode("zone2_only_and_thermistor", 1, "z2", s1=3, s2=1),
    "no_dhw_tank": _mode(
        "no_dhw_tank", 0, **{"main/DHW_Installed": "0", "main/Buffer_Installed": "0"}),
    "with_extra": Preset("with_extra", extra=_EXTRA),
    "without_extra": Preset("without_extra"),
    "pcb_active": Preset(
        "pcb_active",
        {"main/Optional_PCB": "1"},
        extra=(("optional/Z1_Water_Pump", "0"),),
    ),
    "pcb_inactive": Preset("pcb_inactive", {"main/Optional_PCB": "1"}),
    "no_integrations": Preset("no_integrations"),
    "all_integrations": Preset("all_integrations", extra=_INTEGRATIONS),
    "fw-3.2.3": Preset(
        "fw-3.2.3",
        {"main/Operating_Mode_State": "0", "main/Heat_Pump_Model": "12"},
        stats={"version": "3.2.3"},
        max_top=114,
        firmware_ceiling=(3, 2, 3),
        block_opentherm_rw=True,
    ),
    "unknown-inputs": Preset(
        "unknown-inputs",
        {
            "main/Operating_Mode_State": "-1",
            "main/Zones_State": "-1",
            "main/Heating_Mode": "2",
            "main/Cooling_Mode": "-1",
            "main/DHW_Installed": "-1",
            "main/Z1_Sensor_Settings": "9",
        },
    ),
    "profile-change": Preset(
        "profile-change",
        mode_topics(0),
        phases=((PROFILE_CHANGE_MS, {
            "main/Operating_Mode_State": "1",
            "main/Heating_Mode": "1",
        }),),
    ),
    "solar_mode_3": Preset("solar_mode_3", {"main/Solar_Mode": "3", "main/Liquid_Type": "1"}),
}

_ALIASES = {
    "heat-only": "heat_only",
    "cool-only": "cool_only",
    "dhw-only": "dhw_only",
    "Heat+DHW": "heat_dhw",
    "heat+dhw": "heat_dhw",
    "Cool+DHW": "cool_dhw",
    "cool+dhw": "cool_dhw",
    "auto-heat": "auto_heat",
    "auto-heat-dhw": "auto_heat_dhw",
    "auto (cool 7)": "auto_cool_mode7",
    "auto-cool": "auto_cool_mode7",
    "auto-cool-dhw": "auto_cool_dhw",
    "two-zone": "two_zones_heat_curve_cool_direct",
    "two-zones": "two_zones_heat_curve_cool_direct",
    "thermostat-thermistor": "zone2_only_and_thermistor",
    "no-dhw-tank": "no_dhw_tank",
    "with-extra": "with_extra",
    "without-extra": "without_extra",
    "PCB on": "pcb_active",
    "pcb-on": "pcb_active",
    "pcb_on": "pcb_active",
    "pcb-inactive": "pcb_inactive",
    "no-integrations": "no_integrations",
    "all-integrations": "all_integrations",
    "unknown_inputs": "unknown-inputs",
    "profile_change": "profile-change",
    "solar-mode-3": "solar_mode_3",
}


def resolve_preset(name: str) -> Preset:
    key = _ALIASES.get(name, name)
    try:
        return PRESETS[key]
    except KeyError:
        known = ", ".join(sorted(PRESETS))
        raise KeyError(f"unknown preset {name!r}; known: {known}") from None
