import { describe, expect, it } from 'vitest';
import { plantGeometry, plantModel } from '../src/features/overview/plant.js';

const F = (value, unknown = false) => ({ value, unknown, stale: false });
const T = (value, sentinel = false) => ({ value, sentinel });
const baseProfile = { zones: F('z1'), dhw_installed: F(true), buffer_installed: F(false), operating_mode: F(4), heating_control: F('curve') };
const state = (topics) => ({ topics });

describe('plantModel', () => {
  it('reads the live values and derives ΔT and flow', () => {
    const m = plantModel(state({
      'main/Outside_Temp': T(6.3), 'main/Compressor_Freq': T(34), 'main/Main_Outlet_Temp': T(35.2),
      'main/Main_Inlet_Temp': T(30.4), 'main/Main_Target_Temp': T(35), 'main/Pump_Flow': T(14.8),
      'main/ThreeWay_Valve_State': T(0), 'main/Heatpump_State': T(1), 'main/Defrosting_State': T(0),
      'main/DHW_Temp': T(48.6), 'main/DHW_Target_Temp': T(52),
    }), baseProfile);
    expect(m.deltaT).toBeCloseTo(4.8);
    expect(m.flowing).toBe(true);
    expect(m.flowPeriod).toBeCloseTo(18 / 14.8);
    expect(m.fanSpinning).toBe(true);
    expect(m.valve).toBe('room');
    expect(m.dhw).toEqual({ temp: 48.6, target: 52 });
    expect(m.zones).toEqual([{ id: 'z1', water: null }]);
    expect(m.controlMode).toBe('curve');
  });
  it('treats sentinels as missing', () => {
    const m = plantModel(state({ 'main/Outside_Temp': T(-128, true), 'main/Pump_Flow': T(0) }), baseProfile);
    expect(m.outside).toBe(null);
    expect(m.flowing).toBe(false);
    expect(m.flowPeriod).toBe(null);
  });
  it('follows the profile: no tank, two zones, buffer', () => {
    const m = plantModel(state({}), { ...baseProfile, zones: F('both'), dhw_installed: F(false), buffer_installed: F(true) });
    expect(m.dhw).toBe(null);
    expect(m.zones.map((z) => z.id)).toEqual(['z1', 'z2']);
    expect(m.buffer).toEqual({ temp: null });
  });
  it('shows the tank and zone 1 when the profile is unknown', () => {
    const m = plantModel(state({}), { zones: F(null, true), dhw_installed: F(null, true) });
    expect(m.dhw).not.toBe(null);
    expect(m.zones.map((z) => z.id)).toEqual(['z1']);
  });
  it('ignores the DHW valve position when there is no tank', () => {
    const m = plantModel(state({ 'main/ThreeWay_Valve_State': T(1) }), { ...baseProfile, dhw_installed: F(false) });
    expect(m.valve).toBe('room');
  });
  it('names the cooling control while cooling', () => {
    const m = plantModel(state({ 'main/Heatpump_State': T(1), 'main/Defrosting_State': T(0), 'main/ThreeWay_Valve_State': T(0) }),
      { ...baseProfile, operating_mode: F(1), heating_control: F('curve'), cooling_control: F('direct') });
    expect(m.activity).toBe('cooling');
    expect(m.controlMode).toBe('direct');
  });
  it('stops the fan during defrost', () => {
    const m = plantModel(state({ 'main/Compressor_Freq': T(70), 'main/Defrosting_State': T(1) }), baseProfile);
    expect(m.activity).toBe('defrost');
    expect(m.fanSpinning).toBe(false);
  });
});

describe('plantGeometry', () => {
  it('draws one emitter per zone without overlap', () => {
    const one = plantGeometry(plantModel(state({}), baseProfile));
    expect(one.emitters).toHaveLength(1);
    const two = plantGeometry(plantModel(state({}), { ...baseProfile, zones: F('both') }));
    expect(two.emitters).toHaveLength(2);
    const [a, b] = two.emitters;
    expect(a.x + a.w).toBeLessThan(b.x);
  });
  it('omits the DHW pipes without a tank', () => {
    const g = plantGeometry(plantModel(state({}), { ...baseProfile, dhw_installed: F(false) }));
    expect(g.dhwFlow).toBe(null);
    expect(g.dhwReturn).toBe(null);
  });
});
