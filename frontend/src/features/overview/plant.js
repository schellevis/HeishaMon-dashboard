/** What the plant schematic shows, derived from live state and the installation profile only. */
import { activityOf } from '../../lib/format.js';

const known = (field) => (field && !field.unknown ? field.value : undefined);

function num(state, key) {
  const topic = state?.topics?.[key];
  return topic && !topic.sentinel && typeof topic.value === 'number' ? topic.value : null;
}

export function plantModel(state, profile) {
  const zonesValue = known(profile?.zones);
  const zoneIds = zonesValue === 'both' ? ['z1', 'z2'] : zonesValue === 'z2' ? ['z2'] : ['z1'];
  const hasDhw = known(profile?.dhw_installed) !== false;
  const hasBuffer = known(profile?.buffer_installed) === true;
  const activity = activityOf(state, profile);
  const flow = num(state, 'main/Main_Outlet_Temp');
  const ret = num(state, 'main/Main_Inlet_Temp');
  const pumpFlow = num(state, 'main/Pump_Flow');
  const flowing = pumpFlow !== null && pumpFlow > 0;
  const compressor = num(state, 'main/Compressor_Freq');
  const heatingUse = known(profile?.heating_in_use);
  const coolingOnly = heatingUse === false && known(profile?.cooling_in_use) === true;
  // the qualifier names the control of what runs now: cooling while cooling, else heating
  const coolingNow = activity === 'cooling' || coolingOnly;
  return {
    activity,
    outside: num(state, 'main/Outside_Temp'),
    compressor,
    flow,
    ret,
    target: num(state, 'main/Main_Target_Temp'),
    deltaT: flow !== null && ret !== null ? flow - ret : null,
    pumpFlow,
    flowing,
    // seconds per dash cycle: faster with more flow, within a calm range
    flowPeriod: flowing ? Math.min(4, Math.max(0.4, 18 / pumpFlow)) : null,
    fanSpinning: compressor !== null && compressor > 0 && activity !== 'defrost',
    valve: hasDhw && num(state, 'main/ThreeWay_Valve_State') === 1 ? 'dhw' : 'room',
    zones: zoneIds.map((id) => ({ id, water: num(state, `main/${id.toUpperCase()}_Water_Temp`) })),
    dhw: hasDhw ? { temp: num(state, 'main/DHW_Temp'), target: num(state, 'main/DHW_Target_Temp') } : null,
    buffer: hasBuffer ? { temp: num(state, 'main/Buffer_Temp') } : null,
    controlMode: known(coolingNow ? profile?.cooling_control : profile?.heating_control) ?? null,
  };
}

/** Pipe paths and equipment boxes in the viewBox `0 40 960 345` (valve at 600,110; indoor unit right edge x=500). */
export function plantGeometry(model) {
  const two = model.zones.length === 2;
  const emitters = two
    ? [
        { id: model.zones[0].id, x: 730, y: 130, w: 80, h: 80 },
        { id: model.zones[1].id, x: 850, y: 130, w: 80, h: 80 },
      ]
    : [{ id: model.zones[0].id, x: 840, y: 130, w: 80, h: 80 }];
  for (const e of emitters) {
    e.inX = e.x + 20;
    e.outX = e.x + e.w - 20;
  }
  const last = emitters[emitters.length - 1];
  const zoneFlow = [`M600 110 H${last.inX} V130`, ...emitters.slice(0, -1).map((e) => `M${e.inX} 110 V130`)].join(' ');
  const zoneReturn = [`M${last.outX} 210 V230 H500`, ...emitters.slice(0, -1).map((e) => `M${e.outX} 210 V230`)].join(' ');
  return {
    emitters,
    zoneFlow,
    zoneReturn,
    dhwFlow: model.dhw ? 'M600 110 V290 H780' : null,
    dhwReturn: model.dhw ? 'M780 350 H500' : null,
    buffer: model.buffer ? { x: 640, y: 92, w: 60, h: 36 } : null,
  };
}
