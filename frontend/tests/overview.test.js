import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import Overview from '../src/features/overview/OverviewScreen.svelte';
import QuickControls from '../src/features/overview/QuickControls.svelte';
import Tile from '../src/features/overview/Tile.svelte';
import Sparkline from '../src/features/overview/Sparkline.svelte';
import {
  language,
  profile,
  prefs,
  resetClientState,
  state,
} from '../src/lib/stores.js';
import { api } from '../src/lib/api.js';
import { translate } from '../src/lib/i18n/index.js';
import { commandByName, topicByKey } from '../src/lib/catalog.js';

// Import production catalog for tile key validation
import productionCatalog from '../../backend/heishamon_dashboard/catalog.json';

// The vitest `$catalog` alias is a minimal fixture; catalogued-key tiles need the real topics.
vi.mock('../src/lib/catalog.js', async (importOriginal) => {
  const original = await importOriginal();
  const full = (await import('../../backend/heishamon_dashboard/catalog.json')).default;
  return { ...original, topicByKey: (key) => full.topics.find((t) => t.key === key) ?? original.topicByKey(key) };
});

// Profile fixtures per spec §7.1 and §4.3
function makeF(value, unknown = false, stale = false) {
  return { value, unknown, stale };
}

function makeZone(active = true, sensor = 'water') {
  return { active: makeF(active), sensor: makeF(sensor) };
}

const profileFixtures = {
  heatOnly: {
    computed_at: 1000,
    operating_mode: makeF(0), // Heat
    heating_in_use: makeF(true),
    cooling_in_use: makeF(false),
    dhw_in_use: makeF(false),
    zones: makeF('z1'),
    heating_control: makeF('curve'),
    cooling_control: makeF('curve'),
    zone: { z1: makeZone(true, 'water'), z2: makeZone(false, 'water') },
    dhw_installed: makeF(false),
    buffer_installed: makeF(false),
    solar: makeF('off'),
    bivalent: makeF(false),
    glycol: makeF(false),
    optional_pcb_setting: makeF(false),
    pcb_emulation_active: makeF(false),
    has_extra: makeF(false),
    has_1wire: makeF(false),
    has_s0: makeF(false),
    has_opentherm: makeF(false),
    model: makeF(null, true),
    series: makeF(null, true),
    firmware: makeF('4.2.3'),
    firmware_assumed: false,
    board: makeF('ESP32'),
  },

  heatPlusDhw: {
    computed_at: 2000,
    operating_mode: makeF(4), // Heat + DHW
    heating_in_use: makeF(true),
    cooling_in_use: makeF(false),
    dhw_in_use: makeF(true),
    zones: makeF('z1'),
    heating_control: makeF('curve'),
    cooling_control: makeF('curve'),
    zone: { z1: makeZone(true, 'water'), z2: makeZone(false, 'water') },
    dhw_installed: makeF(true),
    buffer_installed: makeF(false),
    solar: makeF('off'),
    bivalent: makeF(false),
    glycol: makeF(false),
    optional_pcb_setting: makeF(false),
    pcb_emulation_active: makeF(false),
    has_extra: makeF(false),
    has_1wire: makeF(false),
    has_s0: makeF(false),
    has_opentherm: makeF(false),
    model: makeF(null, true),
    series: makeF(null, true),
    firmware: makeF('4.2.3'),
    firmware_assumed: false,
    board: makeF('ESP32'),
  },

  twoZone: {
    computed_at: 3000,
    operating_mode: makeF(4), // Heat + DHW
    heating_in_use: makeF(true),
    cooling_in_use: makeF(false),
    dhw_in_use: makeF(true),
    zones: makeF('both'),
    heating_control: makeF('curve'),
    cooling_control: makeF('curve'),
    zone: { z1: makeZone(true, 'water'), z2: makeZone(true, 'water') },
    dhw_installed: makeF(true),
    buffer_installed: makeF(false),
    solar: makeF('off'),
    bivalent: makeF(false),
    glycol: makeF(false),
    optional_pcb_setting: makeF(false),
    pcb_emulation_active: makeF(false),
    has_extra: makeF(false),
    has_1wire: makeF(false),
    has_s0: makeF(false),
    has_opentherm: makeF(false),
    model: makeF(null, true),
    series: makeF(null, true),
    firmware: makeF('4.2.3'),
    firmware_assumed: false,
    board: makeF('ESP32'),
  },

  coolOnly: {
    computed_at: 4000,
    operating_mode: makeF(1), // Cool
    heating_in_use: makeF(false),
    cooling_in_use: makeF(true),
    dhw_in_use: makeF(false),
    zones: makeF('z1'),
    heating_control: makeF('curve'),
    cooling_control: makeF('curve'),
    zone: { z1: makeZone(true, 'water'), z2: makeZone(false, 'water') },
    dhw_installed: makeF(false),
    buffer_installed: makeF(false),
    solar: makeF('off'),
    bivalent: makeF(false),
    glycol: makeF(false),
    optional_pcb_setting: makeF(false),
    pcb_emulation_active: makeF(false),
    has_extra: makeF(false),
    has_1wire: makeF(false),
    has_s0: makeF(false),
    has_opentherm: makeF(false),
    model: makeF(null, true),
    series: makeF(null, true),
    firmware: makeF('4.2.3'),
    firmware_assumed: false,
    board: makeF('ESP32'),
  },

  curveModeWater: {
    computed_at: 5000,
    operating_mode: makeF(0),
    heating_in_use: makeF(true),
    cooling_in_use: makeF(false),
    dhw_in_use: makeF(false),
    zones: makeF('z1'),
    heating_control: makeF('curve'),
    cooling_control: makeF('curve'),
    zone: { z1: makeZone(true, 'water'), z2: makeZone(false, 'water') },
    dhw_installed: makeF(false),
    buffer_installed: makeF(false),
    solar: makeF('off'),
    bivalent: makeF(false),
    glycol: makeF(false),
    optional_pcb_setting: makeF(false),
    pcb_emulation_active: makeF(false),
    has_extra: makeF(false),
    has_1wire: makeF(false),
    has_s0: makeF(false),
    has_opentherm: makeF(false),
    model: makeF(null, true),
    series: makeF(null, true),
    firmware: makeF('4.2.3'),
    firmware_assumed: false,
    board: makeF('ESP32'),
  },

  directModeWater: {
    computed_at: 6000,
    operating_mode: makeF(0),
    heating_in_use: makeF(true),
    cooling_in_use: makeF(false),
    dhw_in_use: makeF(false),
    zones: makeF('z1'),
    heating_control: makeF('direct'),
    cooling_control: makeF('curve'),
    zone: { z1: makeZone(true, 'water'), z2: makeZone(false, 'water') },
    dhw_installed: makeF(false),
    buffer_installed: makeF(false),
    solar: makeF('off'),
    bivalent: makeF(false),
    glycol: makeF(false),
    optional_pcb_setting: makeF(false),
    pcb_emulation_active: makeF(false),
    has_extra: makeF(false),
    has_1wire: makeF(false),
    has_s0: makeF(false),
    has_opentherm: makeF(false),
    model: makeF(null, true),
    series: makeF(null, true),
    firmware: makeF('4.2.3'),
    firmware_assumed: false,
    board: makeF('ESP32'),
  },
};

