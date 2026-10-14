import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import CurveChart from '../src/features/curve/CurveChart.svelte';
import { activeCurve, miniView } from '../src/features/overview/MiniCurve.svelte';

const F = (value, unknown = false) => ({ value, unknown, stale: false });
const curveValues = (z = 'Z1', m = 'Heat') => ({
  [`main/${z}_${m}_Curve_Target_High_Temp`]: 45, [`main/${z}_${m}_Curve_Target_Low_Temp`]: 28,
  [`main/${z}_${m}_Curve_Outside_Low_Temp`]: -10, [`main/${z}_${m}_Curve_Outside_High_Temp`]: 16,
});
const base = { zones: F('z1'), heating_in_use: F(true), cooling_in_use: F(false), heating_control: F('curve'),
  zone: { z1: { sensor: F('water') }, z2: { sensor: F('water') } } };

describe('activeCurve', () => {
  it('picks zone 1 heating by default, also with two zones and during DHW', () => {
    expect(activeCurve({ ...base, zones: F('both') }, 'heating')).toEqual({ zone: 'z1', mode: 'heat' });
    expect(activeCurve(base, 'dhw')).toEqual({ zone: 'z1', mode: 'heat' });
  });
  it('picks zone 2 when only zone 2 is active', () => {
    expect(activeCurve({ ...base, zones: F('z2') }, 'heating')).toEqual({ zone: 'z2', mode: 'heat' });
  });
  it('picks cooling while cooling, or when only cooling is in use', () => {
    expect(activeCurve(base, 'cooling')).toEqual({ zone: 'z1', mode: 'cool' });
    expect(activeCurve({ ...base, heating_in_use: F(false), cooling_in_use: F(true) }, 'idle')).toEqual({ zone: 'z1', mode: 'cool' });
  });
  it('returns null when neither heating nor cooling is in use', () => {
    expect(activeCurve({ ...base, heating_in_use: F(false), cooling_in_use: F(false) }, 'dhw')).toBe(null);
  });
});

describe('miniView', () => {
  const view = (profile, extra = {}) => miniView({ profile, values: { ...curveValues(), ...extra }, zone: 'z1', mode: 'heat' });
  it('curve control: curve plus shift', () => {
    const v = view(base, { 'main/Z1_Heat_Request_Temp': 2 });
    expect(v).toMatchObject({ shift: 2, showShift: true, directSetpoint: null, inactive: false, note: null });
  });
  it('direct control: inactive curve with the absolute setpoint', () => {
    const v = view({ ...base, heating_control: F('direct') }, { 'main/Z1_Heat_Request_Temp': 35 });
    expect(v).toMatchObject({ showShift: false, directSetpoint: 35, coupled: false, note: 'notActive' });
  });
  it('coupled: setpoint is the cold-end target', () => {
    const v = view({ ...base, heating_control: F('direct'), zone: { z1: { sensor: F('ext_thermostat') } } });
    expect(v).toMatchObject({ directSetpoint: 45, coupled: true, note: 'setpoint' });
  });
  it('direct with a missing setpoint: inactive, labelled unavailable', () => {
    const v = view({ ...base, heating_control: F('direct') });
    expect(v).toMatchObject({ directSetpoint: null, inactive: true, showShift: false, note: 'miniSetpointUnavailable' });
  });
  it('unknown control: configuration-only preview', () => {
    const v = view({ ...base, heating_control: F(null, true) }, { 'main/Z1_Heat_Request_Temp': 2 });
    expect(v).toMatchObject({ directSetpoint: null, inactive: true, showShift: false, shift: 0, note: 'miniControlUnknown' });
  });
  it('no curve without all four values', () => {
    expect(miniView({ profile: base, values: {}, zone: 'z1', mode: 'heat' }).curve).toBe(null);
  });
});

describe('CurveChart inactive prop', () => {
  it('draws the inactive line style without a direct setpoint', () => {
    const current = { cold: { outside: -10, target: 45 }, warm: { outside: 16, target: 28 } };
    render(CurveChart, { mode: 'heat', current, editable: false, inactive: true });
    expect(screen.getByTestId('curve-line').getAttribute('class')).toContain('inactive-line');
    expect(screen.queryByTestId('direct-line')).toBe(null);
  });
});
