import { afterEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import { fireEvent, render, screen } from '@testing-library/svelte';
import App from '../src/app/App.svelte';
import Statusbar from '../src/app/Statusbar.svelte';
import ApplyButton from '../src/lib/ui/ApplyButton.svelte';
import CommandStatus from '../src/lib/ui/CommandStatus.svelte';
import ConfirmDialog from '../src/lib/ui/ConfirmDialog.svelte';
import { createApi } from '../src/lib/api.js';
import { api } from '../src/lib/api.js';
import { topicByKey, commandByName } from '../src/lib/catalog.js';
import { formatAge, presentTopic } from '../src/lib/format.js';
import {
  applyHello,
  applyServerMessage,
  commands,
  language,
  prefs,
  profile,
  resetClientState,
  route,
  state,
  system,
} from '../src/lib/stores.js';
import { createWsClient } from '../src/lib/ws.js';

class FakeSocket {
  static instances = [];

  constructor(url) {
    this.url = url;
    this.sent = [];
    FakeSocket.instances.push(this);
  }

  send(data) {
    this.sent.push(data);
  }

  close() {
    this.onclose?.();
  }

  open() {
    this.onopen?.();
  }

  emit(obj) {
    this.onmessage?.({ data: JSON.stringify(obj) });
  }
}

function hello(seq, topics = {}) {
  return {
    type: 'hello',
    seq,
    state: {
      seq,
      topics,
      device_online: 'online',
      last_device_message: 1_000,
      broker_connected: true,
      listen_only_suspected: false,
    },
    profile: { computed_at: seq },
  };
}

afterEach(() => {
  resetClientState();
  localStorage.clear();
  FakeSocket.instances = [];
  vi.restoreAllMocks();
});

describe('WebSocket client (§4.4)', () => {
  it('drops messages with seq ≤ hello.seq', () => {
    const seen = [];
    const dropped = [];
    const client = createWsClient({
      WebSocketImpl: FakeSocket,
      onHello: (msg) => seen.push(msg),
      onMessage: (msg) => seen.push(msg),
      onDrop: (msg) => dropped.push(msg.seq),
      schedule: () => 0,
    });
    client.start();
    const socket = FakeSocket.instances[0];
    socket.open();
    socket.emit({ type: 'value', seq: 1, topic: 'main/Outside_Temp', value: 1, raw: '1', ts: 1, retained: false });
    socket.emit(hello(5, { a: { value: 1, raw: '1' } }));
    socket.emit({ type: 'value', seq: 5, topic: 'a', value: 2, raw: '2', ts: 2, retained: false });
    socket.emit({ type: 'value', seq: 4, topic: 'a', value: 3, raw: '3', ts: 3, retained: false });
    socket.emit({ type: 'value', seq: 6, topic: 'a', value: 4, raw: '4', ts: 4, retained: false });

    expect(seen.map((msg) => msg.seq)).toEqual([5, 6]);
    expect(dropped).toEqual([1, 5, 4]);
    client.stop();
  });

  it('reconnect resyncs from hello and ignores the old socket', () => {
    const hellos = [];
    const messages = [];
    const scheduled = [];
    const client = createWsClient({
      WebSocketImpl: FakeSocket,
      onHello: (msg) => {
        hellos.push(msg);
        applyHello(msg);
      },
      onMessage: (msg) => messages.push(msg),
      schedule: (fn) => {
        scheduled.push(fn);
        return 1;
      },
    });
    client.start();
    const first = FakeSocket.instances[0];
    first.open();
    first.emit(hello(3, { a: { value: 1, raw: '1' } }));
    first.emit({ type: 'value', seq: 4, topic: 'a', value: 2, raw: '2', ts: 4, retained: false });
    first.close();
    expect(scheduled).toHaveLength(1);
    scheduled[0]();
    const second = FakeSocket.instances[1];
    second.open();
    first.emit({ type: 'value', seq: 99, topic: 'a', value: 9, raw: '9', ts: 9, retained: false });
    second.emit(hello(10, {}));
    second.emit({ type: 'value', seq: 8, topic: 'a', value: 8, raw: '8', ts: 8, retained: false });
    second.emit({ type: 'value', seq: 10, topic: 'a', value: 10, raw: '10', ts: 10, retained: false });
    second.emit({ type: 'value', seq: 11, topic: 'b', value: 11, raw: '11', ts: 11, retained: false });

    expect(hellos.map((msg) => msg.seq)).toEqual([3, 10]);
    expect(messages.map((msg) => msg.seq)).toEqual([4, 11]);
    expect(get(state).seq).toBe(10);
    expect(get(state).topics).toEqual({});
    client.stop();
  });
});

describe('stores', () => {
  it('applies value, profile, command, online and flush events', () => {
    applyHello(hello(1, {
      'main/Outside_Temp': {
        value: 10, raw: '10', kind: 'number', unit: '°C', decimals: 0,
        enum_label: null, catalogued: true, sentinel: false,
        last_change: 1, last_seen: 1, retained_only: true,
      },
    }));
    applyServerMessage({
      type: 'value', seq: 2, topic: 'main/Outside_Temp', value: 11, raw: '11', ts: 50, retained: false,
    });
    const topic = get(state).topics['main/Outside_Temp'];
    expect(topic.value).toBe(11);
    expect(topic.last_change).toBe(50);
    expect(topic.last_seen).toBe(50);
    expect(topic.retained_only).toBe(false);
    expect(get(state).seq).toBe(2);

    applyServerMessage({ type: 'profile', seq: 3, profile: { computed_at: 3 } });
    expect(get(profile).computed_at).toBe(3);

    applyServerMessage({
      type: 'command',
      seq: 4,
      command: { id: 'abc', name: 'SetDHWTemp', status: 'pending' },
    });
    expect(get(commands).abc.status).toBe('pending');
    applyServerMessage({
      type: 'online', seq: 5, device: 'offline', broker: false, ts: 80,
    });
    expect(get(state).device_online).toBe('offline');
    expect(get(state).broker_connected).toBe(false);

    applyServerMessage({
      type: 'event', seq: 6, event: { ts: 90, kind: 'flush_failed', detail: { message: 'disk full' } },
    });
    expect(get(system).last_flush_ok).toBe(false);
    expect(get(system).last_flush_error).toBe('disk full');
    applyServerMessage({
      type: 'event', seq: 7, event: { ts: 100, kind: 'flush', detail: {} },
    });
    expect(get(system).last_flush_ok).toBe(true);
    expect(get(system).last_flush_error).toBeNull();
  });
});

describe('API client (§4.4)', () => {
  it('calls the REST paths with JSON mutation bodies', async () => {
    const seen = [];
    const fetchImpl = vi.fn(async (url, init = {}) => {
      seen.push({ url, init });
      if (String(url).endsWith('/missing')) {
        return new Response(JSON.stringify({ error: 'unknown_command', message: 'no', detail: null }), { status: 404 });
      }
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    });
    const client = createApi({ fetch: fetchImpl });
    await client.state();
    await client.profile();
    await client.history({ topics: ['main/Outside_Temp', 'main/Error'], from: 1, to: 2, max_points: 10 });
    expect(client.historyCsvUrl({ topics: ['main/Outside_Temp'], from: 1, to: 2 })).toContain('/api/history.csv?');
    await client.command({ name: 'SetDHWTemp', value: 50, confirm: true });
    await client.commandStatus('abc');
    await client.commands({ since: 5, limit: 10 });
    await client.events({ since: 5, kind: 'flush', limit: 10 });
    await client.prefs();
    await client.putPrefs({
      write_lock: true, pcb_enabled: false, topic_visibility: {}, feature_overrides: {}, tiles: [], chart_presets: [],
    });
    await client.system();
    await client.overlay({ zone: 'z1', mode: 'heat', from: 1, to: 2 });
    await client.flush();
    await expect(client.commandStatus('missing')).rejects.toMatchObject({ status: 404, code: 'unknown_command' });

    const paths = seen.map((call) => `${call.init.method ?? 'GET'} ${call.url}`);
    expect(paths).toEqual([
      'GET /api/state',
      'GET /api/profile',
      'GET /api/history?topics=main%2FOutside_Temp%2Cmain%2FError&from=1&to=2&max_points=10',
      'POST /api/command',
      'GET /api/commands/abc',
      'GET /api/commands?since=5&limit=10',
      'GET /api/events?since=5&kind=flush&limit=10',
      'GET /api/prefs',
      'PUT /api/prefs',
      'GET /api/system',
      'GET /api/overlay?zone=z1&mode=heat&from=1&to=2',
      'POST /api/system/flush',
      'GET /api/commands/missing',
    ]);
    const post = seen.find((call) => call.url === '/api/command');
    expect(post.init.headers['content-type']).toBe('application/json');
    expect(JSON.parse(post.init.body)).toEqual({ name: 'SetDHWTemp', value: 50, confirm: true });
    expect(JSON.parse(seen.find((call) => call.url === '/api/system/flush').init.body)).toEqual({});
  });
});

describe('stale values (§9)', () => {
  const topic = {
    value: 21, raw: '21', kind: 'number', unit: '°C', decimals: 0,
    enum_label: null, catalogued: true, sentinel: false,
    last_change: 1_000, last_seen: 1_000, retained_only: false,
  };

  it('greys a value and shows its age only while the device is offline', () => {
    const offline = presentTopic(topic, { deviceOnline: 'offline', now: 1_000 + 125_000, lang: 'en' });
    expect(offline.greyed).toBe(true);
    expect(offline.className).toBe('value-stale');
    expect(offline.text).toBe('21 °C');
    expect(offline.ageText).toBe('2 min');
    expect(formatAge(125_000, 'en')).toBe('2 min');

    const online = presentTopic(topic, { deviceOnline: 'online', now: 1_000 + 125_000, lang: 'en' });
    expect(online.greyed).toBe(false);
    expect(online.className).toBe('');
    expect(online.ageText).toBe('');
  });
});

describe('shell', () => {
  it('routes to every screen and switches nav at 768 px', async () => {
    window.innerWidth = 1280;
    render(App);
    expect(screen.getByText('HeishaMon dashboard')).toBeTruthy();
    expect(screen.getByTestId('shell').dataset.layout).toBe('side');
    expect(screen.getByTestId('screen-overview')).toBeTruthy();

    await fireEvent.click(screen.getByTestId('nav-charts'));
    expect(get(route)).toBe('charts');
    expect(screen.getByTestId('screen-charts')).toBeTruthy();
    for (const id of ['energy', 'curve', 'settings', 'topics', 'log', 'system', 'overview']) {
      await fireEvent.click(screen.getByTestId(`nav-${id}`));
      expect(screen.getByTestId(`screen-${id}`)).toBeTruthy();
    }

    window.innerWidth = 390;
    window.dispatchEvent(new Event('resize'));
    await tick();
    expect(screen.getByTestId('shell').dataset.layout).toBe('bottom');
    window.innerWidth = 768;
    window.dispatchEvent(new Event('resize'));
    await tick();
    expect(screen.getByTestId('shell').dataset.layout).toBe('side');
  });

  it('shows every status-bar item', async () => {
    language.set('en');
    state.set({
      seq: 1,
      topics: {
        'main/Error': { value: 'H75', raw: 'H75', kind: 'text', sentinel: false, last_seen: 1_000, last_change: 1_000 },
        'main/Defrosting_State': { value: 0, raw: '0', sentinel: false, last_seen: 1_000, last_change: 1_000 },
        'main/ThreeWay_Valve_State': { value: 0, raw: '0', sentinel: false, last_seen: 1_000, last_change: 1_000 },
      },
      device_online: 'offline',
      last_device_message: 1_000,
      broker_connected: false,
      listen_only_suspected: false,
    });
    prefs.set({
      write_lock: false, pcb_enabled: false, topic_visibility: {}, feature_overrides: {}, tiles: [], chart_presets: [],
    });
    system.set({ last_flush_ok: false, last_flush_error: 'disk full' });
    profile.set({
      operating_mode: { value: 4, unknown: false, stale: false },
      heating_in_use: { value: true, unknown: false, stale: false },
      cooling_in_use: { value: false, unknown: false, stale: false },
      dhw_in_use: { value: true, unknown: false, stale: false },
    });

    render(Statusbar, { now: 61_000 });
    expect(screen.getByTestId('device-status').textContent).toContain('Offline');
    expect(screen.getByTestId('device-status').className).toContain('value-stale');
    expect(screen.getByTestId('broker-status').textContent).toContain('Broker disconnected');
    expect(screen.getByTestId('last-message').textContent).toContain('1 min');
    expect(screen.getByTestId('error-code').textContent).toContain('H75');
    expect(screen.getByTestId('operating-mode').textContent).toContain('Heat + DHW');
    expect(screen.getByTestId('activity').textContent).toContain('Heating');
    expect(screen.getByTestId('write-lock').textContent).toContain('Write lock');
    expect(screen.getByTestId('language-switch')).toBeTruthy();
    expect(screen.getByTestId('flush-error').textContent).toContain('disk full');

    vi.spyOn(api, 'putPrefs').mockResolvedValue({
      write_lock: true, pcb_enabled: false, topic_visibility: {}, feature_overrides: {}, tiles: [], chart_presets: [],
    });
    await fireEvent.click(screen.getByTestId('write-lock'));
    await vi.waitFor(() => {
      expect(get(prefs).write_lock).toBe(true);
    });

    await fireEvent.click(screen.getByTestId('lang-nl'));
    expect(get(language)).toBe('nl');
    expect(screen.getByTestId('activity').textContent).toContain('Verwarmen');
  });
});

describe('command controls', () => {
  it('Apply does not submit while disabled, and command status names the record state', async () => {
    const click = vi.fn();
    const { rerender } = render(ApplyButton, { label: 'Apply', disabled: true, onclick: click });
    await fireEvent.click(screen.getByTestId('apply'));
    expect(click).not.toHaveBeenCalled();
    await rerender({ label: 'Apply', disabled: false, onclick: click });
    await fireEvent.click(screen.getByTestId('apply'));
    expect(click).toHaveBeenCalledOnce();
  });

  it('renders each command status', () => {
    language.set('en');
    const { rerender } = render(CommandStatus, { status: 'pending' });
    for (const [status, label] of [
      ['pending', 'Pending'],
      ['retried', 'Retried'],
      ['confirmed', 'Confirmed'],
      ['sent', 'Sent'],
      ['noop', 'No change'],
      ['superseded', 'Superseded'],
      ['failed', 'Failed'],
    ]) {
      rerender({ status });
      expect(screen.getByTestId('command-status').dataset.status).toBe(status);
      expect(screen.getByTestId('command-status').textContent).toContain(label);
    }
  });

  it('confirm dialog resolves confirm and cancel', async () => {
    const onconfirm = vi.fn();
    const oncancel = vi.fn();
    render(ConfirmDialog, {
      open: true, title: 'Send this change?', body: 'Stored in memory.',
      confirmLabel: 'Confirm', cancelLabel: 'Cancel', onconfirm, oncancel,
    });
    expect(screen.getByRole('dialog')).toBeTruthy();
    await fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(oncancel).toHaveBeenCalledOnce();
    await fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    expect(onconfirm).toHaveBeenCalledOnce();
  });
});

describe('catalog access', () => {
  it('reads the fixture catalog only through catalog.js', () => {
    expect(topicByKey('main/Outside_Temp').label.en).toBe('Outside temperature');
    expect(topicByKey('main/Outside_Temp').label.nl).toBe('Buitentemperatuur');
    expect(commandByName('SetDHWTemp').type).toBe('int');
    expect(commandByName('missing')).toBeNull();
  });
});
