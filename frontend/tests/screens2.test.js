import { afterEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import productionCatalog from '../../backend/heishamon_dashboard/catalog.json';
import { encode, resolveRange, validate } from '../src/lib/encoding.js';
import { api } from '../src/lib/api.js';
import {
  changedValue,
  commandGate,
  curvesFromLive,
  draftValue,
  isAction,
  isRisky,
  jsonDiff,
} from '../src/features/settings/grouping.js';
import {
  commands,
  confirmRequest,
  language,
  prefs,
  profile,
  resetClientState,
  state,
  system,
} from '../src/lib/stores.js';
import Log from '../src/features/log/LogScreen.svelte';
import Settings from '../src/features/settings/SettingsScreen.svelte';
import System from '../src/features/system/SystemScreen.svelte';
import Topics from '../src/features/topics/TopicsScreen.svelte';

function field(value, unknown = false, stale = false) {
  return { value, unknown, stale };
}

function makeProfile(overrides = {}) {
  return {
    computed_at: 1,
    operating_mode: field(0),
    heating_in_use: field(true),
    cooling_in_use: field(false),
    dhw_in_use: field(false),
    zones: field('z1'),
    heating_control: field('curve'),
    cooling_control: field('curve'),
    zone: {
      z1: { active: field(true), sensor: field('water'), heat_control: field('curve'), cool_control: field('curve') },
      z2: { active: field(false), sensor: field('water'), heat_control: field('curve'), cool_control: field('curve') },
    },
    dhw_installed: field(false),
    buffer_installed: field(false),
    solar: field('off'),
    bivalent: field(false),
    glycol: field(false),
    optional_pcb_setting: field(false),
    pcb_emulation_active: field(false),
    has_extra: field(false),
    has_1wire: field(false),
    has_s0: field(false),
    has_opentherm: field(false),
    model: field(null, true),
    series: field(null, true),
    firmware: field('3.2.3'),
    firmware_assumed: false,
    board: field('board'),
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

function makeState(topics = {}, overrides = {}) {
  return {
    seq: 1,
    topics,
    device_online: 'online',
    broker_connected: true,
    listen_only_suspected: false,
    last_device_message: 1_700_000_000_000,
    ...overrides,
  };
}

function install({ profileValue, prefsValue, stateValue, systemValue = null }) {
  resetClientState();
  language.set('en');
  profile.set(profileValue);
  prefs.set(prefsValue);
  state.set(stateValue);
  commands.set({});
  system.set(systemValue);
}

function topicValue(value, raw, extra = {}) {
  return {
    value,
    raw,
    kind: 'number',
    unit: '°C',
    decimals: 0,
    enum_label: null,
    catalogued: true,
    sentinel: false,
    last_change: 1_700_000_000_000,
    last_seen: 1_700_000_000_000,
    retained_only: false,
    ...extra,
  };
}

const inventoryEntries = [
  ...productionCatalog.commands.map((entry) => ({ id: entry.name, entry })),
  ...productionCatalog.inputs.map((entry) => ({ id: entry.path, entry })),
];

const inventoryProfile = makeProfile({
  operating_mode: field(4),
  heating_in_use: field(true),
  cooling_in_use: field(true),
  dhw_in_use: field(true),
  zones: field('both'),
  dhw_installed: field(true),
  buffer_installed: field(true),
  solar: field('buffer'),
  bivalent: field(true),
  optional_pcb_setting: field(true),
  pcb_emulation_active: field(true),
  has_extra: field(true),
  has_s0: field(true),
  has_opentherm: field(true),
  firmware: field('4.2.3'),
  firmware_assumed: false,
});

const inventoryPrefs = makePrefs({ pcb_enabled: true });
const inventoryState = makeState();

/** A valid value for an entry, entered by the user in the test (no live value exists). */
function sampleValue(entry, profileValue) {
  if (entry.type === 'json') {
    return { zone1: { heat: { target: { high: 35, low: 25 }, outside: { high: 15, low: -5 } } } };
  }
  if (entry.type === 'bool') {
    const allowed = entry.allowed ?? [0, 1];
    return allowed.includes(1) ? 1 : allowed[0];
  }
  if (Array.isArray(entry.allowed) && entry.allowed.length) return entry.allowed[0];
  const range = resolveRange(entry, profileValue);
  return range?.min ?? 0;
}

/** Type a value into a settings control the way a user would. */
async function enter(id, value) {
  const element = screen.getByTestId(`value-${id}`);
  const text = typeof value === 'object' ? JSON.stringify(value) : String(value);
  if (element.tagName === 'SELECT') await fireEvent.change(element, { target: { value: text } });
  else await fireEvent.input(element, { target: { value: text } });
  await tick();
}

describe('settings, topics, log, system (§7.5–§7.8)', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('§7.5 categories irrelevant to the profile are collapsed but present, and §6 firmware_too_old disables a command', async () => {
    install({
      profileValue: makeProfile(),
      prefsValue: makePrefs(),
      stateValue: makeState(),
    });
    const put = vi.spyOn(api, 'putPrefs').mockResolvedValue(makePrefs());
    render(Settings, { catalogData: productionCatalog });
    await tick();

    expect(put).not.toHaveBeenCalled();
    for (const id of ['dhw', 'sterilization', 'bivalent', 'opentherm', 's0']) {
      const category = screen.getByTestId(`category-${id}`);
      expect(category.tagName).toBe('DETAILS');
      expect(category.dataset.collapsed).toBe('true');
      expect(category.open).toBe(false);
    }
    for (const id of ['operation', 'zones', 'heaters', 'pump', 'quiet']) {
      const category = screen.getByTestId(`category-${id}`);
      expect(category.open).toBe(true);
    }
    expect(screen.getByTestId('control-SetDHWTemp')).toBeTruthy();
    expect(screen.queryByTestId('category-pcb')).toBeNull();
    expect(screen.queryByTestId('control-SetPoolTemp')).toBeNull();

    const row = screen.getByTestId('control-SetSterilizationTemp');
    expect(row.dataset.gate).toBe('firmware_too_old');
    expect(row.textContent).toContain('firmware_too_old');
    expect(screen.getByTestId('apply-SetSterilizationTemp').disabled).toBe(true);
  });

  it('§7.5 Optional PCB appears only when enabled, with the H74 note, and SetPoolTemp accepts 20.5 (§4.4)', async () => {
    install({
      profileValue: makeProfile({
        pcb_emulation_active: field(true),
        firmware: field('4.2.3'),
      }),
      prefsValue: makePrefs({ pcb_enabled: true }),
      stateValue: makeState(),
    });
    const command = vi.spyOn(api, 'command').mockResolvedValue({
      id: 'pool-1',
      name: 'SetPoolTemp',
      status: 'pending',
      payload: '20.5',
      submitted_ts: 1,
    });
    render(Settings, { catalogData: productionCatalog });

    const note = screen.getByTestId('h74-note');
    expect(note.textContent).toContain('H74');
    expect(note.textContent).toContain('service settings');
    expect(screen.getByTestId('category-pcb')).toBeTruthy();

    const input = screen.getByTestId('value-SetPoolTemp');
    await fireEvent.input(input, { target: { value: '20.5' } });
    await tick();
    expect(input.dataset.valid).toBe('true');
    expect(command).not.toHaveBeenCalled();
    expect(encode('dec1', 20.5)).toEqual({ ok: true, payload: '20.5' });

    const pending = fireEvent.click(screen.getByTestId('apply-SetPoolTemp'));
    await tick();
    expect(get(confirmRequest)).toBeTruthy();
    const { answerConfirm } = await import('../src/lib/stores.js');
    answerConfirm(true);
    await pending;
    await waitFor(() => expect(command).toHaveBeenCalledWith({
      name: 'SetPoolTemp',
      value: 20.5,
      confirm: true,
    }));
  });

  it('§10 a pending POST yields to the commands store when the same id is confirmed', async () => {
    install({
      profileValue: makeProfile(),
      prefsValue: makePrefs(),
      stateValue: makeState(),
    });
    const submitted = 1_700_000_100_000;
    vi.spyOn(api, 'command').mockResolvedValue({
      id: 'quiet-1',
      name: 'SetQuietMode',
      status: 'pending',
      payload: '0',
      submitted_ts: submitted,
    });
    render(Settings, { catalogData: productionCatalog });
    await enter('SetQuietMode', 0);
    await fireEvent.click(screen.getByTestId('apply-SetQuietMode'));
    await waitFor(() => expect(screen.getByTestId('command-status').dataset.status).toBe('pending'));

    commands.set({
      'quiet-1': {
        id: 'quiet-1',
        name: 'SetQuietMode',
        status: 'confirmed',
        payload: '0',
        submitted_ts: submitted,
      },
    });
    await waitFor(() => expect(screen.getByTestId('command-status').dataset.status).toBe('confirmed'));
  });

  it('§10 a pending POST yields to the commands store when the same id is failed', async () => {
    install({
      profileValue: makeProfile(),
      prefsValue: makePrefs(),
      stateValue: makeState(),
    });
    const submitted = 1_700_000_200_000;
    vi.spyOn(api, 'command').mockResolvedValue({
      id: 'quiet-2',
      name: 'SetQuietMode',
      status: 'pending',
      payload: '0',
      submitted_ts: submitted,
    });
    render(Settings, { catalogData: productionCatalog });
    await enter('SetQuietMode', 0);
    await fireEvent.click(screen.getByTestId('apply-SetQuietMode'));
    await waitFor(() => expect(screen.getByTestId('command-status').dataset.status).toBe('pending'));

    commands.set({
      'quiet-2': {
        id: 'quiet-2',
        name: 'SetQuietMode',
        status: 'failed',
        payload: '0',
        submitted_ts: submitted,
        detail: 'readback timeout',
      },
    });
    await waitFor(() => expect(screen.getByTestId('command-status').dataset.status).toBe('failed'));
  });

  it('§4.3 ignore suggestions never write prefs without a click; §7.6 shows traffic, raw topics, and hides empty sections', async () => {
    const now = 1_700_000_000_000;
    const day = 24 * 60 * 60 * 1000;
    const outside = productionCatalog.topics.find((topic) => topic.key === 'main/Outside_Temp');
    const top15 = productionCatalog.topics.find((topic) => topic.id === 'TOP15');
    const sentinelTopic = productionCatalog.topics.find((topic) => topic.key === 'main/Main_Inlet_Temp')
      ?? productionCatalog.topics.find((topic) => topic.key.startsWith('main/') && topic.key !== outside.key && topic.key !== top15.key);
    const optionalTopic = productionCatalog.topics.find((topic) => topic.key.startsWith('optional/'));
    const rawKey = 'misc/Not_A_Catalog_Topic';
    expect(outside && top15 && sentinelTopic && optionalTopic).toBeTruthy();

    install({
      profileValue: makeProfile({
        has_extra: field(true),
        optional_pcb_setting: field(false),
      }),
      prefsValue: makePrefs(),
      stateValue: makeState({
        [outside.key]: topicValue(7, '7'),
        [top15.key]: topicValue(100, '100'),
        [sentinelTopic.key]: topicValue(-128, '-128', { sentinel: true, last_change: now - day - 1000 }),
        [optionalTopic.key]: topicValue(0, '0'),
        [rawKey]: topicValue(null, 'raw-payload', { kind: 'text', catalogued: false, unit: null }),
      }),
    });
    const put = vi.spyOn(api, 'putPrefs').mockImplementation(async (body) => body);
    vi.spyOn(api, 'history').mockResolvedValue({ resolution: 'raw', partial: false, series: {} });
    render(Topics, { catalogData: productionCatalog, now });
    await tick();
    await Promise.resolve();

    expect(put).not.toHaveBeenCalled();
    const catalogued = screen.getByTestId(`topic-${outside.key}`);
    expect(catalogued.dataset.catalogued).toBe('true');
    expect(catalogued.textContent).toContain(outside.label.en);
    expect(screen.getByTestId('section-main')).toBeTruthy();
    expect(screen.queryByTestId('section-extra')).toBeNull();
    expect(screen.queryByTestId('section-1wire')).toBeNull();
    expect(screen.queryByTestId('section-s0')).toBeNull();

    const raw = screen.getByTestId(`topic-${rawKey}`);
    expect(raw.dataset.catalogued).toBe('false');
    expect(raw.dataset.raw).toBe('true');
    expect(screen.getByTestId(`raw-${rawKey}`).textContent).toContain('raw-payload');
    expect(screen.getByTestId('section-misc')).toBeTruthy();
    expect(screen.getByTestId('section-optional')).toBeTruthy();
    expect(screen.getByTestId(`suggest-${sentinelTopic.key}`)).toBeTruthy();
    expect(screen.getByTestId(`suggest-${top15.key}`)).toBeTruthy();
    expect(screen.getByTestId(`suggest-${optionalTopic.key}`)).toBeTruthy();

    await fireEvent.click(screen.getByTestId(`suggest-${sentinelTopic.key}`));
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(put.mock.calls[0][0].topic_visibility).toEqual({ [sentinelTopic.key]: 'ignored' });
    expect(put.mock.calls[0][0].topic_visibility[top15.key]).toBeUndefined();
  });

  it('§7.8 the flush-now button calls POST /api/system/flush', async () => {
    install({
      profileValue: makeProfile(),
      prefsValue: makePrefs(),
      stateValue: makeState(),
      systemValue: {
        broker_connected: true,
        device_online: 'online',
        firmware: '4.2.3',
        firmware_assumed: false,
        stats: { version: '4.2.3', uptime: 12 },
        listen_only_suspected: false,
        db_bytes: 10,
        last_flush_ts: null,
        last_flush_ok: true,
        last_flush_error: null,
        flush_interval_s: 900,
        buffer: { samples: 1, sample_bytes: 2, protected: 0 },
        dropped: { samples: 0, ingest: 0 },
      },
    });
    vi.spyOn(api, 'system').mockResolvedValue(null);
    const flush = vi.spyOn(api, 'flush').mockResolvedValue({ flush_id: 'flush-1' });
    render(System);
    await tick();
    expect(flush).not.toHaveBeenCalled();
    expect(screen.getByTestId('system-interval').textContent).toContain('900');
    await fireEvent.click(screen.getByTestId('flush-now'));
    await waitFor(() => expect(flush).toHaveBeenCalledTimes(1));
    expect(flush.mock.calls[0]).toEqual([]);
    expect((await screen.findByTestId('flush-id')).textContent).toContain('flush-1');
  });

  it('§7.7 the log lists commands and events and can filter them', async () => {
    install({
      profileValue: makeProfile(),
      prefsValue: makePrefs(),
      stateValue: makeState(),
    });
    vi.spyOn(api, 'commands').mockResolvedValue({
      commands: [{ id: 'c1', name: 'SetQuietMode', status: 'confirmed', payload: '1', submitted_ts: 5, detail: null }],
    });
    vi.spyOn(api, 'events').mockResolvedValue({
      events: [{ ts: 6, kind: 'defrost_start', detail: { topic: 'main/Defrosting_State' } }],
    });
    render(Log);
    expect(await screen.findByTitle('SetQuietMode')).toBeTruthy();
    expect(screen.getByText('Defrost started')).toBeTruthy();
    const eventTime = screen.getByTestId('log-event-row').querySelector('time');
    expect(eventTime.textContent).toMatch(/1970/);
    expect(eventTime.textContent).not.toMatch(/am|pm/i);
    expect(screen.getByTestId('log-event-row').textContent).toContain('topic: main/Defrosting_State');
    await fireEvent.change(screen.getByTestId('log-filter'), { target: { value: 'events' } });
    await tick();
    expect(screen.queryByTitle('SetQuietMode')).toBeNull();
    expect(screen.getByText('Defrost started')).toBeTruthy();
  });
});

describe('§7.5 A.2 inventory: every command and input submits POST /api/command', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders a control for every catalog command and input', () => {
    install({
      profileValue: inventoryProfile,
      prefsValue: inventoryPrefs,
      stateValue: inventoryState,
    });
    render(Settings, { catalogData: productionCatalog });
    expect(document.querySelectorAll('[data-testid^="control-"]').length).toBe(inventoryEntries.length);
    expect(productionCatalog.commands.length + productionCatalog.inputs.length).toBe(inventoryEntries.length);
  });

  it.each(inventoryEntries)('§7.5 A.2 $id posts the encoded value', async ({ id, entry }) => {
    install({
      profileValue: inventoryProfile,
      prefsValue: inventoryPrefs,
      stateValue: inventoryState,
    });
    const value = sampleValue(entry, inventoryProfile);
    const encoded = validate(entry, value, inventoryProfile);
    expect(encoded.ok).toBe(true);
    expect(commandGate(entry, {
      profile: inventoryProfile,
      prefs: inventoryPrefs,
      live: inventoryState,
      value,
    })).toBeNull();
    const command = vi.spyOn(api, 'command').mockResolvedValue({
      id: 'inv',
      name: id,
      status: 'pending',
      payload: encoded.payload,
      submitted_ts: 1,
    });
    render(Settings, { catalogData: productionCatalog });
    if (!isAction(entry)) {
      expect(screen.getByTestId(`apply-${id}`).disabled).toBe(true);
      await enter(id, value);
    }
    expect(screen.getByTestId(`apply-${id}`).disabled).toBe(false);
    const pending = fireEvent.click(screen.getByTestId(`apply-${id}`));
    await tick();
    if (isRisky(entry, value)) {
      expect(get(confirmRequest)).toBeTruthy();
      const { answerConfirm } = await import('../src/lib/stores.js');
      answerConfirm(true);
    }
    await pending;
    await waitFor(() => expect(command).toHaveBeenCalledTimes(1));
    const body = command.mock.calls[0][0];
    expect(body).toEqual({ name: id, value, confirm: isRisky(entry, value) });
    expect(encode(entry.type, body.value)).toEqual({ ok: true, payload: encoded.payload });
  });
});

