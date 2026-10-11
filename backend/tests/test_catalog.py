"""Test the complete catalog data (T02)."""
import json
from pathlib import Path

import pytest

from heishamon_dashboard import catalog

HERE = Path(__file__).parent
CATALOG_PATH = HERE.parent / "heishamon_dashboard" / "catalog.json"


@pytest.fixture
def cat():
    return catalog.load(CATALOG_PATH)


# ---------------------------------------------------------------------------
# Command inventory (A.2: exactly 64 commands)
# ---------------------------------------------------------------------------

# All 64 command names from A.2
A2_COMMAND_NAMES = {
    "SetHeatpump",
    "SetPump",
    "SetMaxPumpDuty",
    "SetQuietMode",
    "SetZ1HeatRequestTemperature",
    "SetZ1CoolRequestTemperature",
    "SetZ2HeatRequestTemperature",
    "SetZ2CoolRequestTemperature",
    "SetForceDHW",
    "SetForceDefrost",
    "SetForceSterilization",
    "SetSterilizationTemp",
    "SetSterilizationMaxTime",
    "SetForceHeater",
    "SetHolidayMode",
    "SetPowerfulMode",
    "SetOperationMode",
    "SetDHWTemp",
    "SetCurves",
    "SetZones",
    "SetFloorHeatDelta",
    "SetFloorCoolDelta",
    "SetDHWHeatDelta",
    "SetReset",
    "SetHeaterDelayTime",
    "SetHeaterStartDelta",
    "SetHeaterStopDelta",
    "SetMainSchedule",
    "SetAltExternalSensor",
    "SetExternalPadHeater",
    "SetBufferDelta",
    "SetBuffer",
    "SetHeatingOffOutdoorTemp",
    "SetExternalControl",
    "SetExternalError",
    "SetExternalCompressorControl",
    "SetExternalHeatCoolControl",
    "SetBivalentControl",
    "SetBivalentMode",
    "SetBivalentStartTemp",
    "SetBivalentAPStartTemp",
    "SetBivalentAPStopTemp",
    "SetHeatingControl",
    "SetSmartDHW",
    "SetQuietModePriority",
    "SetPumpFlowrateMode",
    "SetDHWSensorSelection",
    "SetDHWHeaterState",
    "SetRoomHeaterState",
    "SetHeaterOnOutdoorTemp",
    # PCB commands (14 with pcb=true)
    "SetHeatCoolMode",
    "SetCompressorState",
    "SetSmartGridMode",
    "SetExternalThermostat1State",
    "SetExternalThermostat2State",
    "SetDemandControl",
    "SetPoolTemp",
    "SetBufferTemp",
    "SetZ1RoomTemp",
    "SetZ1WaterTemp",
    "SetZ2RoomTemp",
    "SetZ2WaterTemp",
    "SetSolarTemp",
    "SetOptPCBByte9",
}

# 14 PCB commands
PCB_COMMANDS = {
    "SetHeatCoolMode",
    "SetCompressorState",
    "SetSmartGridMode",
    "SetExternalThermostat1State",
    "SetExternalThermostat2State",
    "SetDemandControl",
    "SetPoolTemp",
    "SetBufferTemp",
    "SetZ1RoomTemp",
    "SetZ1WaterTemp",
    "SetZ2RoomTemp",
    "SetZ2WaterTemp",
    "SetSolarTemp",
    "SetOptPCBByte9",
}


def test_command_names_exact_64(cat):
    """A.2: exactly 64 commands with the exact names."""
    names = {c["name"] for c in cat.commands}
    assert names == A2_COMMAND_NAMES, f"Expected {len(A2_COMMAND_NAMES)} commands, got {len(names)}: {names.symmetric_difference(A2_COMMAND_NAMES)}"


def test_pcb_commands_14(cat):
    """A.2: 14 commands have pcb=true."""
    pcb_names = {c["name"] for c in cat.commands if c["pcb"]}
    assert pcb_names == PCB_COMMANDS


# ---------------------------------------------------------------------------
# A.2 table: every row validated
# ---------------------------------------------------------------------------

# For each command, verify: class, type, readback, compare, min_firmware, ranges/allowed

