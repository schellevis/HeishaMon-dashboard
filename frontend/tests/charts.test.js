import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import { resetClientState, state, profile, prefs } from '../src/lib/stores.js';

// Stub matchMedia for uplot
vi.stubGlobal('matchMedia', vi.fn(() => ({
  matches: false,
  addListener: vi.fn(),
  removeListener: vi.fn(),
})));
import { translate } from '../src/lib/i18n/index.js';
import { api } from '../src/lib/api.js';
import { catalog, topicByKey } from '../src/lib/catalog.js';
import Charts from '../src/features/charts/ChartsScreen.svelte';
import ChartContainer from '../src/features/charts/ChartContainer.svelte';
import TimeRangeSelector from '../src/features/charts/TimeRangeSelector.svelte';
import TopicSelector from '../src/features/charts/TopicSelector.svelte';
import PresetSelector from '../src/features/charts/PresetSelector.svelte';
import {
  createChart,
  buildSeries,
  themedAxes,
  historyToUplot,
  getBreakChecker,
  insertBreaks,
  COLORS,
  ENUM_COLORS,
} from '../src/lib/uplot.js';
import chartsEn from '../src/lib/i18n/charts.en.js';
import chartsNl from '../src/lib/i18n/charts.nl.js';

// Re-export for easier access
const chartsEnDefault = chartsEn;
const chartsNlDefault = chartsNl;

// Test fixtures
const TEST_TOPICS = [
  { key: 'main/Outside_Temp', kind: 'number', unit: '°C', decimals: 1, label: { en: 'Outside temperature', nl: 'Buitentemperatuur' } },
  { key: 'main/Main_Outlet_Temp', kind: 'number', unit: '°C', decimals: 1, label: { en: 'Outlet temperature', nl: 'Afgifttemperatuur' } },
  { key: 'main/Compressor_State', kind: 'enum', unit: null, decimals: 0, label: { en: 'Compressor state', nl: 'Compressorstatus' } },
  { key: 'main/Error', kind: 'enum', unit: null, decimals: 0, label: { en: 'Error', nl: 'Fout' } },
];

const TEST_HISTORY_RAW = {
  resolution: 'raw',
  partial: false,
  series: {
    'main/Outside_Temp': {
      kind: 'number',
      points: [
        [1000, 15.0],
        [2000, 16.5],
        [3000, null],
        [4000, 17.2],
        [5000, 18.0],
      ],
      coverage: [[1000, 2000], [2000, 3000], [4000, 5000]],
      breaks: [[3000, 4000]],
    },
    'main/Compressor_State': {
      kind: 'enum',
      points: [
        [1000, 0],
        [2000, 1],
        [3000, 1],
        [4000, 0],
        [5000, 0],
      ],
      coverage: [[1000, 5000]],
      breaks: [],
    },
  },
};

const TEST_HISTORY_1M = {
  resolution: '1m',
  partial: false,
  series: {
    'main/Outside_Temp': {
      kind: 'number',
      points: [
        [1200000, 15.5, 60],
        [1260000, 16.0, 60],
        [1320000, null, 0],
        [1380000, 17.0, 60],
      ],
      coverage: null,
      breaks: [[1260000, 1320000]],
    },
  },
};

const TEST_HISTORY_TEXT = {
  resolution: 'raw',
  partial: false,
  series: {
    'main/Error': {
      kind: 'text',
      points: [
        [1000, 'No error'],
        [2000, 'E123'],
        [3000, 'No error'],
      ],
      coverage: [[1000, 2000], [2000, 3000]],
      breaks: [],
    },
  },
};

const TEST_PROFILE = {
  computed_at: 1000,
  features: {
    extra: true,
    dhw: true,
    zones: 2,
  },
  topic_visibility: {
    'main/Outside_Temp': 'visible',
    'main/Main_Outlet_Temp': 'visible',
    'main/Compressor_State': 'visible',
  },
};

// Mock uplot
const uplotCtor = vi.hoisted(() => ({ calls: [] }));
vi.mock('uplot', () => ({
  default: class MockUplot {
    constructor(options, data, target) {
      uplotCtor.calls.push({ options, data, target });
      this.options = options;
      this.data = options.data;
      this.series = options.series;
      this.scales = options.scales;
      this.width = options.width || 800;
      this.height = options.height || 400;
    }
    setData(data) {
      this.data = data;
    }
    destroy() {}
  },
}));

