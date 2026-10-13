import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { render, screen, waitFor } from '@testing-library/svelte';
import Overview from '../src/features/overview/OverviewScreen.svelte';
import { api } from '../src/lib/api.js';
import {
  applyHello,
  applyServerMessage,
  prefs,
  resetClientState,
  state,
  updatePrefs,
} from '../src/lib/stores.js';

const EMPTY_PREFS = {
  write_lock: false,
  pcb_enabled: false,
  topic_visibility: {},
  feature_overrides: {},
  tiles: [],
  chart_presets: [],
};

function hello(topics = {}) {
  applyHello({ type: 'hello', state: { seq: 1, topics, device_online: 'online' }, profile: null });
}

function value(topic, raw, extra = {}) {
  applyServerMessage({ type: 'value', seq: 2, topic, raw: String(raw), value: Number(raw), ts: 100, retained: false, ...extra });
}

afterEach(() => {
  resetClientState();
  vi.restoreAllMocks();
});

describe('live value normalisation (F5)', () => {
  it('updates the enum label when the value changes', () => {
    hello({ 'main/Operating_Mode_State': { value: 0, raw: '0', last_change: 1, last_seen: 1, retained_only: false } });
    value('main/Operating_Mode_State', 0);
    expect(get(state).topics['main/Operating_Mode_State'].enum_label.en).toBe('Heat');
    value('main/Operating_Mode_State', 1);
    expect(get(state).topics['main/Operating_Mode_State'].enum_label.en).toBe('Cool');
  });

  it('clears the sentinel flag when a real value arrives', () => {
    hello();
    value('main/Outside_Temp', -128);
    expect(get(state).topics['main/Outside_Temp'].sentinel).toBe(true);
    value('main/Outside_Temp', 7);
    expect(get(state).topics['main/Outside_Temp'].sentinel).toBe(false);
  });

  it('catalogues a topic first seen after hello', () => {
    hello();
    value('main/Outside_Temp', 35);
    const topic = get(state).topics['main/Outside_Temp'];
    expect(topic.catalogued).toBe(true);
    expect(topic.kind).not.toBe('text');
    expect(topic.unit).toBeTruthy();
    value('main/Not_In_Catalog', 5);
    expect(get(state).topics['main/Not_In_Catalog'].catalogued).toBe(false);
  });
});

describe('updatePrefs (F8)', () => {
  it('keeps two edits from different components', async () => {
    const server = { ...EMPTY_PREFS };
    vi.spyOn(api, 'putPrefs').mockImplementation(async (body) => {
      await new Promise((resolve) => setTimeout(resolve, 5));
      Object.assign(server, JSON.parse(JSON.stringify(body)));
      return JSON.parse(JSON.stringify(server));
    });
    prefs.set({ ...EMPTY_PREFS });
    await Promise.all([
      updatePrefs({ write_lock: true }),
      updatePrefs((cur) => ({ feature_overrides: { ...cur.feature_overrides, dhw: 'show' } })),
    ]);
    expect(server.write_lock).toBe(true);
    expect(server.feature_overrides).toEqual({ dhw: 'show' });
    expect(get(prefs).write_lock).toBe(true);
    expect(get(prefs).feature_overrides).toEqual({ dhw: 'show' });
  });
});

describe('Overview tile ids (F9)', () => {
  it('skips an unknown tile id without throwing', async () => {
    vi.spyOn(api, 'history').mockResolvedValue({ series: {} });
    prefs.set({ ...EMPTY_PREFS, tiles: ['no_such_tile'] });
    state.set({ seq: 1, topics: {}, device_online: 'online' });
    expect(() => render(Overview)).not.toThrow();
    await waitFor(() => expect(screen.queryByText('no_such_tile')).toBeNull());
  });
});

describe('no raw HTML (F10)', () => {
  it('has no {@html in frontend/src', () => {
    const hits = [];
    const walk = (dir) => {
      for (const name of readdirSync(dir)) {
        const path = join(dir, name);
        if (statSync(path).isDirectory()) walk(path);
        else if (readFileSync(path, 'utf8').includes('{@html')) hits.push(path);
      }
    };
    walk(join(import.meta.dirname, '..', 'src'));
    expect(hits).toEqual([]);
  });
});