A2_TABLE = {
    "SetHeatpump": {
        "class": "setting",
        "type": "bool",
        "readback": ["main/Heatpump_State"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "allowed": [0, 1],
        "risky": True,
    },
    "SetPump": {
        "class": "unverifiable",
        "type": "bool",
        "readback": [],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "allowed": [0, 1],
        "risky": False,
    },
    "SetMaxPumpDuty": {
        "class": "setting",
        "type": "int",
        "readback": ["main/Max_Pump_Duty"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": 0, "max": 100, "step": 1},
        "risky": False,
    },
    "SetQuietMode": {
        "class": "setting",
        "type": "int",
        "readback": ["main/Quiet_Mode_Level"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": 0, "max": 3, "step": 1},
        "risky": False,
    },
    "SetZ1HeatRequestTemperature": {
        "class": "setting",
        "type": "int",
        "readback": ["main/Z1_Heat_Request_Temp"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": -5, "max": 5, "step": 1},
        "risky": False,
    },
    "SetZ1CoolRequestTemperature": {
        "class": "setting",
        "type": "int",
        "readback": ["main/Z1_Cool_Request_Temp"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": -5, "max": 5, "step": 1},
        "risky": False,
    },
    "SetZ2HeatRequestTemperature": {
        "class": "setting",
        "type": "int",
        "readback": ["main/Z2_Heat_Request_Temp"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": -5, "max": 5, "step": 1},
        "risky": False,
    },
    "SetZ2CoolRequestTemperature": {
        "class": "setting",
        "type": "int",
        "readback": ["main/Z2_Cool_Request_Temp"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": -5, "max": 5, "step": 1},
        "risky": False,
    },
    "SetForceDHW": {
        "class": "setting",
        "type": "bool",
        "readback": ["main/Force_DHW_State"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "allowed": [0, 1],
        "risky": False,
    },
    "SetForceDefrost": {
        "class": "trigger",
        "type": "bool",
        "readback": [],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "allowed": [1],
        "risky": False,
    },
    "SetForceSterilization": {
        "class": "trigger",
        "type": "bool",
        "readback": [],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "allowed": [1],
        "risky": False,
    },
    "SetSterilizationTemp": {
        "class": "setting",
        "type": "int2",
        "readback": ["main/Sterilization_Temp"],
        "compare": "equal",
        "min_firmware": "4.2.3",
        "range": {"min": 55, "max": 75, "step": 1},
        "risky": False,
    },
    "SetSterilizationMaxTime": {
        "class": "setting",
        "type": "int12",
        "readback": ["main/Sterilization_Max_Time"],
        "compare": "equal",
        "min_firmware": "4.2.3",
        "range": {"min": 5, "max": 60, "step": 5},
        "risky": False,
    },
    "SetForceHeater": {
        "class": "setting",
        "type": "bool",
        "readback": ["main/Force_Heater_State"],
        "compare": "equal",
        "min_firmware": "4.2.0",
        "allowed": [0, 1],
        "risky": False,
    },
    "SetHolidayMode": {
        "class": "setting",
        "type": "bool",
        "readback": ["main/Holiday_Mode_State"],
        "compare": "holiday",
        "min_firmware": "3.2.3",
        "allowed": [0, 1],
        "risky": False,
    },
    "SetPowerfulMode": {
        "class": "setting",
        "type": "int",
        "readback": ["main/Powerful_Mode_Time"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": 0, "max": 3, "step": 1},
        "risky": False,
    },
    "SetOperationMode": {
        "class": "setting",
        "type": "int",
        "readback": ["main/Operating_Mode_State"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": 0, "max": 6, "step": 1},
        "risky": False,
    },
    "SetDHWTemp": {
        "class": "setting",
        "type": "int",
        "readback": ["main/DHW_Target_Temp"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": 40, "max": 75, "step": 1},
        "risky": False,
    },
    "SetCurves": {
        "class": "setting",
        "type": "json",
        "readback": [
            "main/Z1_Heat_Curve_Target_High_Temp", "main/Z1_Heat_Curve_Target_Low_Temp",
            "main/Z1_Heat_Curve_Outside_High_Temp", "main/Z1_Heat_Curve_Outside_Low_Temp",
            "main/Z1_Cool_Curve_Target_High_Temp", "main/Z1_Cool_Curve_Target_Low_Temp",
            "main/Z1_Cool_Curve_Outside_High_Temp", "main/Z1_Cool_Curve_Outside_Low_Temp",
            "main/Z2_Heat_Curve_Target_High_Temp", "main/Z2_Heat_Curve_Target_Low_Temp",
            "main/Z2_Heat_Curve_Outside_High_Temp", "main/Z2_Heat_Curve_Outside_Low_Temp",
            "main/Z2_Cool_Curve_Target_High_Temp", "main/Z2_Cool_Curve_Target_Low_Temp",
            "main/Z2_Cool_Curve_Outside_High_Temp", "main/Z2_Cool_Curve_Outside_Low_Temp"
        ],
        "compare": "curve_leaf",
        "min_firmware": "3.2.3",
        "risky": False,
    },
    "SetZones": {
        "class": "setting",
        "type": "int",
        "readback": ["main/Zones_State"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": 0, "max": 2, "step": 1},
        "risky": False,
    },
    "SetFloorHeatDelta": {
        "class": "setting",
        "type": "int",
        "readback": ["main/Heat_Delta"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": -10, "max": 10, "step": 1},
        "risky": False,
    },
    "SetFloorCoolDelta": {
        "class": "setting",
        "type": "int",
        "readback": ["main/Cool_Delta"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": -10, "max": 10, "step": 1},
        "risky": False,
    },
    "SetDHWHeatDelta": {
        "class": "setting",
        "type": "int",
        "readback": ["main/DHW_Heat_Delta"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": -10, "max": 10, "step": 1},
        "risky": False,
    },
    "SetReset": {
        "class": "trigger",
        "type": "bool",
        "readback": [],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "allowed": [1],
        "risky": True,
    },
    "SetHeaterDelayTime": {
        "class": "setting",
        "type": "int",
        "readback": ["main/Heater_Delay_Time"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": 0, "max": 30, "step": 1},
        "risky": False,
    },
    "SetHeaterStartDelta": {
        "class": "setting",
        "type": "int",
        "readback": ["main/Heater_Start_Delta"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": -15, "max": 15, "step": 1},
        "risky": False,
    },
    "SetHeaterStopDelta": {
        "class": "setting",
        "type": "int",
        "readback": ["main/Heater_Stop_Delta"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": -15, "max": 15, "step": 1},
        "risky": False,
    },
    "SetMainSchedule": {
        "class": "setting",
        "type": "bool",
        "readback": ["main/Main_Schedule_State"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "allowed": [0, 1],
        "risky": False,
    },
    "SetAltExternalSensor": {
        "class": "setting",
        "type": "bool",
        "readback": ["main/Alt_External_Sensor"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "allowed": [0, 1],
        "risky": False,
    },
    "SetExternalPadHeater": {
        "class": "setting",
        "type": "int",
        "readback": ["main/External_Pad_Heater"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": 0, "max": 2, "step": 1},
        "risky": False,
    },
    "SetBufferDelta": {
        "class": "setting",
        "type": "int",
        "readback": ["main/Buffer_Tank_Delta"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": -10, "max": 10, "step": 1},
        "risky": False,
    },
    "SetBuffer": {
        "class": "setting",
        "type": "bool",
        "readback": ["main/Buffer_Installed"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "allowed": [0, 1],
        "risky": False,
    },
    "SetHeatingOffOutdoorTemp": {
        "class": "setting",
        "type": "int",
        "readback": ["main/Heating_Off_Outdoor_Temp"],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": 5, "max": 35, "step": 1},
        "risky": False,
    },
    "SetExternalControl": {
        "class": "setting",
        "type": "bool",
        "readback": ["main/External_Control"],
        "compare": "equal",
        "min_firmware": "3.9",
        "allowed": [0, 1],
        "risky": False,
    },
    "SetExternalError": {
        "class": "setting",
        "type": "bool",
        "readback": ["main/External_Error_Signal"],
        "compare": "equal",
        "min_firmware": "3.9",
        "allowed": [0, 1],
        "risky": False,
    },
    "SetExternalCompressorControl": {
        "class": "setting",
        "type": "bool",
        "readback": ["main/External_Compressor_Control"],
        "compare": "equal",
        "min_firmware": "3.9",
        "allowed": [0, 1],
        "risky": False,
    },
    "SetExternalHeatCoolControl": {
        "class": "setting",
        "type": "bool",
        "readback": ["main/External_Heat_Cool_Control"],
        "compare": "equal",
        "min_firmware": "3.9",
        "allowed": [0, 1],
        "risky": False,
    },
    "SetBivalentControl": {
        "class": "setting",
        "type": "bool",
        "readback": ["main/Bivalent_Control"],
        "compare": "equal",
        "min_firmware": "3.9",
        "allowed": [0, 1],
        "risky": False,
    },
    "SetBivalentMode": {
        "class": "setting",
        "type": "int",
        "readback": ["main/Bivalent_Mode"],
        "compare": "equal",
        "min_firmware": "3.9",
        "range": {"min": 0, "max": 2, "step": 1},
        "risky": False,
    },
    "SetBivalentStartTemp": {
        "class": "setting",
        "type": "int",
        "readback": ["main/Bivalent_Start_Temp"],
        "compare": "equal",
        "min_firmware": "3.9",
        "range": {"min": -20, "max": 30, "step": 1},
        "risky": False,
    },
    "SetBivalentAPStartTemp": {
        "class": "setting",
        "type": "int",
        "readback": ["main/Bivalent_Advanced_Start_Temp"],
        "compare": "equal",
        "min_firmware": "3.9",
        "range": {"min": -20, "max": 30, "step": 1},
        "risky": False,
    },
    "SetBivalentAPStopTemp": {
        "class": "setting",
        "type": "int",
        "readback": ["main/Bivalent_Advanced_Stop_Temp"],
        "compare": "equal",
        "min_firmware": "3.9",
        "range": {"min": -20, "max": 30, "step": 1},
        "risky": False,
    },
    "SetHeatingControl": {
        "class": "setting",
        "type": "bool",
        "readback": ["main/Heating_Control"],
        "compare": "equal",
        "min_firmware": "4.0",
        "allowed": [0, 1],
        "risky": False,
    },
    "SetSmartDHW": {
        "class": "setting",
        "type": "bool",
        "readback": ["main/Smart_DHW"],
        "compare": "equal",
        "min_firmware": "4.0",
        "allowed": [0, 1],
        "risky": False,
    },
    "SetQuietModePriority": {
        "class": "setting",
        "type": "bool",
        "readback": ["main/Quiet_Mode_Priority"],
        "compare": "equal",
        "min_firmware": "4.0",
        "allowed": [0, 1],
        "risky": False,
    },
    "SetPumpFlowrateMode": {
        "class": "setting",
        "type": "bool",
        "readback": ["main/Pump_Flowrate_Mode"],
        "compare": "equal",
        "min_firmware": "4.0",
        "allowed": [0, 1],
        "risky": False,
    },
    "SetDHWSensorSelection": {
        "class": "setting",
        "type": "bool",
        "readback": ["main/DHW_Sensor_Selection"],
        "compare": "equal",
        "min_firmware": "4.1.2",
        "allowed": [0, 1],
        "risky": False,
    },
    "SetDHWHeaterState": {
        "class": "setting",
        "type": "bool",
        "readback": ["main/DHW_Heater_State"],
        "compare": "equal",
        "min_firmware": "4.1.2",
        "allowed": [0, 1],
        "risky": False,
    },
    "SetRoomHeaterState": {
        "class": "setting",
        "type": "bool",
        "readback": ["main/Room_Heater_State"],
        "compare": "equal",
        "min_firmware": "4.1.2",
        "allowed": [0, 1],
        "risky": False,
    },
    "SetHeaterOnOutdoorTemp": {
        "class": "setting",
        "type": "int",
        "readback": ["main/Heater_On_Outdoor_Temp"],
        "compare": "equal",
        "min_firmware": "4.1.2",
        "range": {"min": -15, "max": 20, "step": 1},
        "risky": False,
    },
    # PCB commands
    "SetHeatCoolMode": {
        "class": "unverifiable",
        "type": "bool",
        "readback": [],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "allowed": [0, 1],
        "risky": False,
    },
    "SetCompressorState": {
        "class": "unverifiable",
        "type": "bool",
        "readback": [],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "allowed": [0, 1],
        "risky": False,
    },
    "SetSmartGridMode": {
        "class": "unverifiable",
        "type": "int",
        "readback": [],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": 0, "max": 3, "step": 1},
        "risky": False,
    },
    "SetExternalThermostat1State": {
        "class": "unverifiable",
        "type": "int",
        "readback": [],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": 0, "max": 3, "step": 1},
        "risky": False,
    },
    "SetExternalThermostat2State": {
        "class": "unverifiable",
        "type": "int",
        "readback": [],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": 0, "max": 3, "step": 1},
        "risky": False,
    },
    "SetDemandControl": {
        "class": "unverifiable",
        "type": "int",
        "readback": [],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": 0, "max": 255, "step": 1},
        "risky": False,
    },
    "SetPoolTemp": {
        "class": "unverifiable",
        "type": "dec1",
        "readback": [],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": -30.0, "max": 90.0, "step": 0.5},
        "risky": True,
    },
    "SetBufferTemp": {
        "class": "unverifiable",
        "type": "dec1",
        "readback": [],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": -30.0, "max": 90.0, "step": 0.5},
        "risky": True,
    },
    "SetZ1RoomTemp": {
        "class": "unverifiable",
        "type": "dec1",
        "readback": [],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": -30.0, "max": 90.0, "step": 0.5},
        "risky": True,
    },
    "SetZ1WaterTemp": {
        "class": "unverifiable",
        "type": "dec1",
        "readback": [],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": -30.0, "max": 90.0, "step": 0.5},
        "risky": True,
    },
    "SetZ2RoomTemp": {
        "class": "unverifiable",
        "type": "dec1",
        "readback": [],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": -30.0, "max": 90.0, "step": 0.5},
        "risky": True,
    },
    "SetZ2WaterTemp": {
        "class": "unverifiable",
        "type": "dec1",
        "readback": [],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": -30.0, "max": 90.0, "step": 0.5},
        "risky": True,
    },
    "SetSolarTemp": {
        "class": "unverifiable",
        "type": "dec1",
        "readback": [],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": -30.0, "max": 90.0, "step": 0.5},
        "risky": True,
    },
    "SetOptPCBByte9": {
        "class": "unverifiable",
        "type": "int",
        "readback": [],
        "compare": "equal",
        "min_firmware": "3.2.3",
        "range": {"min": 0, "max": 255, "step": 1},
        "risky": True,
    },
}


def get_range_or_allowed(cmd):
    """Extract range or allowed from command entry."""
    if "range" in cmd:
        return {"range": cmd["range"]}
    elif "allowed" in cmd:
        return {"allowed": cmd["allowed"]}
    return None


@pytest.mark.parametrize("name", A2_COMMAND_NAMES)
def test_a2_row(name, cat):
    """For every A.2 row, verify all fields match."""
    cmd = cat.command(name)
    assert cmd is not None, f"Command {name} not found"

    spec = A2_TABLE[name]

    # Check required fields
    assert cmd["class"] == spec["class"], f"{name}: class mismatch"
    assert cmd["type"] == spec["type"], f"{name}: type mismatch"
    assert cmd["readback"] == spec["readback"], f"{name}: readback mismatch"
    assert cmd["compare"] == spec["compare"], f"{name}: compare mismatch"
    assert cmd["min_firmware"] == spec["min_firmware"], f"{name}: min_firmware mismatch"
    assert cmd["risky"] == spec["risky"], f"{name}: risky mismatch"

    # Check range/allowed
    range_or_allowed = get_range_or_allowed(cmd)
    spec_range_or_allowed = get_range_or_allowed(spec)
    assert range_or_allowed == spec_range_or_allowed, f"{name}: range/allowed mismatch"


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

# Input paths from A.2
INPUT_PATHS = {
    # S0 (retain=true)
    "s0/WatthourTotal/1",
    "s0/WatthourTotal/2",
    # OpenTherm bounds (retain=true, from v3.5)
    "opentherm/read/dhwSetUppBound",
    "opentherm/read/dhwSetLowBound",
    "opentherm/read/chSetUppBound",
    "opentherm/read/chSetLowBound",
    # OpenTherm non-bounds (retain=false, from v3.5)
    "opentherm/read/dhwSetpoint",
    "opentherm/read/maxTSet",
    "opentherm/read/outsideTemp",
    "opentherm/read/inletTemp",
    "opentherm/read/outletTemp",
    "opentherm/read/dhwTemp",
    "opentherm/read/roomSetOverride",
    "opentherm/read/chPressure",
    "opentherm/read/relativeModulation",
    # bool inputs
    "opentherm/read/flameState",
    "opentherm/read/chState",
    "opentherm/read/dhwState",
    "opentherm/read/coolingState",
}

# 6 retained inputs: 2 S0 + 4 bounds
RETAINED_INPUTS = {
    "s0/WatthourTotal/1",
    "s0/WatthourTotal/2",
    "opentherm/read/dhwSetUppBound",
    "opentherm/read/dhwSetLowBound",
    "opentherm/read/chSetUppBound",
    "opentherm/read/chSetLowBound",
}


def test_inputs_paths(cat):
    """The inputs equal the A.2 inputs table."""
    paths = {i["path"] for i in cat.inputs}
    assert paths == INPUT_PATHS, f"Input paths mismatch: {paths.symmetric_difference(INPUT_PATHS)}"


def test_inputs_retain(cat):
    """retain true only for the 2 S0 paths and the 4 bounds."""
    retained = {i["path"] for i in cat.inputs if i["retain"]}
    assert retained == RETAINED_INPUTS


# ---------------------------------------------------------------------------
# Readback topics
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", A2_COMMAND_NAMES)
def test_readback_topics_exist(name, cat):
    """Every readback topic exists in topics."""
    cmd = cat.command(name)
    for rb in cmd.get("readback", []):
        assert cat.topic(rb) is not None, f"Readback topic {rb} for command {name} not found"


# ---------------------------------------------------------------------------
# Enum value sets (A.4)
# ---------------------------------------------------------------------------

# A.4 enum decodings
A4_ENUMS = {
    "main/Operating_Mode_State": [0, 1, 2, 3, 4, 5, 6, 7, 8, -1],
    "main/Heating_Mode": [0, 1, -1, 2],
    "main/Cooling_Mode": [0, 1, -1, 2],
    "main/Zones_State": [0, 1, 2, -1],
    "main/Z1_Sensor_Settings": [0, 1, 2, 3],
    "main/Z2_Sensor_Settings": [0, 1, 2, 3],
    "main/ThreeWay_Valve_State": [0, 1, -1, 2],
    "main/Defrosting_State": [0, 1, -1, 2],
    "main/Buffer_Installed": [0, 1, -1],
    "main/DHW_Installed": [0, 1, -1],
    "main/Optional_PCB": [0, 1, -1],
    "main/Bivalent_Control": [0, 1, -1],
    "main/Solar_Mode": [0, 1, 2, -1],
    "main/Liquid_Type": [0, 1, -1],
}


@pytest.mark.parametrize("topic_key", A4_ENUMS)
def test_enum_labels_exist(topic_key, cat):
    """Every enum topic has EN and NL labels for every value in A.4."""
    topic = cat.topic(topic_key)
    assert topic is not None, f"Topic {topic_key} not found"
    assert topic["kind"] == "enum", f"Topic {topic_key} is not enum"
    assert "enum" in topic, f"Topic {topic_key} has no enum"

    enum_values = A4_ENUMS[topic_key]
    for val in enum_values:
        val_str = str(val)
        assert val_str in topic["enum"], f"Topic {topic_key} missing enum value {val_str}"
        labels = topic["enum"][val_str]
        assert "en" in labels, f"Topic {topic_key} value {val_str} missing EN label"
        assert "nl" in labels, f"Topic {topic_key} value {val_str} missing NL label"


def test_operating_mode_state_encoding(cat):
    """Operating_Mode_State 0-8 encoded exactly."""
    topic = cat.topic("main/Operating_Mode_State")
    enum_map = topic["enum"]
    for i in range(9):
        assert str(i) in enum_map, f"Operating_Mode_State missing value {i}"


# ---------------------------------------------------------------------------
# range_source and risky
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", A2_COMMAND_NAMES)
def test_range_source_exists(name, cat):
    """Every entry has a range_source."""
    cmd = cat.command(name)
    assert "range_source" in cmd, f"Command {name} missing range_source"


@pytest.mark.parametrize("name", A2_COMMAND_NAMES)
def test_encoding_domain_risky(name, cat):
    """encoding_domain entries have risky: true."""
    cmd = cat.command(name)
    if cmd["range_source"] == "encoding_domain":
        # Only these PCB commands with encoding_domain should be risky
        assert cmd["risky"] == True, f"Command {name} with encoding_domain should be risky"


# ---------------------------------------------------------------------------
# TOP115-143 min_firmware (A.1)
# ---------------------------------------------------------------------------

# TOP115-118: v3.5
TOP115_118 = {"main/Water_Pressure", "main/Second_Inlet_Temp", "main/Economizer_Outlet_Temp", "main/Second_Room_Thermostat_Temp"}

# TOP119-138: v3.9
TOP119_138 = {
    "main/External_Control", "main/External_Heat_Cool_Control", "main/External_Error_Signal",
    "main/External_Compressor_Control", "main/Z2_Pump_State", "main/Z1_Pump_State",
    "main/TwoWay_Valve_State", "main/ThreeWay_Valve_State2", "main/Z1_Valve_PID",
    "main/Z2_Valve_PID", "main/Bivalent_Control", "main/Bivalent_Mode",
    "main/Bivalent_Start_Temp", "main/Bivalent_Advanced_Heat", "main/Bivalent_Advanced_DHW",
    "main/Bivalent_Advanced_Start_Temp", "main/Bivalent_Advanced_Stop_Temp",
    "main/Bivalent_Advanced_Start_Delay", "main/Bivalent_Advanced_Stop_Delay",
    "main/Bivalent_Advanced_DHW_Delay",
}

# TOP139-142: v4.0
TOP139_142 = {
    "main/Heating_Control", "main/Smart_DHW", "main/Quiet_Mode_Priority",
    "main/Expansion_Valve",
}

# TOP143: v4.1.2
TOP143 = {"main/DHW_Sensor_Selection"}


@pytest.mark.parametrize("key", TOP115_118)
def test_top115_118_min_firmware(key, cat):
    """TOP115-118 carry min_firmware 3.5."""
    topic = cat.topic(key)
    assert topic is not None
    assert topic["min_firmware"] == "3.5"


@pytest.mark.parametrize("key", TOP119_138)
def test_top119_138_min_firmware(key, cat):
    """TOP119-138 carry min_firmware 3.9."""
    topic = cat.topic(key)
    assert topic is not None
    assert topic["min_firmware"] == "3.9"


@pytest.mark.parametrize("key", TOP139_142)
def test_top139_142_min_firmware(key, cat):
    """TOP139-142 carry min_firmware 4.0."""
    topic = cat.topic(key)
    assert topic is not None
    assert topic["min_firmware"] == "4.0"


@pytest.mark.parametrize("key", TOP143)
def test_top143_min_firmware(key, cat):
    """TOP143 carries min_firmware 4.1.2."""
    topic = cat.topic(key)
    assert topic is not None
    assert topic["min_firmware"] == "4.1.2"


# ---------------------------------------------------------------------------
# Topic count
# ---------------------------------------------------------------------------


def test_topic_count(cat):
    """All TOP0-143, XTOP0-5 and OPT0-6 topics present."""
    # TOP0-143 = 144 topics
    # XTOP0-5 = 6 topics
    # OPT0-6 = 7 topics
    # Total = 157 topics
    assert len(cat.topics) == 157


# ---------------------------------------------------------------------------
# Models empty
# ---------------------------------------------------------------------------


def test_models_empty(cat):
    """models: [] (empty is valid per A.3)."""
    assert len(cat.models) == 0


# ---------------------------------------------------------------------------
# Topic ids (upstream index), Dutch labels, enum meanings (A.4)
# ---------------------------------------------------------------------------

import re  # noqa: E402


def test_topic_ids_upstream_index(cat):
    ids = [t["id"] for t in cat.topics]
    assert all(re.fullmatch(r"(TOP|XTOP|OPT)\d+", i) for i in ids)
    assert len(set(ids)) == len(ids) == 157
    by_key = {t["key"]: t["id"] for t in cat.topics}
    assert by_key["main/Heatpump_State"] == "TOP0"
    assert by_key["main/Outside_Temp"] == "TOP14"
    assert by_key["main/Heat_Pump_Model"] == "TOP92"
    assert by_key["extra/Heat_Power_Consumption_Extra"] == "XTOP0"
    assert by_key["optional/Alarm_State"] == "OPT6"
    assert {i for i in ids if i.startswith("TOP")} == {f"TOP{n}" for n in range(144)}
    assert {i for i in ids if i.startswith("XTOP")} == {f"XTOP{n}" for n in range(6)}
    assert {i for i in ids if i.startswith("OPT")} == {f"OPT{n}" for n in range(7)}


def test_dutch_labels_are_translated(cat):
    entries = list(cat.topics) + list(cat.commands) + list(cat.inputs)
    assert len(entries) == 157 + 64 + 19
    same = [e for e in entries if e["label"]["nl"] == e["label"]["en"]]
    assert len(same) <= 0.10 * len(entries), [e.get("key") or e.get("name") or e.get("path") for e in same]
    assert all(e["label"]["nl"].strip() for e in entries)


A4_MEANINGS = {
    "main/Operating_Mode_State": {
        0: "Heating", 1: "Cooling", 2: "Auto (heating)", 3: "DHW only", 4: "Heating + DHW",
        5: "Cooling + DHW", 6: "Auto (heating) + DHW", 7: "Auto (cooling)", 8: "Auto (cooling) + DHW"},
    "main/Heating_Mode": {0: "Curve", 1: "Direct"},
    "main/Cooling_Mode": {0: "Curve", 1: "Direct"},
    "main/Zones_State": {0: "Zone 1", 1: "Zone 2", 2: "Zone 1 and 2"},
    "main/Z1_Sensor_Settings": {0: "Water temperature", 1: "External thermostat",
                                2: "Internal thermostat", 3: "Thermistor"},
    "main/Z2_Sensor_Settings": {0: "Water temperature", 1: "External thermostat",
                                2: "Internal thermostat", 3: "Thermistor"},
    "main/ThreeWay_Valve_State": {0: "Room / heating circuit", 1: "DHW"},
    "main/Defrosting_State": {0: "Not defrosting", 1: "Defrosting"},
    "main/Buffer_Installed": {0: "No", 1: "Yes"},
    "main/DHW_Installed": {0: "No", 1: "Yes"},
    "main/Optional_PCB": {0: "No", 1: "Yes"},
    "main/Bivalent_Control": {0: "No", 1: "Yes"},
    "main/Solar_Mode": {0: "Off", 1: "Buffer", 2: "DHW"},
    "main/Liquid_Type": {0: "Water", 1: "Glycol"},
}


@pytest.mark.parametrize("topic_key", A4_MEANINGS)
def test_enum_meanings_match_a4(topic_key, cat):
    enum = cat.topic(topic_key)["enum"]
    for v, en in A4_MEANINGS[topic_key].items():
        assert enum[str(v)]["en"] == en
        assert enum[str(v)]["nl"] != "" and not enum[str(v)]["nl"].startswith("Waarde")
    for v, lab in enum.items():
        if int(v) not in A4_MEANINGS[topic_key]:
            assert lab["en"] == "Unknown"


# ---------------------------------------------------------------------------
# Conditional ranges and applicability (A.2, A.3)
# ---------------------------------------------------------------------------

ROOM_SENSORS = ("ext_thermostat", "int_thermostat", "thermistor")


def _cmd(name):
    data = json.loads(CATALOG_PATH.read_text())
    return next(c for c in data["commands"] if c["name"] == name)


@pytest.mark.parametrize("zone", ["1", "2"])
@pytest.mark.parametrize("kind,ctl,water,room", [
    ("Heat", "profile.heating_control", (20, 65), (10, 30)),
    ("Cool", "profile.cooling_control", (5, 20), (18, 30)),
])
def test_request_temperature_conditional_ranges(zone, kind, ctl, water, room):
    cmd = _cmd(f"SetZ{zone}{kind}RequestTemperature")
    sensor = f"profile.zone.z{zone}.sensor"
    got = [({k: v for k, v in r["when"].items()}, r["min"], r["max"], r["step"])
           for r in cmd["conditional_ranges"]]
    expected = [({ctl: "curve"}, -5, 5, 1), ({ctl: "direct", sensor: "water"}, *water, 1)]
    expected += [({ctl: "direct", sensor: s}, *room, 1) for s in ROOM_SENSORS]
    assert got == expected


@pytest.mark.parametrize("name,path", [
    *[(n, "profile.dhw_installed") for n in (
        "SetDHWTemp", "SetForceDHW", "SetSterilizationTemp", "SetSterilizationMaxTime",
        "SetForceSterilization", "SetDHWHeatDelta", "SetDHWHeaterState",
        "SetDHWSensorSelection", "SetSmartDHW")],
    ("SetZ2HeatRequestTemperature", "profile.zone.z2.active"),
    ("SetZ2CoolRequestTemperature", "profile.zone.z2.active"),
    ("SetBufferDelta", "profile.buffer_installed"),
    ("SetBivalentMode", "profile.bivalent"),
])
def test_applicability_requirements(name, path):
    cmd = _cmd(name)
    assert cmd["applicability"] == {"requires": [path]}
    assert cmd["safe_under_unknown"] is False


def test_catalog_still_loads_with_new_fields(cat):
    assert len(cat.commands) == 64