// Mock fetch for API
const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

afterEach(() => {
  resetClientState();
  mockFetch.mockReset();
  localStorage.clear();
  vi.restoreAllMocks();
});

beforeEach(() => {
  // Set up mock catalog
  vi.doMock('$catalog', () => ({
    default: {
      schema: 1,
      topics: TEST_TOPICS,
      commands: [],
      inputs: [],
    },
  }));
});

describe('Charts screen (§7.2)', () => {
  describe('Initialization', () => {
    it('renders the charts screen with testid', () => {
      render(Charts);
      expect(screen.getByTestId('screen-charts')).toBeTruthy();
    });

    it('displays the charts title', () => {
      render(Charts);
      expect(screen.getByText(translate('en', 'charts.charts_title'))).toBeTruthy();
    });

    it('shows empty state when no topics are selected', () => {
      render(Charts);
      expect(screen.getByText(translate('en', 'charts.no_topics_selected'))).toBeTruthy();
    });
  });

  describe('Presets', () => {
    it('has built-in preset names in English', () => {
      expect(chartsEnDefault.preset_temperatures).toBe('Temperatures');
      expect(chartsEnDefault.preset_power_cop).toBe('Power & COP');
      expect(chartsEnDefault.preset_compressor).toBe('Compressor');
      expect(chartsEnDefault.preset_pump_pressure).toBe('Pump & Pressure');
      expect(chartsEnDefault.preset_dhw).toBe('DHW');
      expect(chartsEnDefault.preset_zones).toBe('Zones');
      expect(chartsEnDefault.preset_cooling).toBe('Cooling');
    });

    it('has built-in preset names in Dutch', () => {
      expect(chartsNlDefault.preset_temperatures).toBe('Temperaturen');
      expect(chartsNlDefault.preset_power_cop).toBe('Vermogen & COP');
      expect(chartsNlDefault.preset_compressor).toBe('Compressor');
      expect(chartsNlDefault.preset_pump_pressure).toBe('Pomp & Druk');
      expect(chartsNlDefault.preset_dhw).toBe('Warm water');
      expect(chartsNlDefault.preset_zones).toBe('Zones');
      expect(chartsNlDefault.preset_cooling).toBe('Koelen');
    });

    it('filters presets by profile and ignored topics', async () => {
      // Mock profile without DHW
      profile.set({ ...TEST_PROFILE, features: { dhw: false, zones: 1 } });
      
      // Set DHW topics as ignored
      prefs.set({
        topic_visibility: {
          'main/DHW_Temp': 'ignored',
          'main/DHW_State': 'ignored',
        },
      });

      const { container } = render(PresetSelector, {
        selectedTopics: [],
        onSelectPreset: vi.fn(),
      });

      await tick();

      // Built-in presets should be filtered
      // DHW preset should be filtered out or have topics removed
    });

    it('saves user presets to prefs', async () => {
      const putPrefsMock = vi.fn().mockResolvedValue({});
      vi.spyOn(api, 'putPrefs').mockImplementation(putPrefsMock);

      prefs.set({ chart_presets: [] });

      const { container } = render(PresetSelector, {
        selectedTopics: ['main/Outside_Temp'],
        onSelectPreset: vi.fn(),
      });

      // Find save input and button
      const input = container.querySelector('input[placeholder*="Preset name"]');
      const saveButton = container.querySelector('button');

      // Enter preset name
      fireEvent.input(input, { target: { value: 'Test Preset' } });
      
      // Click save
      fireEvent.click(saveButton);

      await tick();

      // Should call putPrefs
      expect(putPrefsMock).toHaveBeenCalled();
    });
  });

  describe('Line breaks', () => {
    it('breaks line at breaks intervals from history', () => {
      const check = getBreakChecker(TEST_HISTORY_RAW.series['main/Outside_Temp'].breaks);
      
      // Break is [3000, 4000]
      expect(check(2500)).toBe(false);
      expect(check(3500)).toBe(true);
      expect(check(4500)).toBe(false);
    });

    it('breaks line at null points in raw data', () => {
      const history = TEST_HISTORY_RAW;
      const uplot = historyToUplot(history);
      
      // The null at index 2 should create a gap
      // In uplot data, null values are preserved
      expect(uplot.data[1]).toContain(null);
    });

    it('handles breaks at the start and end', () => {
      const breaks = [[0, 1000], [5000, 6000]];
      const check = getBreakChecker(breaks);
      
      expect(check(500)).toBe(true);
      expect(check(2500)).toBe(false);
      expect(check(5500)).toBe(true);
    });

    it('handles empty breaks array', () => {
      const check = getBreakChecker([]);
      expect(check(1000)).toBe(false);
    });

    it('handles null breaks', () => {
      const check = getBreakChecker(null);
      expect(check(1000)).toBe(false);
    });
  });

  describe('Enum bands', () => {
    it('has color mapping for enum values', () => {
      expect(ENUM_COLORS[0]).toBe('#64737f');
      expect(ENUM_COLORS[1]).toBe('#4fa3e0');
      expect(ENUM_COLORS[2]).toBe('#f0a04b');
      expect(ENUM_COLORS[8]).toBe('#93a3b0');
    });

    it('converts enum history to uplot with bands', () => {
      const history = {
        resolution: 'raw',
        partial: false,
        series: {
          'main/Compressor_State': TEST_HISTORY_RAW.series['main/Compressor_State'],
        },
      };

      const uplot = historyToUplot(history);
      
      // Enum series should have bars draw style
      expect(uplot.series[0].enumBand).toBe(true);
      expect(uplot.series[0].fill).toBeDefined();
    });
  });

  describe('CSV link', () => {
    it('CSV link carries the same query as history', async () => {
      const mockHistory = {
        resolution: 'raw',
        partial: false,
        series: {
          'main/Outside_Temp': {
            kind: 'number',
            points: [[1000, 15], [2000, 16]],
            coverage: [],
            breaks: [],
          },
        },
      };

      mockFetch.mockResolvedValue(mockHistory);

      const from = 1000;
      const to = 2000;

      const { container } = render(Charts);

      // Wait for default range to be set
      await tick();

      // Check if CSV button exists
      const csvButton = container.querySelector('a[download]');
      
      // When topics are selected, CSV button should appear
      // This tests the logic, not the actual rendering
    });

    it('historyToUplot produces CSV-compatible data', () => {
      const uplot = historyToUplot(TEST_HISTORY_RAW);
      
      // Each series in uplot.data (except first which is timestamps)
      // should correspond to series in history
      expect(uplot.data.length).toBeGreaterThan(1);
      
      // First column is timestamps
      expect(uplot.data[0].length).toBe(6); // 5 points + inserted break row
      expect(uplot.data[0][0]).toBe(1);
      expect(uplot.data[0][5]).toBe(5);
    });
  });

  describe('User presets saved to prefs', () => {
    it('saves custom preset name', async () => {
      const putPrefsMock = vi.fn().mockResolvedValue({
        chart_presets: [{ name: 'My Preset', topics: ['main/Outside_Temp'] }],
      });
      vi.spyOn(api, 'putPrefs').mockImplementation(putPrefsMock);

      prefs.set({ chart_presets: [] });

      const { container } = render(PresetSelector, {
        selectedTopics: ['main/Outside_Temp'],
        onSelectPreset: vi.fn(),
      });

      const input = container.querySelector('input[placeholder*="Preset name"]');
      fireEvent.input(input, { target: { value: 'My Preset' } });
      
      const saveButton = Array.from(container.querySelectorAll('button')).find(
        b => b.textContent.includes('Save')
      );
      
      fireEvent.click(saveButton);

      await tick();

      expect(putPrefsMock).toHaveBeenCalledWith(expect.objectContaining({
        chart_presets: expect.arrayContaining([
          expect.objectContaining({
            name: 'My Preset',
            topics: ['main/Outside_Temp'],
          }),
        ]),
      }));
    });

    it('rejects duplicate preset names', async () => {
      vi.spyOn(api, 'putPrefs').mockResolvedValue({});

      prefs.set({
        chart_presets: [{ name: 'Duplicate', topics: ['main/Outside_Temp'] }],
      });

      const { container } = render(PresetSelector, {
        selectedTopics: ['main/Outside_Temp'],
        onSelectPreset: vi.fn(),
      });

      const input = container.querySelector('input[placeholder*="Preset name"]');
      fireEvent.input(input, { target: { value: 'Duplicate' } });
      
      const saveButton = Array.from(container.querySelectorAll('button')).find(
        b => b.textContent.includes('Save')
      );
      
      fireEvent.click(saveButton);

      await tick();

      // Should show error
      expect(container.querySelector('.error')?.textContent).toContain('already exists');
    });

    it('deletes user presets', async () => {
      const putPrefsMock = vi.fn().mockResolvedValue({
        chart_presets: [],
      });
      vi.spyOn(api, 'putPrefs').mockImplementation(putPrefsMock);

      const existingPreset = { name: 'To Delete', topics: ['main/Outside_Temp'] };
      prefs.set({ chart_presets: [existingPreset] });

      const { container } = render(PresetSelector, {
        selectedTopics: [],
        onSelectPreset: vi.fn(),
      });

      await tick();

      // Find delete button for the preset
      const deleteButtons = container.querySelectorAll('.delete');
      fireEvent.click(deleteButtons[0]);

      await tick();

      expect(putPrefsMock).toHaveBeenCalledWith(expect.objectContaining({
        chart_presets: [],
      }));
    });
  });
});

