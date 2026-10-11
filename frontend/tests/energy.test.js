import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { tick } from 'svelte';
import { render, screen } from '@testing-library/svelte';
import Energy from '../src/screens/Energy.svelte';
import { api } from '../src/lib/api.js';
import { language, profile, resetClientState, state } from '../src/lib/stores.js';
import { translate } from '../src/lib/i18n/index.js';

// Mock date for consistent testing
const mockDate = new Date('2026-10-11T03:00:00.000Z');
const fromTs = mockDate.getTime() - 2 * 60 * 60 * 1000; // 01:00:00
const toTs = mockDate.getTime(); // 03:00:00

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(mockDate);
});

afterEach(() => {
  vi.useRealTimers();
  resetClientState();
  vi.restoreAllMocks();
});

// Helper to create a T2-like history response
// T2: one sample at 500W at 01:00:00, unchanged until flush at 03:00:00
// Energy = 500 * 7200 = 3,600,000 J = 1.0 kWh
function createT2History() {
  // 01:00:00 to 03:00:00 = 2 hours = 7200 seconds
  // At 1h resolution, we have 2 buckets of 3600 seconds each
  // bucket_start_ts for 01:00 = fromTs, for 02:00 = fromTs + 3600000
  const prodPoints = [
    [fromTs, 500, 3600],  // 01:00-02:00: 500W avg, 3600s covered
    [fromTs + 3600000, 500, 3600],  // 02:00-03:00: 500W avg, 3600s covered
  ];
  
  return {
    resolution: '1h',
    partial: false,
    series: {
      'main/Heat_Power_Production': {
        kind: 'number',
        points: prodPoints,
        coverage: null,
        breaks: [],
      },
      'main/Heat_Power_Consumption': {
        kind: 'number',
        points: prodPoints.map(([ts, avg, cov]) => [ts, avg, cov]),
        coverage: null,
        breaks: [],
      },
    },
  };
}

// Profile without extra (uses main/ topics)
function createProfileWithoutExtra() {
  return {
    computed_at: mockDate.getTime(),
    has_extra: { value: false, unknown: false, stale: false },
    operating_mode: { value: 4, unknown: false, stale: false }, // Heat + DHW
    heating_in_use: { value: true, unknown: false, stale: false },
    cooling_in_use: { value: false, unknown: false, stale: false },
    dhw_in_use: { value: true, unknown: false, stale: false },
  };
}

// Profile with extra (uses extra/ topics)
function createProfileWithExtra() {
  return {
    computed_at: mockDate.getTime(),
    has_extra: { value: true, unknown: false, stale: false },
    operating_mode: { value: 4, unknown: false, stale: false },
    heating_in_use: { value: true, unknown: false, stale: false },
    cooling_in_use: { value: false, unknown: false, stale: false },
    dhw_in_use: { value: true, unknown: false, stale: false },
  };
}

