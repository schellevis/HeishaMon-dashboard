import { describe, expect, it } from 'vitest';
import { activityFrom } from '../src/lib/domain/activity.js';
import { activityOf } from '../src/lib/format.js';
import { modeSets } from '../src/lib/domain/rules.js';

const heatMode = modeSets.heating[0];
const coolMode = modeSets.cooling.find((m) => !modeSets.heating.includes(m));

describe('activityFrom', () => {
  it('defrost wins over everything', () => {
    expect(activityFrom({ defrost: 1, valve: 1, heatpump: 1, mode: heatMode })).toBe('defrost');
  });
  it('valve on DHW means dhw', () => {
    expect(activityFrom({ defrost: 0, valve: 1, heatpump: 1, mode: heatMode })).toBe('dhw');
  });
  it('heat pump off means idle', () => {
    expect(activityFrom({ defrost: 0, valve: 0, heatpump: 0, mode: heatMode })).toBe('idle');
  });
  it('falls back to the mode', () => {
    expect(activityFrom({ defrost: 0, valve: 0, heatpump: 1, mode: heatMode })).toBe('heating');
    expect(activityFrom({ defrost: 0, valve: 0, heatpump: 1, mode: coolMode })).toBe('cooling');
    expect(activityFrom({ defrost: null, valve: null, heatpump: null, mode: null })).toBe('idle');
  });
  it('treats rollup averages with a 0.5 threshold', () => {
    expect(activityFrom({ defrost: 0.6, valve: 0, heatpump: 1, mode: heatMode })).toBe('defrost');
    expect(activityFrom({ defrost: 0.4, valve: 0.2, heatpump: 0.9, mode: heatMode + 0.2 })).toBe('heating');
  });
  it('strict mode returns unknown when a needed input is missing', () => {
    const strict = { strict: true };
    expect(activityFrom({ defrost: null, valve: 0, heatpump: 1, mode: heatMode }, strict)).toBe('unknown');
    expect(activityFrom({ defrost: 0, valve: null, heatpump: 1, mode: heatMode }, strict)).toBe('unknown');
    expect(activityFrom({ defrost: 0, valve: 0, heatpump: null, mode: heatMode }, strict)).toBe('unknown');
    expect(activityFrom({ defrost: 0, valve: 0, heatpump: 1, mode: null }, strict)).toBe('unknown');
    expect(activityFrom({ defrost: 0, valve: 0, heatpump: 1, mode: 99 }, strict)).toBe('unknown');
    expect(activityFrom({ defrost: 1, valve: null, heatpump: null, mode: null }, strict)).toBe('defrost');
    expect(activityFrom({ defrost: 0, valve: 0, heatpump: 0, mode: null }, strict)).toBe('idle');
    expect(activityFrom({ defrost: 0, valve: 0, heatpump: 1, mode: heatMode }, strict)).toBe('heating');
  });
  it('activityOf still agrees for a live state', () => {
    const t = (value) => ({ value, sentinel: false });
    const state = { topics: { 'main/Defrosting_State': t(0), 'main/ThreeWay_Valve_State': t(1), 'main/Heatpump_State': t(1) } };
    expect(activityOf(state, null)).toBe('dhw');
  });
});
