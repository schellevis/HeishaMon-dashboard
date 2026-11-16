import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import PlantSchematic from '../src/features/overview/PlantSchematic.svelte';

const F = (value) => ({ value, unknown: false, stale: false });
const T = (value) => ({ value, sentinel: false });
const profile = { zones: F('z1'), dhw_installed: F(true), buffer_installed: F(false), operating_mode: F(4), heating_control: F('curve') };
const live = { topics: {
  'main/Outside_Temp': T(6.3), 'main/Compressor_Freq': T(34), 'main/Main_Outlet_Temp': T(35.2),
  'main/Main_Inlet_Temp': T(30.4), 'main/Main_Target_Temp': T(35), 'main/Pump_Flow': T(14.8),
  'main/ThreeWay_Valve_State': T(0), 'main/Heatpump_State': T(1), 'main/Defrosting_State': T(0),
  'main/DHW_Temp': T(48.6), 'main/DHW_Target_Temp': T(52),
} };

describe('PlantSchematic', () => {
  it('shows the readings', () => {
    render(PlantSchematic, { stateData: live, profile, lang: 'en' });
    expect(screen.getByTestId('plant-outside').textContent).toBe('6.3°');
    expect(screen.getByTestId('plant-flow').textContent).toBe('35.2°');
    expect(screen.getByTestId('plant-return').textContent).toBe('30.4°');
    expect(screen.getByTestId('plant-compressor').textContent).toBe('34');
    expect(screen.getByTestId('plant-pump').textContent).toBe('14.8');
    expect(screen.getByTestId('plant-dhw').textContent).toBe('48.6°');
    expect(screen.getByTestId('plant').textContent).toContain('Heating');
  });
  it('dims the DHW branch while the valve points at the room', () => {
    render(PlantSchematic, { stateData: live, profile, lang: 'en' });
    expect(screen.getByTestId('plant-dhw-branch').getAttribute('data-active')).toBe('false');
  });
  it('hides the tank when the profile has none', () => {
    render(PlantSchematic, { stateData: live, profile: { ...profile, dhw_installed: F(false) }, lang: 'en' });
    expect(screen.queryByTestId('plant-dhw-branch')).toBe(null);
  });
  it('draws two zones', () => {
    render(PlantSchematic, { stateData: live, profile: { ...profile, zones: F('both') }, lang: 'nl' });
    expect(screen.getByTestId('plant-zone-z1')).toBeTruthy();
    expect(screen.getByTestId('plant-zone-z2')).toBeTruthy();
  });
  it('draws the buffer tank with its temperature when the profile has one', () => {
    const withBuffer = { topics: { ...live.topics, 'main/Buffer_Temp': T(41.5) } };
    render(PlantSchematic, { stateData: withBuffer, profile: { ...profile, buffer_installed: F(true) }, lang: 'en' });
    expect(screen.getByTestId('plant-buffer').textContent).toContain('41.5°');
  });
  it('has no buffer without one in the profile', () => {
    render(PlantSchematic, { stateData: live, profile, lang: 'en' });
    expect(screen.queryByTestId('plant-buffer')).toBe(null);
  });
  it('shows a dash for a missing reading', () => {
    render(PlantSchematic, { stateData: { topics: {} }, profile, lang: 'en' });
    expect(screen.getByTestId('plant-outside').textContent).toBe('—');
  });
});