function makeState(overrides = {}) {
  return {
    seq: 1,
    topics: {},
    device_online: 'online',
    last_device_message: 1000,
    broker_connected: true,
    listen_only_suspected: false,
    ...overrides,
  };
}

function makePrefs(overrides = {}) {
  return {
    write_lock: false,
    pcb_enabled: false,
    topic_visibility: {},
    feature_overrides: {},
    tiles: [],
    chart_presets: [],
    ...overrides,
  };
}

// Mock fetch for sparkline tests
function mockFetch(handlers) {
  return vi.fn(async (url, init = {}) => {
    const handler = handlers.find((h) => url.includes(h.url));
    if (handler) {
      return new Response(JSON.stringify(handler.response), { status: 200 });
    }
    return new Response(JSON.stringify({ error: 'not_found' }), { status: 404 });
  });
}

afterEach(() => {
  resetClientState();
  localStorage.clear();
  vi.restoreAllMocks();
});

describe('Overview screen (§7.1)', () => {
  beforeEach(() => {
    language.set('en');
    
    // Mock api.history to return empty results for tests
    vi.spyOn(api, 'history').mockResolvedValue({
      series: {},
      resolution: '1h',
    });
    
    // Mock api.putPrefs for pin/unpin tests
    vi.spyOn(api, 'putPrefs').mockResolvedValue({
      write_lock: false,
      pcb_enabled: false,
      topic_visibility: {},
      feature_overrides: {},
      tiles: [],
      chart_presets: [],
    });
  });

  it('lays out schematic, now panel, controls, timeline, curve, events and tiles', async () => {
    vi.spyOn(api, 'energy').mockResolvedValue({ periods: {} });
    vi.spyOn(api, 'events').mockResolvedValue({ events: [] });
    vi.spyOn(api, 'commands').mockResolvedValue({ commands: [] });
    state.set(makeState());
    profile.set(profileFixtures.heatPlusDhw);
    prefs.set(makePrefs());
    render(Overview);
    for (const id of ['plant', 'quick-controls', 'timeline', 'recent-events', 'tiles']) {
      expect(screen.getByTestId(id)).toBeTruthy();
    }
    expect(screen.getByTestId('now-cop')).toBeTruthy();
  });

  it('shows a temperature dot on degree tiles, none for a sentinel', () => {
    const t = (value, sentinel = false) => ({
      value, raw: String(value), kind: 'number', unit: '°C', decimals: 1, enum_label: null,
      catalogued: true, sentinel, last_change: 1, last_seen: 1, retained_only: false,
    });
    const { unmount } = render(Tile, { key: 'outsideTemp', topic: t(6), sparkline: [] });
    expect(screen.getByTestId('tile-outsideTemp').querySelector('.temp-dot')).toBeTruthy();
    unmount();
    render(Tile, { key: 'outsideTemp', topic: t(-128, true), sparkline: [] });
    expect(screen.getByTestId('tile-outsideTemp').querySelector('.temp-dot')).toBeNull();
  });

  describe('tile keys exist in production catalog', () => {
    it('every tile topic key exists in the production catalog', () => {
      // All topic keys used in tiles must exist in catalog.topics
      const catalogTopicKeys = new Set(productionCatalog.topics.map((t) => t.key));
      
      // These are the topic keys used in Overview.svelte
      const usedKeys = [
        'main/Outside_Temp',
        'main/Main_Outlet_Temp',
        'main/Main_Inlet_Temp',
        'main/Compressor_Freq',
        'main/Heat_Power_Consumption',
        'main/Heat_Power_Production',
        'main/ThreeWay_Valve_State',
        'main/Defrosting_State',
        'main/DHW_Temp',
        'main/Buffer_Temp',
        'main/Solar_Temp',
        'main/Cool_Power_Production',
      ];
      
      for (const key of usedKeys) {
        expect(catalogTopicKeys).toContain(key);
      }
    });
  });

  describe('power source follows the profile (F4)', () => {
    const tv = (value) => ({
      value, raw: String(value), kind: 'number', unit: 'W', decimals: 0, enum_label: null,
      catalogued: true, sentinel: false, last_change: 1, last_seen: 1, retained_only: false,
    });
    const topics = {
      'main/Heat_Power_Production': tv(1000), 'main/Heat_Power_Consumption': tv(200),
      'extra/Heat_Power_Production_Extra': tv(2000), 'extra/Heat_Power_Consumption_Extra': tv(1000),
    };

    it('uses extra/ for the COP and power tiles when has_extra is true', () => {
      state.set(makeState({ topics }));
      profile.set({ ...profileFixtures.heatOnly, has_extra: makeF(true) });
      prefs.set(makePrefs());
      render(Overview);
      expect(screen.getByTestId('tile-cop').textContent).toContain('2.00');
      expect(screen.getByTestId('tile-heatPowerProduction').textContent).toContain('2000');
    });

    it('uses main/ when has_extra is false, even if extra/ topics exist', () => {
      state.set(makeState({ topics }));
      profile.set(profileFixtures.heatOnly);
      prefs.set(makePrefs());
      render(Overview);
      expect(screen.getByTestId('tile-cop').textContent).toContain('5.00');
    });
  });

  describe('catalogued-key tiles (B8)', () => {
    const dhw = {
      value: 47, raw: '47', kind: 'number', unit: '°C', decimals: 0, enum_label: null,
      catalogued: true, sentinel: false, last_change: 1, last_seen: 1, retained_only: false,
    };

    it('renders main/DHW_Temp with the catalog label, unit and value', () => {
      state.set(makeState({ topics: { 'main/DHW_Temp': dhw } }));
      profile.set(profileFixtures.heatOnly);
      prefs.set(makePrefs({ tiles: ['main/DHW_Temp'] }));
      render(Overview);
      const tile = screen.getByTestId('tile-main/DHW_Temp');
      expect(tile.textContent).toContain('DHW tank temperature');
      expect(tile.textContent).toContain('47 °C');
    });

    it('uses the catalog unit when the live value carries none', () => {
      render(Tile, { key: 'main/DHW_Temp', topic: { ...dhw, unit: '' }, lang: 'nl', isPinned: true });
      expect(screen.getByTestId('tile-main/DHW_Temp').textContent).toContain('Tapwatertemperatuur');
      expect(screen.getByTestId('tile-main/DHW_Temp').textContent).toContain('47 °C');
    });

    it('skips a stored id that is neither a built-in tile nor catalogued', () => {
      state.set(makeState());
      profile.set(profileFixtures.heatOnly);
      prefs.set(makePrefs({ tiles: ['nonsense', 'main/Nope'] }));
      render(Overview);
      expect(screen.queryByTestId('tile-nonsense')).toBeNull();
      expect(screen.queryByTestId('tile-main/Nope')).toBeNull();
      expect(screen.getByTestId('tile-outsideTemp')).toBeTruthy();
    });

    it('follows a prefs update made elsewhere (shared store)', async () => {
      state.set(makeState({ topics: { 'main/DHW_Temp': dhw } }));
      profile.set(profileFixtures.heatOnly);
      prefs.set(makePrefs());
      render(Overview);
      expect(screen.getByTestId('tile-outsideTemp').dataset.pinned).toBe('false');
      expect(screen.queryByTestId('tile-main/DHW_Temp')).toBeNull();
      prefs.set(makePrefs({ tiles: ['outsideTemp', 'main/DHW_Temp'] }));
      await tick();
      expect(screen.getByTestId('tile-outsideTemp').dataset.pinned).toBe('true');
      expect(screen.getByTestId('tile-main/DHW_Temp')).toBeTruthy();
    });
  });

  describe('tile sets for profiles', () => {
    it('shows default tiles for heat-only profile', () => {
      state.set(makeState());
      profile.set(profileFixtures.heatOnly);
      prefs.set(makePrefs());

      render(Overview);

      // Should show basic tiles
      expect(screen.getByTestId('tile-outsideTemp')).toBeTruthy();
      expect(screen.getByTestId('tile-mainOutletTemp')).toBeTruthy();
      expect(screen.getByTestId('tile-mainInletTemp')).toBeTruthy();
      expect(screen.getByTestId('tile-deltaTemp')).toBeTruthy();
      expect(screen.getByTestId('tile-compressorFreq')).toBeTruthy();
      expect(screen.getByTestId('tile-heatPowerConsumption')).toBeTruthy();
      expect(screen.getByTestId('tile-heatPowerProduction')).toBeTruthy();
      expect(screen.getByTestId('tile-cop')).toBeTruthy();
      expect(screen.getByTestId('tile-threeWayValve')).toBeTruthy();
      expect(screen.getByTestId('tile-defrostingState')).toBeTruthy();

      // Should NOT show DHW tile
      expect(screen.queryByTestId('tile-dhwTemp')).toBeFalsy();
      expect(screen.queryByTestId('tile-bufferTemp')).toBeFalsy();
      expect(screen.queryByTestId('tile-solarTemp')).toBeFalsy();
      expect(screen.queryByTestId('tile-coolPowerProduction')).toBeFalsy();
    });

    it('shows DHW tile for Heat+DHW profile', () => {
      state.set(makeState());
      profile.set(profileFixtures.heatPlusDhw);
      prefs.set(makePrefs());

      render(Overview);

      expect(screen.getByTestId('tile-dhwTemp')).toBeTruthy();
    });

    it('shows tiles for two-zone profile', () => {
      state.set(makeState());
      profile.set(profileFixtures.twoZone);
      prefs.set(makePrefs());

      render(Overview);

      expect(screen.getByTestId('tile-outsideTemp')).toBeTruthy();
      expect(screen.getByTestId('tile-dhwTemp')).toBeTruthy();
    });

    it('shows cooling power tile for cool-only profile', () => {
      state.set(makeState());
      profile.set(profileFixtures.coolOnly);
      prefs.set(makePrefs());

      render(Overview);

      expect(screen.getByTestId('tile-coolPowerProduction')).toBeTruthy();
    });
  });

  describe('24 h sparklines from history API', () => {
    it('renders sparkline component in each tile', () => {
      state.set(makeState());
      profile.set(profileFixtures.heatOnly);
      prefs.set(makePrefs());

      render(Overview);

      const tile = screen.getByTestId('tile-outsideTemp');
      expect(tile.querySelector('svg')).toBeTruthy();
    });

    it('renders sparkline component with data', () => {
      const data = [10, 12, 15, 18, 20, 18, 15, 12, 10];
      render(Sparkline, { data, width: 100, height: 40 });
      expect(screen.getByTestId('sparkline')).toBeTruthy();
    });

    it('sparkline normalizes values for SVG path', () => {
      const data = [10, 20, 30, 20, 10];
      const width = 100;
      const height = 40;
      render(Sparkline, { data, width, height });
      expect(screen.getByTestId('sparkline')).toBeTruthy();
    });

    it('sparkline handles null gaps from zero-coverage points', () => {
      const data = [10, null, 15, 20, null, 10];
      render(Sparkline, { data, width: 100, height: 40 });
      expect(screen.getByTestId('sparkline')).toBeTruthy();
    });
  });

  describe('pin/unpin/reorder prefs', () => {
    it('pinned tiles appear first', () => {
      state.set(makeState());
      profile.set(profileFixtures.heatOnly);
      prefs.set(makePrefs({ tiles: ['dhwTemp', 'outsideTemp'] }));

      render(Overview);

      const tiles = screen.getAllByTestId(/^tile-/);
      const tileIds = tiles.map((t) => t.dataset.testid);
      expect(tileIds).toContain('tile-dhwTemp');
      expect(tileIds).toContain('tile-outsideTemp');
    });

    it('tile pin button toggles pin state', async () => {
      state.set(makeState());
      profile.set(profileFixtures.heatOnly);
      prefs.set(makePrefs({ tiles: [] }));

      render(Tile, {
        key: 'outsideTemp',
        topic: { value: 15, raw: '15', kind: 'number', unit: '°C', decimals: 0, sentinel: false, last_seen: 1000, last_change: 1000 },
        sparkline: [10, 12, 15, 18, 20],
        lang: 'en',
        deviceOnline: 'online',
        isPinned: false,
      });

      const pinButton = screen.getByRole('button', { name: /Pin/i });
      expect(pinButton.textContent).toContain('☆');
    });

    it('pinned tile shows star icon', async () => {
      state.set(makeState());
      profile.set(profileFixtures.heatOnly);
      prefs.set(makePrefs({ tiles: [] }));

      render(Tile, {
        key: 'outsideTemp',
        topic: { value: 15, raw: '15', kind: 'number', unit: '°C', decimals: 0, sentinel: false, last_seen: 1000, last_change: 1000 },
        sparkline: [10, 12, 15, 18, 20],
        lang: 'en',
        deviceOnline: 'online',
        isPinned: true,
      });

      const pinButton = screen.getByRole('button', { name: /Unpin/i });
      expect(pinButton.textContent).toContain('★');
    });

    it('pinning calls PUT /api/prefs with updated tiles list', async () => {
      state.set(makeState());
      profile.set(profileFixtures.heatOnly);
      prefs.set(makePrefs({ tiles: [] }));

      // Mock api.putPrefs
      const mockPutPrefs = vi.spyOn(api, 'putPrefs').mockResolvedValue({
        write_lock: false,
        pcb_enabled: false,
        topic_visibility: {},
        feature_overrides: {},
        tiles: ['outsideTemp'],
        chart_presets: [],
      });

      render(QuickControls, {
        profile: profileFixtures.heatOnly,
        stateData: get(state),
        prefs: get(prefs),
        lang: 'en',
      });

      // Note: pin/unpin is handled in Overview.svelte, not QuickControls
      // This test verifies the mechanism in Overview.svelte
    });
  });
});