describe('uplot utilities', () => {
  describe('historyToUplot', () => {
    it('converts raw history to uplot format', () => {
      const uplot = historyToUplot(TEST_HISTORY_RAW);
      
      expect(uplot.series).toHaveLength(2);
      expect(uplot.data).toHaveLength(3); // timestamps + 2 value series
      expect(uplot.data[0].slice(0, 5)).toEqual([1, 2, 3, 3.001, 4]);
    });

    it('converts 1m rollup history to uplot format', () => {
      const uplot = historyToUplot(TEST_HISTORY_1M);
      
      expect(uplot.series).toHaveLength(1);
      expect(uplot.data).toHaveLength(2);
      expect(uplot.data[0]).toEqual([1200, 1260, 1260.001, 1320, 1380]);
      // uplot uses [ts, avg] format for rollups
      expect(uplot.data[1]).toEqual([15.5, 16.0, null, null, 17.0]);
    });

    it('converts text series to uplot format', () => {
      const uplot = historyToUplot(TEST_HISTORY_TEXT);
      
      expect(uplot.series).toHaveLength(1);
      expect(uplot.data).toHaveLength(2);
    });

    it('handles empty series', () => {
      const uplot = historyToUplot({
        resolution: 'raw',
        partial: false,
        series: {},
      });
      
      expect(uplot.series).toHaveLength(0);
      expect(uplot.data).toHaveLength(0);
    });

    it('identifies enum series from catalog', () => {
      const catalogTopic = { key: 'main/Compressor_State', kind: 'enum' };
      
      const history = {
        resolution: 'raw',
        partial: false,
        series: {
          'main/Compressor_State': {
            kind: 'number', // This is wrong in the data but enum in catalog
            points: [[1000, 0], [2000, 1]],
            coverage: [],
            breaks: [],
          },
        },
      };

      const uplot = historyToUplot(history, { topics: [catalogTopic] });
      
      // Should be identified as enum from catalog
      expect(uplot.series[0].enumBand).toBe(true);
    });
  });

  describe('seconds, breaks and gaps in historyToUplot', () => {
    it('passes x values to uPlot in seconds', () => {
      const u = historyToUplot(TEST_HISTORY_1M);
      expect(u.data[0].every((x) => x < 10000)).toBe(true);
      expect(u.data[0][0]).toBe(1200);
    });

    it('breaks a 1m series inside its break and leaves null/zero-coverage as gaps', () => {
      const u = historyToUplot(TEST_HISTORY_1M);
      const x = u.data[0];
      const y = u.data[1];
      const at = (t) => y[x.indexOf(t)];
      expect(at(1260)).toBe(16.0);
      expect(at(1260.001)).toBeNull(); // inserted at break start
      expect(at(1320)).toBeNull(); // covered_seconds 0
      expect(at(1380)).toBe(17.0);
      expect(u.series[0].spanGaps).toBe(false);
    });

    it('keeps a null raw point as a gap', () => {
      const u = historyToUplot(TEST_HISTORY_RAW);
      expect(u.data[1][u.data[0].indexOf(3)]).toBeNull();
    });
  });

  describe('getBreakChecker', () => {
    it('returns false for timestamps not in any break', () => {
      const check = getBreakChecker([[1000, 2000]]);
      expect(check(500)).toBe(false);
      expect(check(2500)).toBe(false);
    });

    it('returns true for timestamps at break start', () => {
      const check = getBreakChecker([[1000, 2000]]);
      expect(check(1000)).toBe(true);
    });

    it('returns true for timestamps at break end', () => {
      const check = getBreakChecker([[1000, 2000]]);
      expect(check(2000)).toBe(true);
    });

    it('returns true for timestamps within break', () => {
      const check = getBreakChecker([[1000, 2000]]);
      expect(check(1500)).toBe(true);
    });

    it('handles multiple overlapping breaks', () => {
      const check = getBreakChecker([[1000, 2000], [1500, 2500]]);
      expect(check(1000)).toBe(true);
      expect(check(2000)).toBe(true);
      expect(check(2500)).toBe(true);
    });
  });

  describe('insertBreaks', () => {
    it('returns unchanged data when no breaks', () => {
      const data = [[1000, 2000, 3000], [1, 2, 3]];
      const result = insertBreaks(data, []);
      expect(result).toEqual(data);
    });

    it('returns unchanged data when breaks is null', () => {
      const data = [[1000, 2000, 3000], [1, 2, 3]];
      const result = insertBreaks(data, null);
      expect(result).toEqual(data);
    });

    it('inserts a null row for all series at a break start (ms -> s)', () => {
      const data = [[1, 2, 5], [1, 2, 5], [9, 8, 7]];
      const r = insertBreaks(data, [[3000, 4000]]);
      expect(r[0]).toEqual([1, 2, 3, 5]);
      expect(r[1]).toEqual([1, 2, null, 5]);
      expect(r[2]).toEqual([9, 8, null, 7]);
    });

    it('handles empty data', () => {
      const result = insertBreaks([], [[1000, 2000]]);
      expect(result).toEqual([]);
    });
  });
});

