/** Labels for the event and command logs, shared by the Log screen and the Overview card. */
import { translate } from './i18n/index.js';
import { commandByName } from './catalog.js';

export function kindLabel(kind, lang) {
  const key = `log.kind_${kind}`;
  const text = translate(lang, key);
  return text === key ? kind : text;
}

export function commandLabel(name, lang) {
  const entry = commandByName(name);
  return entry?.label?.[lang] || entry?.label?.en || name;
}

export function detailText(detail) {
  if (detail == null) return '';
  if (typeof detail !== 'object') return String(detail);
  return Object.entries(detail)
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([key, value]) => `${key}: ${typeof value === 'object' ? JSON.stringify(value) : value}`)
    .join(', ');
}

const FAIL_KINDS = new Set(['error_change', 'flush_failed', 'buffer_overflow', 'events_dropped', 'ingest_dropped', 'command_rejected', 'device_offline', 'broker_disconnected']);

export function eventTone(kind) {
  if (kind === 'defrost_start' || kind === 'defrost_end') return 'defrost';
  return FAIL_KINDS.has(kind) ? 'fail' : 'neutral';
}

export function commandTone(status) {
  if (status === 'confirmed' || status === 'sent' || status === 'noop') return 'ok';
  if (status === 'pending' || status === 'retried') return 'pending';
  if (status === 'failed') return 'fail';
  return 'neutral';
}

/** The newest `n` events and commands, merged, for the Overview card. */
export function recentItems(events = [], commands = [], lang = 'en', n = 6) {
  const items = [
    ...events.map((e) => ({ ts: e.ts, title: kindLabel(e.kind, lang), detail: detailText(e.detail), tone: eventTone(e.kind) })),
    ...commands.map((c) => ({
      ts: c.submitted_ts,
      title: `${commandLabel(c.name, lang)} → ${c.payload}`,
      detail: `${c.name} = ${c.payload} · ${c.status}`,
      tone: commandTone(c.status),
    })),
  ];
  return items.sort((a, b) => b.ts - a.ts).slice(0, n);
}