describe('§6/§7.5 drafts start from the live read-back value', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  const curveTopics = {
    'main/Z1_Heat_Curve_Target_High_Temp': topicValue(30, '30'),
    'main/Z1_Heat_Curve_Target_Low_Temp': topicValue(30, '30'),
    'main/Z1_Heat_Curve_Outside_High_Temp': topicValue(3, '3'),
    'main/Z1_Heat_Curve_Outside_Low_Temp': topicValue(-10, '-10'),
  };

  function liveState() {
    return makeState({
      'main/DHW_Target_Temp': topicValue(40, '40'),
      'main/Operating_Mode_State': topicValue(4, '4', {
        kind: 'enum', unit: null, enum_label: { en: 'Heating + DHW', nl: 'Verwarmen + tapwater' },
      }),
      'main/Quiet_Mode_Level': topicValue(3, '3', { kind: 'enum', unit: null }),
      'main/Heatpump_State': topicValue(1, '1', { kind: 'enum', unit: null }),
      'main/Z1_Heat_Request_Temp': topicValue(-1, '-1'),
      'main/Holiday_Mode_State': topicValue(2, '2', { kind: 'enum', unit: null }),
      ...curveTopics,
    });
  }

  function installLive() {
    install({
      profileValue: makeProfile({ dhw_installed: field(true), firmware: field('4.2.3'), operating_mode: field(4) }),
      prefsValue: makePrefs(),
      stateValue: liveState(),
    });
  }

  it('draftValue returns the read-back value, null when unknown, and the current curves for SetCurves', () => {
    const live = liveState();
    const byName = (name) => productionCatalog.commands.find((entry) => entry.name === name);
    expect(draftValue(byName('SetDHWTemp'), live)).toBe(40);
    expect(draftValue(byName('SetOperationMode'), live)).toBe(4);
    expect(draftValue(byName('SetQuietMode'), live)).toBe(3);
    expect(draftValue(byName('SetHeatpump'), live)).toBe(1);
    expect(draftValue(byName('SetZ1HeatRequestTemperature'), live)).toBe(-1);
    expect(draftValue(byName('SetHolidayMode'), live)).toBe(1);
    expect(draftValue(byName('SetMaxPumpDuty'), live)).toBeNull();
    expect(draftValue(byName('SetPump'), live)).toBeNull();
    expect(draftValue(byName('SetForceDefrost'), live)).toBe(1);
    expect(draftValue(byName('SetCurves'), live)).toEqual({
      zone1: { heat: { target: { high: 30, low: 30 }, outside: { high: 3, low: -10 } } },
    });
    expect(curvesFromLive(makeState())).toEqual({});
  });

  it('changedValue is null for an unchanged draft and sends only changed curve leaves', () => {
    const dhw = productionCatalog.commands.find((entry) => entry.name === 'SetDHWTemp');
    const curves = productionCatalog.commands.find((entry) => entry.name === 'SetCurves');
    expect(changedValue(dhw, 40, 40)).toBeNull();
    expect(changedValue(dhw, 40, 45)).toBe(45);
    expect(changedValue(dhw, null, 45)).toBe(45);
    const base = curvesFromLive(liveState());
    expect(changedValue(curves, base, base)).toBeNull();
    const next = structuredClone(base);
    next.zone1.heat.target.high = 32;
    expect(changedValue(curves, base, next)).toEqual({ zone1: { heat: { target: { high: 32 } } } });
    expect(jsonDiff({ a: 1 }, { a: 1, b: { c: 2 } })).toEqual({ b: { c: 2 } });
  });

  it('settings inputs show the live values and Apply stays disabled until the draft changes', async () => {
    installLive();
    const command = vi.spyOn(api, 'command').mockResolvedValue({ id: 'x', name: 'SetDHWTemp', status: 'pending', submitted_ts: 1 });
    render(Settings, { catalogData: productionCatalog });
    await tick();

    expect(screen.getByTestId('value-SetDHWTemp').value).toBe('40');
    expect(screen.getByTestId('apply-SetDHWTemp').disabled).toBe(true);

    const mode = screen.getByTestId('value-SetOperationMode');
    expect(mode.tagName).toBe('SELECT');
    expect(mode.value).toBe('4');
    expect([...mode.options].map((option) => option.textContent.trim())).toContain('Heating + DHW');
    expect(screen.getByTestId('apply-SetOperationMode').disabled).toBe(true);

    expect(screen.getByTestId('value-SetQuietMode').value).toBe('3');
    expect(screen.getByTestId('apply-SetQuietMode').disabled).toBe(true);

    const curve = screen.getByTestId('value-SetCurves');
    expect(JSON.parse(curve.value)).toEqual({ zone1: { heat: { target: { high: 30, low: 30 }, outside: { high: 3, low: -10 } } } });
    expect(screen.getByTestId('apply-SetCurves').disabled).toBe(true);

    // No read-back: nothing is pre-selected, Apply needs an explicit choice.
    expect(screen.getByTestId('value-SetMaxPumpDuty').value).toBe('');
    expect(screen.getByTestId('apply-SetMaxPumpDuty').disabled).toBe(true);

    for (const button of document.querySelectorAll('[data-testid^="apply-"]')) {
      if (!button.disabled) await fireEvent.click(button);
    }
    // Only single-value actions (force defrost, reset, ...) are enabled; they ask for confirmation
    // or post their only value — never a made-up setting.
    for (const call of command.mock.calls) {
      const entry = productionCatalog.commands.find((item) => item.name === call[0].name);
      expect(isAction(entry)).toBe(true);
    }
  });

  it('editing a draft enables Apply and posts the edited value; curves post only the changed leaf', async () => {
    installLive();
    const command = vi.spyOn(api, 'command').mockImplementation(async (body) => ({ id: body.name, name: body.name, status: 'pending', submitted_ts: 1 }));
    render(Settings, { catalogData: productionCatalog });
    await tick();

    await enter('SetDHWTemp', 45);
    expect(screen.getByTestId('apply-SetDHWTemp').disabled).toBe(false);
    await fireEvent.click(screen.getByTestId('apply-SetDHWTemp'));
    await waitFor(() => expect(command).toHaveBeenCalledWith({ name: 'SetDHWTemp', value: 45, confirm: false }));

    await enter('SetDHWTemp', 40);
    expect(screen.getByTestId('apply-SetDHWTemp').disabled).toBe(true);

    const curve = JSON.parse(screen.getByTestId('value-SetCurves').value);
    curve.zone1.heat.target.high = 33;
    await enter('SetCurves', curve);
    await fireEvent.click(screen.getByTestId('apply-SetCurves'));
    await waitFor(() => expect(command).toHaveBeenCalledWith({
      name: 'SetCurves',
      value: { zone1: { heat: { target: { high: 33 } } } },
      confirm: false,
    }));
  });
});

describe('§7.6 topic sparklines do not refetch on live messages', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('history is fetched once (batched) and not again when values change', async () => {
    const topics = {};
    for (const topic of productionCatalog.topics.slice(0, 60)) topics[topic.key] = topicValue(1, '1');
    install({ profileValue: makeProfile(), prefsValue: makePrefs(), stateValue: makeState(topics) });
    const history = vi.spyOn(api, 'history').mockResolvedValue({ resolution: 'raw', partial: false, series: {} });
    render(Topics, { catalogData: productionCatalog });
    await waitFor(() => expect(history).toHaveBeenCalledTimes(3)); // 60 topics, batches of 20 (server limit)
    for (let i = 0; i < 20; i += 1) {
      const key = productionCatalog.topics[i % 60].key;
      state.update((current) => ({
        ...current,
        seq: current.seq + 1,
        topics: { ...current.topics, [key]: topicValue(i, String(i)) },
      }));
      await tick();
    }
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(history).toHaveBeenCalledTimes(3);
    expect(history.mock.calls[0][0].topics).toHaveLength(20);
  });
});