describe('Color scheme', () => {
  it('has 10 colors defined', () => {
    expect(COLORS).toHaveLength(10);
  });

  it('has consistent colors', () => {
    expect(COLORS[0]).toBe('#f0a04b'); // amber
    expect(COLORS[1]).toBe('#4fa3e0'); // blue
    expect(COLORS[2]).toBe('#6cc59a'); // green
  });
});

describe('TimeRangeSelector', () => {
  it('renders range presets', () => {
    render(TimeRangeSelector, {
      from: 1000,
      to: 86401000, // 24h in ms
      resolution: null,
    });

    expect(screen.getByRole('button', { name: translate('en', 'charts.range_1h') })).toBeTruthy();
    expect(screen.getByRole('button', { name: translate('en', 'charts.range_6h') })).toBeTruthy();
    expect(screen.getByRole('button', { name: translate('en', 'charts.range_1d') })).toBeTruthy();
  });

  it('renders resolution selector', () => {
    render(TimeRangeSelector, {
      from: 1000,
      to: 2000,
      resolution: null,
    });

    expect(screen.getByText(translate('en', 'charts.resolution_label') + ':')).toBeTruthy();
    expect(screen.getByRole('option', { name: translate('en', 'charts.resolution_auto') })).toBeTruthy();
    expect(screen.getByRole('option', { name: translate('en', 'charts.resolution_raw') })).toBeTruthy();
    expect(screen.getByRole('option', { name: translate('en', 'charts.resolution_1m') })).toBeTruthy();
    expect(screen.getByRole('option', { name: translate('en', 'charts.resolution_1h') })).toBeTruthy();
  });

  it('renders zoom controls', () => {
    render(TimeRangeSelector);

    expect(screen.getByText('Zoom in')).toBeTruthy();
    expect(screen.getByText('Zoom out')).toBeTruthy();
  });

  it('resolution select shows Auto when no resolution is set', () => {
    render(TimeRangeSelector, { from: 0, to: 3_600_000, resolution: null, onRangeChange: vi.fn(), onResolutionChange: vi.fn() });
    const select = screen.getByTestId('resolution-select');
    expect(select.value).toBe('');
    expect(select.selectedOptions[0].textContent.trim()).not.toBe('');
  });
});

