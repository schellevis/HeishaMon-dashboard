import { afterEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import Energy from '../src/features/energy/EnergyScreen.svelte';
import { api } from '../src/lib/api.js';
import { applyHello, language, resetClientState } from '../src/lib/stores.js';
import { translate } from '../src/lib/i18n/index.js';

afterEach(() => {
  resetClientState();
  vi.restoreAllMocks();
});

const flag = (value) => ({ value, unknown: false, stale: false });

function energyBody(period = 'day', periods = {}) {
  return { tz: 'UTC', period, from: 0, to: 1, estimate: true, periods };
}

const DAY_ROWS = {
  '2026-10-11': { heat: { production_kwh: 3, consumption_kwh: 1 } },
  '2026-10-10': { dhw: { production_kwh: 2, consumption_kwh: 1 }, heat: { production_kwh: 1, consumption_kwh: 1 } },
};

function hello(topics = {}, hasExtra = false) {
  applyHello({
    type: 'hello',
    state: { seq: 1, topics, device_online: 'online' },
    profile: { has_extra: flag(hasExtra) },
  });
}

describe('Energy screen', () => {
  it('has matching EN and NL strings', () => {
    expect(translate('en', 'energy.title')).toBe('Energy');
    expect(translate('nl', 'energy.title')).toBe('Energie');
  });

  it('mounts before hello, then loads', async () => {
    const energy = vi.spyOn(api, 'energy').mockResolvedValue(energyBody('day', DAY_ROWS));
    render(Energy);
    await tick();
    expect(energy).not.toHaveBeenCalled();
    hello();
    await waitFor(() => expect(screen.getByTestId('energy-table')).toBeTruthy());
    expect(energy).toHaveBeenCalledWith({ period: 'day' });
    expect(screen.getByTestId('prod-2026-10-11-heat').textContent).toContain('3.00 kWh');
    expect(screen.getByTestId('cop-2026-10-11-heat').textContent).toBe('3.00');
    expect(screen.getByTestId('total-prod').textContent).toContain('6.00 kWh');
    // empty modes are omitted
    expect(screen.queryByTestId('energy-row-2026-10-11-cool')).toBeNull();
  });

  it('re-renders text when the language switches', async () => {
    vi.spyOn(api, 'energy').mockResolvedValue(energyBody('day', DAY_ROWS));
    language.set('en');
    hello();
    render(Energy);
    await waitFor(() => expect(screen.getByTestId('energy-table')).toBeTruthy());
    expect(screen.getByTestId('period-day').textContent.trim()).toBe('Day');
    language.set('nl');
    await waitFor(() => expect(screen.getByTestId('period-day').textContent.trim()).toBe('Dag'));
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Energie');
  });

  it('shows S0 WatthourTotal as cumulative kWh', async () => {
    vi.spyOn(api, 'energy').mockResolvedValue(energyBody());
    hello({
      's0/WatthourTotal/1': {
        value: 1000, raw: '1000', kind: 'number', unit: 'Wh', decimals: 0, enum_label: null,
        catalogued: true, sentinel: false, last_change: 1, last_seen: 1, retained_only: false,
      },
    });
    render(Energy);
    await waitFor(() => expect(screen.getByTestId('s0-section')).toBeTruthy());
    expect(screen.getByTestId('s0-s0-WatthourTotal-1').textContent).toContain('1.0 kWh');
    expect(screen.getByTestId('s0-section').textContent).toContain('Cumulative meter reading');
  });

  it('requests the chosen period', async () => {
    const energy = vi.spyOn(api, 'energy').mockImplementation(async ({ period }) =>
      energyBody(period, { [period === 'month' ? '2026-10' : '2026']: { heat: { production_kwh: 4, consumption_kwh: 2 } } }));
    hello();
    render(Energy);
    await waitFor(() => expect(energy).toHaveBeenCalledWith({ period: 'day' }));
    await fireEvent.click(screen.getByTestId('period-month'));
    await waitFor(() => expect(energy).toHaveBeenCalledWith({ period: 'month' }));
    await waitFor(() => expect(screen.getByTestId('energy-row-2026-10-heat')).toBeTruthy());
    await fireEvent.click(screen.getByTestId('period-year'));
    await waitFor(() => expect(energy).toHaveBeenCalledWith({ period: 'year' }));
    await waitFor(() => expect(screen.getByTestId('energy-row-2026-heat')).toBeTruthy());
  });

  it('labels main/ based values as an estimate only without extra', async () => {
    vi.spyOn(api, 'energy').mockResolvedValue({ ...energyBody('day', DAY_ROWS), estimate: false });
    hello({}, true);
    render(Energy);
    await waitFor(() => expect(screen.getByTestId('energy-table')).toBeTruthy());
    expect(screen.queryByTestId('estimate-label')).toBeNull();
  });
});