describe('Energy screen (T16)', () => {
  describe('i18n strings', () => {
    it('has matching EN and NL string keys', () => {
      // This is tested by the i18n.test.js glob test, but we verify the module loads
      expect(translate('en', 'energy.title')).toBe('Energy');
      expect(translate('nl', 'energy.title')).toBe('Energie');
    });
  });

  describe('T2-like fixture energy equals 1.0 kWh', () => {
    it('computes 1.0 kWh from T2-like fixture (500W for 2 hours)', async () => {
      const t2History = createT2History();
      
      // Mock the API
      vi.spyOn(api, 'history').mockResolvedValue(t2History);
      
      // Set up stores
      profile.set(createProfileWithoutExtra());
      state.set({
        seq: 1,
        topics: {
          'main/Heat_Power_Production': {
            value: 500, raw: '500', kind: 'number', unit: 'W', decimals: 0,
            enum_label: null, catalogued: true, sentinel: false,
            last_change: mockDate.getTime(), last_seen: mockDate.getTime(), retained_only: false,
          },
          'main/Heat_Power_Consumption': {
            value: 500, raw: '500', kind: 'number', unit: 'W', decimals: 0,
            enum_label: null, catalogued: true, sentinel: false,
            last_change: mockDate.getTime(), last_seen: mockDate.getTime(), retained_only: false,
          },
        },
        device_online: 'online',
        last_device_message: mockDate.getTime(),
        broker_connected: true,
        listen_only_suspected: false,
      });
      language.set('en');
      
      render(Energy);
      
      // Wait for the async load to complete
      await tick();
      await vi.waitFor(() => {
        // The loading state should be false
        expect(screen.queryByTestId('loading')).toBeNull();
      });
      
      // The energy should be computed from the history
      // T2: 500 * 7200 = 3,600,000 J = 1.0 kWh
      // Check that the production value shows "1.00" (toFixed(2) for values < 10)
      const prodCell = screen.getByTestId('prod-heat');
      expect(prodCell.textContent).toContain('1.00');
      
      // Also check the consumption
      const consCell = screen.getByTestId('cons-heat');
      expect(consCell.textContent).toContain('1.00');
    });
  });

  describe('estimate label', () => {
    it('shows estimate label when using main/ topics (no extra)', async () => {
      vi.spyOn(api, 'history').mockResolvedValue({
        resolution: '1h',
        partial: false,
        series: {
          'main/Heat_Power_Production': {
            kind: 'number',
            points: [[fromTs, 500, 3600]],
            coverage: null,
            breaks: [],
          },
          'main/Heat_Power_Consumption': {
            kind: 'number',
            points: [[fromTs, 500, 3600]],
            coverage: null,
            breaks: [],
          },
        },
      });
      
      profile.set(createProfileWithoutExtra());
      state.set({
        seq: 1,
        topics: {},
        device_online: 'online',
        last_device_message: mockDate.getTime(),
        broker_connected: true,
        listen_only_suspected: false,
      });
      language.set('en');
      
      render(Energy);
      
      await tick();
      await vi.waitFor(() => {
        expect(screen.queryByTestId('loading')).toBeNull();
      });
      
      // Should show estimate label (because we're using main/ topics)
      expect(screen.getByTestId('estimate-label')).toBeTruthy();
    });

    it('does not show estimate label when using extra/ topics', async () => {
      vi.spyOn(api, 'history').mockResolvedValue({
        resolution: '1h',
        partial: false,
        series: {},
      });
      
      profile.set(createProfileWithExtra());
      state.set({
        seq: 1,
        topics: {},
        device_online: 'online',
        last_device_message: mockDate.getTime(),
        broker_connected: true,
        listen_only_suspected: false,
      });
      language.set('en');
      
      render(Energy);
      
      await tick();
      await vi.waitFor(() => {
        expect(screen.queryByTestId('loading')).toBeNull();
      });
      
      // Should NOT show estimate note
      expect(screen.queryByTestId('estimate-note')).toBeNull();
      // Should NOT show estimate label
      expect(screen.queryByTestId('estimate-label')).toBeNull();
    });
  });

  describe('S0 display', () => {
    it('shows S0 section when S0 topics are present', async () => {
      vi.spyOn(api, 'history').mockResolvedValue({
        resolution: '1h',
        partial: false,
        series: {},
      });
      
      const s0Value = 1500.5;
      profile.set(createProfileWithoutExtra());
      state.set({
        seq: 1,
        topics: {
          's0/WatthourTotal/1': {
            value: s0Value, raw: '1500.5', kind: 'number', unit: 'kWh', decimals: 1,
            enum_label: null, catalogued: true, sentinel: false,
            last_change: mockDate.getTime(), last_seen: mockDate.getTime(), retained_only: false,
          },
        },
        device_online: 'online',
        last_device_message: mockDate.getTime(),
        broker_connected: true,
        listen_only_suspected: false,
      });
      language.set('en');
      
      render(Energy);
      
      await tick();
      await vi.waitFor(() => {
        expect(screen.queryByTestId('loading')).toBeNull();
      });
      
      // Should show S0 section
      expect(screen.getByTestId('s0-section')).toBeTruthy();
      // Should show the S0 value
      expect(screen.getByTestId('s0-s0-WatthourTotal-1')).toBeTruthy();
    });

    it('omits S0 section when no S0 topics', async () => {
      vi.spyOn(api, 'history').mockResolvedValue({
        resolution: '1h',
        partial: false,
        series: {},
      });
      
      profile.set(createProfileWithoutExtra());
      state.set({
        seq: 1,
        topics: {},
        device_online: 'online',
        last_device_message: mockDate.getTime(),
        broker_connected: true,
        listen_only_suspected: false,
      });
      language.set('en');
      
      render(Energy);
      
      await tick();
      await vi.waitFor(() => {
        expect(screen.queryByTestId('loading')).toBeNull();
      });
      
      // Should NOT show S0 section
      expect(screen.queryByTestId('s0-section')).toBeNull();
    });
  });

  describe('empty splits', () => {
    it('omits modes with no data', async () => {
      vi.spyOn(api, 'history').mockResolvedValue({
        resolution: '1h',
        partial: false,
        series: {
          // Only heat production and consumption have data
          'main/Heat_Power_Production': {
            kind: 'number',
            points: [[fromTs, 500, 3600]],
            coverage: null,
            breaks: [],
          },
          'main/Heat_Power_Consumption': {
            kind: 'number',
            points: [[fromTs, 500, 3600]],
            coverage: null,
            breaks: [],
          },
          // Cool and DHW have no data (empty points)
          'main/Cool_Power_Production': {
            kind: 'number',
            points: [],
            coverage: null,
            breaks: [],
          },
          'main/Cool_Power_Consumption': {
            kind: 'number',
            points: [],
            coverage: null,
            breaks: [],
          },
          'main/DHW_Power_Production': {
            kind: 'number',
            points: [],
            coverage: null,
            breaks: [],
          },
          'main/DHW_Power_Consumption': {
            kind: 'number',
            points: [],
            coverage: null,
            breaks: [],
          },
        },
      });
      
      profile.set(createProfileWithoutExtra());
      state.set({
        seq: 1,
        topics: {},
        device_online: 'online',
        last_device_message: mockDate.getTime(),
        broker_connected: true,
        listen_only_suspected: false,
      });
      language.set('en');
      
      render(Energy);
      
      await tick();
      await vi.waitFor(() => {
        expect(screen.queryByTestId('loading')).toBeNull();
      });
      
      // Should show heat row
      expect(screen.getByTestId('energy-row-heat')).toBeTruthy();
      // Should NOT show cool row (empty)
      expect(screen.queryByTestId('energy-row-cool')).toBeNull();
      // Should NOT show dhw row (empty)
      expect(screen.queryByTestId('energy-row-dhw')).toBeNull();
    });
  });

  describe('period selector', () => {
    it('renders all period buttons when data exists', async () => {
      vi.spyOn(api, 'history').mockResolvedValue(createT2History());
      
      profile.set(createProfileWithoutExtra());
      state.set({
        seq: 1,
        topics: {},
        device_online: 'online',
        last_device_message: mockDate.getTime(),
        broker_connected: true,
        listen_only_suspected: false,
      });
      language.set('en');
      
      render(Energy);
      
      await tick();
      await vi.waitFor(() => {
        expect(screen.queryByTestId('loading')).toBeNull();
      });
      
      expect(screen.getByTestId('period-selector')).toBeTruthy();
      expect(screen.getByTestId('period-day')).toBeTruthy();
      expect(screen.getByTestId('period-month')).toBeTruthy();
      expect(screen.getByTestId('period-year')).toBeTruthy();
    });
  });
});