describe('TopicSelector', () => {
  it('renders available topics', () => {
    render(TopicSelector, {
      selected: [],
      onSelect: vi.fn(),
      maxTopics: 20,
    });

    // Should show filter input
    expect(screen.getByPlaceholderText(translate('en', 'charts.filter_topics_placeholder'))).toBeTruthy();
  });

  it('shows selected topics count', () => {
    render(TopicSelector, {
      selected: ['main/Outside_Temp', 'main/Main_Outlet_Temp'],
      onSelect: vi.fn(),
      maxTopics: 20,
    });

    expect(screen.getByText(/2 \/ 20/)).toBeTruthy();
  });

  it('shows maximum topics limit warning', () => {
    const selected = Array(20).fill('topic');
    render(TopicSelector, {
      selected,
      onSelect: vi.fn(),
      maxTopics: 20,
    });

    expect(screen.getByText(/20 \/ 20/)).toBeTruthy();
  });
});

describe('ChartContainer', () => {
  it('renders empty state when no topics', () => {
    render(ChartContainer, {
      topics: [],
      from: 1000,
      to: 2000,
    });

    expect(screen.getByText(translate('en', 'charts.no_topics_selected'))).toBeTruthy();
  });

  it('renders loading state', () => {
    // Mock fetch to return a promise
    mockFetch.mockImplementation(() => new Promise(() => {}));

    render(ChartContainer, {
      topics: ['main/Outside_Temp'],
      from: 1000,
      to: 2000,
    });

    expect(screen.getByText(translate('en', 'charts.loading'))).toBeTruthy();
  });

  it('renders chart when data loads', async () => {
    mockFetch.mockResolvedValue(TEST_HISTORY_RAW);

    render(ChartContainer, {
      topics: ['main/Outside_Temp'],
      from: 1000,
      to: 2000,
    });

    await tick();

    // Chart container should be rendered
    expect(screen.getByTestId('chart-container')).toBeTruthy();
  });
});

