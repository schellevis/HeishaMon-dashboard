import { get, writable } from 'svelte/store';
import { fullPrefs } from '../features/settings/prefs.js';
import { api } from './api.js';
import { LANGUAGE_KEY, initialLanguage } from './i18n/index.js';
import { normalizeTopicValue } from './domain/normalize.js';
import { createWsClient, wsUrl } from './ws.js';

import { ROUTES } from '../app/registry.js';
export { ROUTES };

export const state = writable(null);
export const profile = writable(null);
export const prefs = writable(null);
export const commands = writable({});
export const system = writable(null);
export const language = writable('en');
export const route = writable('overview');
export const confirmRequest = writable(null);

export function parseRoute(hash) {
  const name = String(hash ?? '').replace(/^#\/?/, '').split(/[/?#]/)[0];
  return ROUTES.includes(name) ? name : 'overview';
}

export function setRouteFromHash(hash) {
  route.set(parseRoute(hash));
}

export function loadLanguage(storage = globalThis.localStorage, nav = globalThis.navigator) {
  const lang = initialLanguage(storage, nav);
  language.set(lang);
  return lang;
}

export function bindLanguagePersistence(storage = globalThis.localStorage) {
  return language.subscribe((lang) => {
    if ((lang === 'en' || lang === 'nl') && storage?.setItem) storage.setItem(LANGUAGE_KEY, lang);
  });
}

export function resetClientState() {
  state.set(null);
  profile.set(null);
  prefs.set(null);
  commands.set({});
  system.set(null);
  language.set('en');
  route.set('overview');
  confirmRequest.set(null);
}

export function applyHello(msg) {
  const snapshot = msg.state;
  if (snapshot?.topics) {
    const topics = {};
    for (const [key, entry] of Object.entries(snapshot.topics)) {
      topics[key] = { ...entry, ...normalizeTopicValue(key, entry.raw, entry.value, entry) };
    }
    state.set({ ...snapshot, topics });
  } else {
    state.set(snapshot);
  }
  profile.set(msg.profile);
}

function applyValue(msg) {
  state.update((current) => {
    if (!current) return current;
    const prev = current.topics?.[msg.topic];
    const changed = !prev || prev.raw !== msg.raw;
    const next = {
      ...prev,
      ...normalizeTopicValue(msg.topic, msg.raw, msg.value, prev),
      value: msg.value,
      raw: msg.raw,
      last_seen: msg.ts,
      last_change: changed ? msg.ts : prev.last_change,
      retained_only: prev ? (msg.retained ? prev.retained_only : false) : Boolean(msg.retained),
    };
    return {
      ...current,
      seq: msg.seq,
      topics: { ...current.topics, [msg.topic]: next },
    };
  });
}

function applyProfile(msg) {
  profile.set(msg.profile);
}

function applyCommand(msg) {
  const command = msg.command;
  if (!command?.id) return;
  commands.update((current) => ({ ...current, [command.id]: command }));
}

function applyOnline(msg) {
  state.update((current) => {
    if (!current) return current;
    return {
      ...current,
      seq: msg.seq,
      device_online: msg.device,
      broker_connected: msg.broker,
      last_device_message: msg.ts ?? current.last_device_message,
    };
  });
}

function applyEvent(msg) {
  const event = msg.event;
  if (!event) return;
  if (event.kind === 'flush_failed') {
    const detail = event.detail;
    const message = typeof detail === 'string' ? detail : detail?.message || detail?.error || '';
    system.update((current) => ({
      ...(current ?? {}),
      last_flush_ok: false,
      last_flush_error: message,
      last_flush_ts: event.ts,
    }));
  } else if (event.kind === 'flush') {
    system.update((current) => ({
      ...(current ?? {}),
      last_flush_ok: true,
      last_flush_error: null,
      last_flush_ts: event.ts,
    }));
  }
}

export function applyServerMessage(msg) {
  switch (msg?.type) {
    case 'hello':
      applyHello(msg);
      break;
    case 'value':
      applyValue(msg);
      break;
    case 'profile':
      applyProfile(msg);
      break;
    case 'command':
      applyCommand(msg);
      break;
    case 'online':
      applyOnline(msg);
      break;
    case 'event':
      applyEvent(msg);
      break;
    default:
      break;
  }
}

let prefsQueue = Promise.resolve();

/**
 * Serialised prefs write. `patch` is an object or `(current) => object`; it is merged over the latest
 * prefs when its turn comes, so edits from different components never overwrite each other. The server
 * response is written back into the `prefs` store.
 */
export function updatePrefs(patch) {
  const run = async () => {
    const current = fullPrefs(get(prefs));
    const delta = typeof patch === 'function' ? patch(current) : patch;
    const saved = await api.putPrefs({ ...current, ...delta });
    if (saved) prefs.set(saved);
    return saved;
  };
  const result = prefsQueue.then(run, run);
  prefsQueue = result.catch(() => {});
  return result;
}

export function askConfirm(detail) {
  return new Promise((resolve) => {
    confirmRequest.set({ ...detail, resolve });
  });
}

export function answerConfirm(accepted) {
  let current;
  confirmRequest.update((value) => {
    current = value;
    return null;
  });
  current?.resolve(accepted);
}

/** Open the live socket and load prefs plus system, which hello does not carry. */
export function startRealtime() {
  const client = createWsClient({
    url: wsUrl(),
    onHello: applyHello,
    onMessage: applyServerMessage,
  });
  client.start();
  api.prefs().then((value) => prefs.set(value)).catch(() => {});
  api.system().then((value) => system.set(value)).catch(() => {});
  return () => client.stop();
}