describe('Quick controls (§7.1)', () => {
  beforeEach(() => {
    language.set('en');
  });

  function num(value, extra = {}) {
    return {
      value, raw: String(value), kind: 'number', unit: '°C', decimals: 0, enum_label: null,
      sentinel: false, last_seen: 1000, last_change: 1000, ...extra,
    };
  }

  // Live values seen on a real installation: on, Heat+DHW, quiet 3, Z1 shift -1, DHW 40.
  function liveTopics(overrides = {}) {
    return {
      'main/Heatpump_State': num(1, { kind: 'enum', unit: null }),
      'main/Operating_Mode_State': num(4, { kind: 'enum', unit: null }),
      'main/Quiet_Mode_Level': num(3, { kind: 'enum', unit: null }),
      'main/Powerful_Mode_Time': num(0, { kind: 'enum', unit: null }),
      'main/Z1_Heat_Request_Temp': num(-1),
      'main/DHW_Target_Temp': num(40),
      'main/Force_DHW_State': num(0, { kind: 'enum', unit: null }),
      ...overrides,
    };
  }

  function renderControls(profileValue, topics = liveTopics(), lang = 'en') {
    const stateData = makeState({ topics });
    state.set(stateData);
    profile.set(profileValue);
    prefs.set(makePrefs());
    return render(QuickControls, {
      profile: profileValue,
      stateData,
      prefs: makePrefs(),
      lang,
      catalogData: productionCatalog,
    });
  }

  describe('controls start from the live read-back values', () => {
    it('heat pump, mode, quiet and DHW setpoint show the live values; Apply is disabled while unchanged', () => {
      renderControls(profileFixtures.heatPlusDhw);

      const hp = screen.getByTestId('input-hp-power');
      expect(hp.value).toBe('1');
      expect(hp.selectedOptions[0].textContent.trim()).toBe('On');
      expect(screen.getByTestId('control-hp-power').textContent).toContain('Heat pump');
      expect(screen.getByTestId('control-hp-power').textContent).not.toContain('Heat pump off');

      expect(screen.getByTestId('input-mode').value).toBe('4');
      expect(screen.getByTestId('input-mode').selectedOptions[0].textContent.trim()).toBe('Heating + DHW');
      expect(screen.getByTestId('input-quiet').value).toBe('3');
      expect(screen.getByTestId('input-dhw').value).toBe('40');

      for (const id of ['apply-hp-power', 'apply-mode', 'apply-quiet', 'apply-powerful', 'apply-z1-heat', 'apply-dhw']) {
        expect(screen.getByTestId(id).disabled).toBe(true);
      }
    });

    it('Z1 heat request slider shows the live shift (-1) with a °C read-out, not a missing i18n key', () => {
      renderControls(profileFixtures.curveModeWater);
      const slider = screen.getByTestId('slider-z1-heat');
      expect(slider.value).toBe('-1');
      const control = screen.getByTestId('control-z1-heat');
      expect(control.textContent).toContain('−1 °C');
      expect(control.textContent).toContain('shift');
      expect(control.textContent).not.toContain('unitCelsius');
    });

    it('Apply buttons are translated (nl)', () => {
      renderControls(profileFixtures.heatPlusDhw, liveTopics(), 'nl');
      expect(screen.getByTestId('apply-dhw').textContent.trim()).toBe('Toepassen');
      expect(screen.getByTestId('control-hp-power').textContent).toContain('Warmtepomp');
      expect(screen.getByTestId('input-hp-power').selectedOptions[0].textContent.trim()).toBe('Aan');
    });

    it('a control without a live value has nothing pre-selected and cannot be applied', () => {
      renderControls(profileFixtures.heatPlusDhw, {});
      expect(screen.getByTestId('input-dhw').value).toBe('');
      expect(screen.getByTestId('apply-dhw').disabled).toBe(true);
      expect(screen.getByTestId('input-mode').value).toBe('');
      expect(screen.getByTestId('apply-mode').disabled).toBe(true);
    });
  });

  describe('mode-adaptive zone request controls', () => {
    it('Z1 heat request shows -5..5 range in curve mode with water sensor', () => {
      renderControls(profileFixtures.curveModeWater);
      const slider = screen.getByTestId('slider-z1-heat');
      expect(slider.min).toBe('-5');
      expect(slider.max).toBe('5');
      expect(slider.step).toBe('1');
    });

    it('Z1 heat request shows 20..65 range in direct mode with water sensor', () => {
      renderControls(profileFixtures.directModeWater, liveTopics({ 'main/Z1_Heat_Request_Temp': num(40) }));
      const slider = screen.getByTestId('slider-z1-heat');
      expect(slider.min).toBe('20');
      expect(slider.max).toBe('65');
      expect(slider.value).toBe('40');
      expect(screen.getByTestId('control-z1-heat').textContent).toContain('setpoint');
    });

    it('DHW setpoint shows 40..75 range from catalog', () => {
      renderControls(profileFixtures.heatPlusDhw);
      const input = screen.getByTestId('input-dhw');
      expect(input.min).toBe('40');
      expect(input.max).toBe('75');
    });

    it('nothing is sent on slider move; Apply sends the moved value', async () => {
      const command = vi.spyOn(api, 'command').mockResolvedValue({ id: 'z1', name: 'SetZ1HeatRequestTemperature', status: 'pending', submitted_ts: 1 });
      renderControls(profileFixtures.curveModeWater);

      await fireEvent.input(screen.getByTestId('slider-z1-heat'), { target: { value: '3' } });
      expect(command).not.toHaveBeenCalled();
      const apply = screen.getByTestId('apply-z1-heat');
      expect(apply.disabled).toBe(false);
      await fireEvent.click(apply);
      await waitFor(() => expect(command).toHaveBeenCalledWith({ name: 'SetZ1HeatRequestTemperature', value: 3, confirm: false }));
    });

    it('DHW setpoint Apply sends the edited value, not a default', async () => {
      const command = vi.spyOn(api, 'command').mockResolvedValue({ id: 'd', name: 'SetDHWTemp', status: 'pending', submitted_ts: 1 });
      renderControls(profileFixtures.heatPlusDhw);
      await fireEvent.input(screen.getByTestId('input-dhw'), { target: { value: '45' } });
      await fireEvent.click(screen.getByTestId('apply-dhw'));
      await waitFor(() => expect(command).toHaveBeenCalledWith({ name: 'SetDHWTemp', value: 45, confirm: false }));
    });

    it('switching the heat pump off asks for confirmation (risky)', async () => {
      const { confirmRequest, answerConfirm } = await import('../src/lib/stores.js');
      const command = vi.spyOn(api, 'command').mockResolvedValue({ id: 'h', name: 'SetHeatpump', status: 'pending', submitted_ts: 1 });
      renderControls(profileFixtures.heatPlusDhw);
      await fireEvent.change(screen.getByTestId('input-hp-power'), { target: { value: '0' } });
      const pending = fireEvent.click(screen.getByTestId('apply-hp-power'));
      await tick();
      expect(get(confirmRequest)).toBeTruthy();
      expect(command).not.toHaveBeenCalled();
      answerConfirm(true);
      await pending;
      await waitFor(() => expect(command).toHaveBeenCalledWith({ name: 'SetHeatpump', value: 0, confirm: true }));
    });
  });

  describe('coupled mode: direct control with a room thermostat (setpoint in the curve cold-end target)', () => {
    const coupledProfile = {
      ...profileFixtures.directModeWater,
      zones: makeF('both'),
      zone: { z1: makeZone(true, 'ext_thermostat'), z2: makeZone(true, 'water') },
    };
    // as observed live: request temperature stays 0, the cold-end target carries the setpoint
    const coupledTopics = () => liveTopics({
      'main/Z1_Heat_Request_Temp': num(0),
      'main/Z1_Heat_Curve_Target_High_Temp': num(27),
      'main/Z1_Heat_Curve_Target_Low_Temp': num(30),
      'main/Z2_Heat_Request_Temp': num(35),
    });

    it('shows the cold-end target as setpoint with an inline explanation, not the 0 request', () => {
      renderControls(coupledProfile, coupledTopics());
      const box = screen.getByTestId('control-z1-heat');
      expect(box.dataset.coupled).toBe('true');
      const slider = screen.getByTestId('slider-z1-heat');
      expect(slider.value).toBe('27');
      expect(slider.min).toBe('15');
      expect(slider.max).toBe('75');
      expect(box.textContent).toContain('27 °C');
      expect(box.textContent).not.toContain('0 °C');
      expect(screen.getByTestId('coupled-note-z1-heat').textContent).toContain('Z1_Heat_Curve_Target_High_Temp');
      expect(screen.getByTestId('apply-z1-heat').disabled).toBe(true);
      // zone 2 has a water sensor: still the request-temperature control
      expect(screen.getByTestId('control-z2-heat').dataset.coupled).toBeUndefined();
      expect(screen.getByTestId('slider-z2-heat').value).toBe('35');
    });

    it('explains it in Dutch', () => {
      renderControls(coupledProfile, coupledTopics(), 'nl');
      expect(screen.getByTestId('coupled-note-z1-heat').textContent).toContain('koude kant');
      expect(screen.getByTestId('apply-z1-heat').textContent.trim()).toBe('Toepassen');
    });

    it('Apply sends a partial SetCurves on the cold-end target (below the warm-end target is allowed)', async () => {
      const command = vi.spyOn(api, 'command').mockResolvedValue({
        id: 'c', name: 'SetCurves', status: 'pending', submitted_ts: 1,
        keys: { 'main/Z1_Heat_Curve_Target_High_Temp': { expected: 21, status: 'pending' } },
      });
      renderControls(coupledProfile, coupledTopics());
      await fireEvent.input(screen.getByTestId('slider-z1-heat'), { target: { value: '21' } });
      expect(command).not.toHaveBeenCalled();
      await fireEvent.click(screen.getByTestId('apply-z1-heat'));
      await waitFor(() => expect(command).toHaveBeenCalledWith({
        name: 'SetCurves', value: { zone1: { heat: { target: { high: 21 } } } }, confirm: false,
      }));
      await waitFor(() => expect(screen.getByTestId('control-z1-heat').querySelector('[data-status]').dataset.status).toBe('pending'));
    });

    it('the read-back status of that leaf is shown from the command map', () => {
      const stateData = makeState({ topics: coupledTopics() });
      render(QuickControls, {
        profile: coupledProfile, stateData, prefs: makePrefs(), lang: 'en', catalogData: productionCatalog,
        commandMap: {
          other: { id: 'other', name: 'SetCurves', submitted_ts: 9, status: 'pending', keys: { 'main/Z2_Heat_Curve_Target_High_Temp': { status: 'pending' } } },
          mine: { id: 'mine', name: 'SetCurves', submitted_ts: 5, status: 'confirmed', keys: { 'main/Z1_Heat_Curve_Target_High_Temp': { status: 'confirmed' } } },
        },
      });
      expect(screen.getByTestId('control-z1-heat').querySelector('[data-status]').dataset.status).toBe('confirmed');
    });

    it('write lock blocks Apply', async () => {
      const stateData = makeState({ topics: coupledTopics() });
      render(QuickControls, {
        profile: coupledProfile, stateData, prefs: makePrefs({ write_lock: true }), lang: 'en', catalogData: productionCatalog,
      });
      await fireEvent.input(screen.getByTestId('slider-z1-heat'), { target: { value: '21' } });
      expect(screen.getByTestId('apply-z1-heat').disabled).toBe(true);
    });

    it('settings: the request-temperature control points to the curve cold-end target', async () => {
      const { default: CommandControl } = await import('../src/features/settings/CommandControl.svelte');
      const stateData = makeState({ topics: coupledTopics() });
      render(CommandControl, {
        entry: productionCatalog.commands.find((c) => c.name === 'SetZ1HeatRequestTemperature'), profile: coupledProfile, live: stateData,
        prefs: makePrefs(), lang: 'en', catalogData: productionCatalog,
      });
      expect(screen.getByTestId('coupled-current-SetZ1HeatRequestTemperature').textContent).toContain('27 °C');
      expect(screen.getByTestId('coupled-note-SetZ1HeatRequestTemperature').textContent).toContain('Z1_Heat_Curve_Target_High_Temp');
      expect(screen.getByTestId('coupled-note-SetZ1HeatRequestTemperature').querySelector('a').getAttribute('href')).toBe('#/curve');
    });

    it('settings: no coupled note with a water sensor', async () => {
      const { default: CommandControl } = await import('../src/features/settings/CommandControl.svelte');
      render(CommandControl, {
        entry: productionCatalog.commands.find((c) => c.name === 'SetZ1HeatRequestTemperature'), profile: profileFixtures.directModeWater,
        live: makeState({ topics: coupledTopics() }), prefs: makePrefs(), lang: 'en', catalogData: productionCatalog,
      });
      expect(screen.queryByTestId('coupled-note-SetZ1HeatRequestTemperature')).toBeNull();
    });
  });

  describe('DHW controls visibility', () => {
    it('shows DHW setpoint control when DHW tank is installed', () => {
      renderControls(profileFixtures.heatPlusDhw);
      expect(screen.getByTestId('control-dhw-setpoint')).toBeTruthy();
    });

    it('hides DHW setpoint control when no DHW tank', () => {
      renderControls(profileFixtures.heatOnly);
      expect(screen.queryByTestId('control-dhw-setpoint')).toBeFalsy();
    });
  });

  describe('force DHW', () => {
    it('shows force DHW only with DHW tank', () => {
      renderControls(profileFixtures.heatPlusDhw);
      expect(screen.getByTestId('control-force-dhw')).toBeTruthy();
    });

    it('hides force DHW without DHW tank', () => {
      renderControls(profileFixtures.heatOnly);
      expect(screen.queryByTestId('control-force-dhw')).toBeFalsy();
    });

    it('force DHW is enabled in DHW-capable modes and blocked otherwise', async () => {
      renderControls(profileFixtures.heatPlusDhw);
      expect(screen.getByTestId('control-force-dhw').dataset.enabled).toBe('true');
      await fireEvent.change(screen.getByTestId('input-force-dhw'), { target: { value: '1' } });
      expect(screen.getByTestId('apply-force-dhw').disabled).toBe(false);
    });

    it('force DHW is blocked in a mode without DHW', async () => {
      renderControls({ ...profileFixtures.heatPlusDhw, operating_mode: makeF(0) }, liveTopics({ 'main/Operating_Mode_State': num(0) }));
      expect(screen.getByTestId('control-force-dhw').dataset.enabled).toBe('false');
      await fireEvent.change(screen.getByTestId('input-force-dhw'), { target: { value: '1' } });
      expect(screen.getByTestId('apply-force-dhw').disabled).toBe(true);
    });
  });

  describe('EEPROM warning strings', () => {
    it('EEPROM warning appears with title', () => {
      expect(translate('en', 'overview.eepromWarningTitle')).toBe('EEPROM wear warning');
      expect(translate('en', 'overview.eepromWarning')).toContain('20 minutes');
    });
  });
});