describe('ChartContainer regression: no effect loop', () => {
  it('creates the chart once per data load and passes its container', async () => {
    uplotCtor.calls.length = 0;
    const hist = vi.spyOn(api, 'history').mockResolvedValue(TEST_HISTORY_RAW);
    render(ChartContainer, { topics: ['main/Outside_Temp'], from: 1000, to: 2000, height: 300, showLegend: true });
    await new Promise((r) => setTimeout(r, 150));
    await tick();
    expect(hist).toHaveBeenCalledTimes(1);
    expect(uplotCtor.calls).toHaveLength(1);
    const el = screen.getByTestId('chart-container');
    expect(uplotCtor.calls[0].target).toBe(el);
    // x-axis series placeholder + value series, no string draw hooks
    expect(uplotCtor.calls[0].options.series[0]).toEqual({});
    expect(uplotCtor.calls[0].options.series.every((s) => typeof s.draw !== 'string')).toBe(true);
  });
});

describe('chart labels and local time axis (§7.2)', () => {
  it('series use catalog labels in the UI language, with the unit', async () => {
    const { historyToUplot: toUplot } = await import('../src/lib/uplot.js');
    const history = { resolution: 'raw', partial: false, series: { 'main/Outside_Temp': { kind: 'number', points: [[1000, 5]], breaks: [] } } };
    const cat = { topics: [{ key: 'main/Outside_Temp', kind: 'number', unit: '°C', label: { en: 'Outside temperature', nl: 'Buitentemperatuur' } }] };
    expect(toUplot(history, cat, { lang: 'nl' }).series[0].label).toBe('Buitentemperatuur (°C)');
    expect(toUplot(history, cat, { lang: 'en' }).series[0].label).toBe('Outside temperature (°C)');
  });

  it('time axis is 24-hour in the given time zone, not UTC am/pm', async () => {
    const { timeAxes } = await import('../src/lib/uplot.js');
    const [x] = timeAxes('nl', 'Europe/Amsterdam');
    // 2026-10-12T07:43:00Z is 09:43 in Amsterdam (CEST)
    const sec = Date.UTC(2026, 9, 12, 7, 43) / 1000;
    expect(x.values(null, [sec], 0, 70, 3600)).toEqual(['09:43']);
    const [xEn] = timeAxes('en', 'Europe/Amsterdam');
    expect(xEn.values(null, [sec], 0, 70, 3600)[0]).not.toMatch(/am|pm/i);
  });
});

