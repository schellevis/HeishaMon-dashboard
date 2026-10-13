import { describe, expect, it } from 'vitest';
import productionCatalog from '../../backend/heishamon_dashboard/catalog.json';
import { entryId, groupCatalog } from '../src/features/settings/grouping.js';

// Group -> ordered command/input ids, captured from the pre-ui_group name heuristics (R2).
const EXPECTED = {
  "operation": [
    "SetHeatpump",
    "SetForceDefrost",
    "SetHolidayMode",
    "SetPowerfulMode",
    "SetOperationMode",
    "SetCurves",
    "SetReset",
    "SetAltExternalSensor",
    "SetBufferDelta",
    "SetBuffer",
    "SetHeatingOffOutdoorTemp",
    "SetExternalControl",
    "SetExternalError",
    "SetExternalCompressorControl",
    "SetExternalHeatCoolControl",
    "SetHeatingControl"
  ],
  "zones": [
    "SetZ1HeatRequestTemperature",
    "SetZ1CoolRequestTemperature",
    "SetZ2HeatRequestTemperature",
    "SetZ2CoolRequestTemperature",
    "SetZones",
    "SetFloorHeatDelta",
    "SetFloorCoolDelta"
  ],
  "dhw": [
    "SetForceDHW",
    "SetDHWTemp",
    "SetDHWHeatDelta",
    "SetSmartDHW",
    "SetDHWSensorSelection",
    "SetDHWHeaterState"
  ],
  "sterilization": [
    "SetForceSterilization",
    "SetSterilizationTemp",
    "SetSterilizationMaxTime"
  ],
  "heaters": [
    "SetForceHeater",
    "SetHeaterDelayTime",
    "SetHeaterStartDelta",
    "SetHeaterStopDelta",
    "SetExternalPadHeater",
    "SetRoomHeaterState",
    "SetHeaterOnOutdoorTemp"
  ],
  "bivalent": [
    "SetBivalentControl",
    "SetBivalentMode",
    "SetBivalentStartTemp",
    "SetBivalentAPStartTemp",
    "SetBivalentAPStopTemp"
  ],
  "solar": [],
  "pump": [
    "SetPump",
    "SetMaxPumpDuty",
    "SetPumpFlowrateMode"
  ],
  "quiet": [
    "SetQuietMode",
    "SetMainSchedule",
    "SetQuietModePriority"
  ],
  "opentherm": [
    "opentherm/read/chPressure",
    "opentherm/read/chSetLowBound",
    "opentherm/read/chSetUppBound",
    "opentherm/read/chState",
    "opentherm/read/coolingState",
    "opentherm/read/dhwSetLowBound",
    "opentherm/read/dhwSetUppBound",
    "opentherm/read/dhwSetpoint",
    "opentherm/read/dhwState",
    "opentherm/read/dhwTemp",
    "opentherm/read/flameState",
    "opentherm/read/inletTemp",
    "opentherm/read/maxTSet",
    "opentherm/read/outletTemp",
    "opentherm/read/outsideTemp",
    "opentherm/read/relativeModulation"
  ],
  "s0": [
    "s0/WatthourTotal/1",
    "s0/WatthourTotal/2"
  ],
  "pcb": [
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
    "SetOptPCBByte9"
  ]
};

describe('settings grouping snapshot', () => {
  it('places every command and input in the same group and order as before', () => {
    const actual = {};
    for (const group of groupCatalog(productionCatalog)) actual[group.id] = group.items.map(entryId);
    expect(actual).toEqual(EXPECTED);
  });
});