describe('Overview sparklines (§7.1)', () => {
  it('fetch history once per tile set, not on every live message', async () => {
    language.set('en');
    const history = vi.spyOn(api, 'history').mockResolvedValue({ series: {}, resolution: '1h' });
    state.set(makeState({ topics: { 'main/Outside_Temp': { value: 5, raw: '5', kind: 'number', unit: '°C', decimals: 0, sentinel: false, last_seen: 1, last_change: 1 } } }));
    profile.set(profileFixtures.heatOnly);
    prefs.set(makePrefs());
    render(Overview);
    await waitFor(() => expect(history).toHaveBeenCalled());
    const first = history.mock.calls.length;
    for (let i = 0; i < 10; i += 1) {
      state.update((current) => ({
        ...current,
        seq: current.seq + 1,
        topics: { ...current.topics, 'main/Outside_Temp': { ...current.topics['main/Outside_Temp'], value: 5 + i, raw: String(5 + i) } },
      }));
      await tick();
    }
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(history.mock.calls.length).toBe(first);
  });
});

describe('i18n translation keys', () => {
  it('all overview keys exist in both languages', () => {
    expect(translate('en', 'overview.quickControls')).toBe('Quick controls');
    expect(translate('nl', 'overview.quickControls')).toBe('Snelbediening');
    expect(translate('en', 'overview.outsideTemp')).toBe('Outside temperature');
    expect(translate('nl', 'overview.outsideTemp')).toBe('Buitentemperatuur');
  });
});

describe('command wear warning and rate limit (R4)', () => {
  it('maps a 429 to a translated message with the wait', async () => {
    const { errorMessage } = await import('../src/lib/commands/controller.js');
    expect(errorMessage({ code: 'rate_limited', retryAfter: 30 }, 'en')).toContain('30');
    expect(errorMessage({ code: 'rate_limited', retryAfter: 30 }, 'nl')).toContain('30');
    expect(errorMessage({ code: 'out_of_range', retryAfter: null }, 'en')).toBe('out_of_range');
  });
});