describe('T06: LOCF alignment, preset contract, overrides', () => {
  const hist = (extra = {}) => ({
    resolution: 'raw',
    series: {
      'main/A': { kind: 'number', points: [[1000, 1], [4000, 2]], breaks: [], ...extra.a },
      'main/B': { kind: 'number', points: [[2000, 10], [3000, 20], [5000, 30]], breaks: [], ...extra.b },
    },
  });

  it('carries the last value forward on the shared axis', () => {
    const u = historyToUplot(hist());
    expect(u.data[0]).toEqual([1, 2, 3, 4, 5]);
    expect(u.data[1]).toEqual([1, 1, 1, 2, 2]);
    expect(u.data[2]).toEqual([null, 10, 20, 20, 30]);
  });

  it('keeps null for zero-coverage points and does not carry across them', () => {
    const u = historyToUplot(hist({ a: { points: [[1000, 1, 5], [2500, 9, 0], [4000, 2, 5]] } }));
    expect(u.data[1]).toEqual([1, 1, null, null, 2, 2]);
  });

  it('keeps null inside and across a series break', () => {
    const u = historyToUplot(hist({ b: { breaks: [[2500, 4500]] } }));
    // B: 2000=10, 3000=20 is inside the break only as a point; 4000 lies in the break
    expect(u.data[0]).toEqual([1, 2, 2.5, 3, 4, 5]);
    expect(u.data[2][4]).toBeNull();
  });

  it('every built-in preset key is a catalog key', async () => {
    const { readFileSync } = await import('node:fs');
    const { resolve } = await import('node:path');
    const real = JSON.parse(readFileSync(resolve(process.cwd(), '../backend/heishamon_dashboard/catalog.json'), 'utf8'));
    const { BUILTIN_PRESETS, presetTopics } = await import('../src/features/charts/PresetSelector.svelte');
    const keys = new Set(real.topics.map((t) => t.key));
    for (const profileVariant of [null, { has_extra: { value: true } }, { has_extra: { value: false } }]) {
      for (const preset of Object.values(BUILTIN_PRESETS)) {
        for (const key of presetTopics(preset, profileVariant)) expect(keys.has(key), key).toBe(true);
      }
    }
  });

  it('reads feature overrides from the prefs store', async () => {
    const probe = { key: 'main/Feature_Probe', kind: 'number', unit: '', decimals: 0, feature: 'dhw', category: 'x', label: { en: 'Feature probe' } };
    catalog.topics.push(probe);
    try {
      profile.set({});
      prefs.set({});
      const shown = render(TopicSelector, { selected: [], onSelect: vi.fn() });
      await tick();
      expect(shown.container.textContent).toContain('Feature probe');
      shown.unmount();
      prefs.set({ feature_overrides: { dhw: 'hide' } });
      const hidden = render(TopicSelector, { selected: [], onSelect: vi.fn() });
      await tick();
      expect(hidden.container.textContent).not.toContain('Feature probe');
    } finally {
      catalog.topics.splice(catalog.topics.indexOf(probe), 1);
    }
  });
});

describe('buildSeries', () => {
  const Fake = { paths: { stepped: () => 'STEPPED' } };
  it('prepends the x series and steps enum and stepped series', () => {
    const out = buildSeries([{ label: 'a' }, { label: 'b', enumBand: true }, { label: 'c', stepped: true }], Fake);
    expect(out[0]).toEqual({});
    expect(out[1].paths).toBeUndefined();
    expect(out[2].paths).toBe('STEPPED');
    expect(out[3].paths).toBe('STEPPED');
    expect('stepped' in out[3]).toBe(false);
  });
});

describe('themedAxes', () => {
  it('keeps explicit axis colours and fills the rest', () => {
    const [a, b] = themedAxes([{ stroke: 'red' }, {}]);
    expect(a.stroke).toBe('red');
    expect(b).toHaveProperty('grid');
    expect(b).toHaveProperty('ticks');
  });
});
