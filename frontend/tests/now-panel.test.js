import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/svelte';
import NowPanel, { nowMode, todayLabel, todayTotals } from '../src/features/overview/NowPanel.svelte';
import { api } from '../src/lib/api.js';

const F = (value) => ({ value, unknown: false, stale: false });
const T = (value) => ({ value, sentinel: false, last_change: 1, last_seen: 1, retained_only: false });
const profile = { has_extra: F(false) };
const live = { topics: {
  'main/Heat_Power_Production': T(2710), 'main/Heat_Power_Consumption': T(620),
  'main/Compressor_Freq': T(34), 'main/Pump_Flow': T(14.8),
} };

afterEach(() => vi.restoreAllMocks());

// 2026-10-14 10:00 Europe/Amsterdam
const TO = Date.UTC(2026, 9, 14, 8, 0);

describe('todayTotals', () => {
  it('sums today (server-local date of `to`) over all modes', () => {
    const r = todayTotals({ tz: 'Europe/Amsterdam', to: TO, periods: {
      '2026-10-13': { heat: { production_kwh: 1, consumption_kwh: 1 } },
      '2026-10-14': { heat: { production_kwh: 24, consumption_kwh: 6 }, dhw: { production_kwh: 6, consumption_kwh: 2 } },
    } });
    expect(r).toEqual({ consumed: 8, produced: 30, cop: 3.75 });
  });
  it('uses the server time zone for the date', () => {
    // 23:30 UTC on the 13th is already the 14th in Amsterdam
    expect(todayLabel({ tz: 'Europe/Amsterdam', to: Date.UTC(2026, 9, 13, 23, 30) })).toBe('2026-10-14');
  });
  it('returns null when today has no period, or without data', () => {
    expect(todayTotals({ tz: 'Europe/Amsterdam', to: TO, periods: { '2026-10-13': { heat: { production_kwh: 1, consumption_kwh: 1 } } } })).toBe(null);
    expect(todayTotals(null)).toBe(null);
    expect(todayTotals({ periods: {} })).toBe(null);
  });
});

describe('nowMode', () => {
  it('follows the activity', () => {
    expect(nowMode('dhw')).toBe('dhw');
    expect(nowMode('cooling')).toBe('cool');
    for (const a of ['heating', 'defrost', 'idle']) expect(nowMode(a)).toBe('heat');
  });
});

describe('NowPanel', () => {
  it('shows COP, power and today', async () => {
    vi.spyOn(api, 'energy').mockResolvedValue({ tz: 'Europe/Amsterdam', to: TO, periods: { '2026-10-14': { heat: { production_kwh: 24, consumption_kwh: 6 } } } });
    render(NowPanel, { stateData: live, profile, lang: 'en' });
    expect(screen.getByTestId('now-mode').textContent).toBe('Heating');
    expect(screen.getByTestId('now-cop').textContent).toBe('4.4');
    expect(screen.getByTestId('now-power').textContent).toBe('2.71 kW out / 0.62 kW in');
    expect(screen.getByTestId('now-compressor').textContent).toContain('34');
    await waitFor(() => expect(screen.getByTestId('now-today').textContent).toContain('6.0'));
  });
  it('shows a dash when COP cannot be computed and hides today on failure', async () => {
    vi.spyOn(api, 'energy').mockRejectedValue(new Error('x'));
    render(NowPanel, { stateData: { topics: {} }, profile, lang: 'en' });
    expect(screen.getByTestId('now-cop').textContent).toBe('—');
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByTestId('now-today')).toBe(null);
  });
  it('shows the DHW pair during a DHW run', () => {
    vi.spyOn(api, 'energy').mockResolvedValue({ periods: {} });
    const dhw = { topics: { ...live.topics, 'main/ThreeWay_Valve_State': T(1),
      'main/DHW_Power_Production': T(3000), 'main/DHW_Power_Consumption': T(1000) } };
    render(NowPanel, { stateData: dhw, profile, lang: 'en' });
    expect(screen.getByTestId('now-mode').textContent).toBe('DHW');
    expect(screen.getByTestId('now-cop').textContent).toBe('3.0');
    expect(screen.getByTestId('now-power').textContent).toBe('3.00 kW out / 1.00 kW in');
  });
  it('shows the cooling pair as EER without the ambient bar', () => {
    vi.spyOn(api, 'energy').mockResolvedValue({ periods: {} });
    const cool = { topics: { 'main/Heatpump_State': T(1), 'main/Operating_Mode_State': T(1),
      'main/Cool_Power_Production': T(2000), 'main/Cool_Power_Consumption': T(500) } };
    render(NowPanel, { stateData: cool, profile: { ...profile, operating_mode: F(1) }, lang: 'en' });
    expect(screen.getByTestId('now-mode').textContent).toBe('Cooling');
    expect(screen.getByTestId('now-cop-label').textContent).toBe('EER');
    expect(screen.getByTestId('now-cop').textContent).toBe('4.0');
    expect(screen.queryByTestId('now-bar')).toBe(null);
  });
});

describe('liveCop mode argument', () => {
  it('keeps the heat default and selects other pairs', async () => {
    const { liveCop } = await import('../src/lib/domain/power.js');
    const v = { 'main/Heat_Power_Production': T(2000), 'main/Heat_Power_Consumption': T(500),
      'main/DHW_Power_Production': T(900), 'main/DHW_Power_Consumption': T(300) };
    expect(liveCop(v, profile).value).toBe(4);
    expect(liveCop(v, profile, 'dhw').value).toBe(3);
    expect(liveCop(v, profile, 'cool')).toBe(null);
  });
});
