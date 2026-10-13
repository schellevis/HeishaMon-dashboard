/** Settings grouping, drafts, and the client mirror of the §6 gates. */

import { curveLeaf } from '../../lib/domain/rules.js';
import { activeFirmware, cmpVersion, parseFirmware } from './firmware.js';

/** Spec §7.5 category order. Optional PCB is shown only when the pref is on. */
export const SPEC_CATEGORIES = [
  { id: 'operation', labelKey: 'settings.catOperation' },
  { id: 'zones', labelKey: 'settings.catZones' },
  { id: 'dhw', labelKey: 'settings.catDhw' },
  { id: 'sterilization', labelKey: 'settings.catSterilization' },
  { id: 'heaters', labelKey: 'settings.catHeaters' },
  { id: 'bivalent', labelKey: 'settings.catBivalent' },
  { id: 'solar', labelKey: 'settings.catSolar' },
  { id: 'pump', labelKey: 'settings.catPump' },
  { id: 'quiet', labelKey: 'settings.catQuiet' },
  { id: 'opentherm', labelKey: 'settings.catOpentherm' },
  { id: 's0', labelKey: 'settings.catS0' },
  { id: 'pcb', labelKey: 'settings.catPcb' },
];

export function entryId(entry) {
  return entry.name || entry.path;
}

function explicit(profile, field) {
  if (!profile) return undefined;
  const node = profile[field];
  if (!node || typeof node !== 'object' || !('value' in node)) return undefined;
  if (node.unknown || node.stale) return undefined;
  return node.value;
}

/** Irrelevant categories stay in the page, collapsed (spec §7.5). Unknown profile fields stay open. */
export function categoryRelevant(id, profile) {
  if (id === 'dhw' || id === 'sterilization') {
    const value = explicit(profile, 'dhw_installed');
    return value === undefined ? true : value === true;
  }
  if (id === 'bivalent') {
    const value = explicit(profile, 'bivalent');
    return value === undefined ? true : value === true;
  }
  if (id === 'solar') {
    const value = explicit(profile, 'solar');
    return value === undefined ? true : value !== 'off';
  }
  if (id === 's0') {
    const value = explicit(profile, 'has_s0');
    return value === undefined ? true : value === true;
  }
  if (id === 'opentherm') {
    const value = explicit(profile, 'has_opentherm');
    return value === undefined ? true : value === true;
  }
  return true;
}

const CURVE_ZONES = { zone1: 1, zone2: 2 };
const CURVE_MODES = ['heat', 'cool'];
const CURVE_LEAVES = [
  ['target', 'high'],
  ['target', 'low'],
  ['outside', 'high'],
  ['outside', 'low'],
];

function liveNumber(live, key) {
  const topic = live?.topics?.[key];
  if (!topic || topic.sentinel) return null;
  return typeof topic.value === 'number' && Number.isFinite(topic.value) ? topic.value : null;
}

/** The read-back topic shown as "current value" (first catalog read-back, else the input's own path). */
export function readbackKeyOf(entry, live = null) {
  if (entry.readback?.length) return entry.readback[0];
  if (entry.path && live?.topics?.[entry.path]) return entry.path;
  return null;
}

/** Current curves as `SetCurves` JSON, built from the read-back topics. Only leaves with a value are included. */
export function curvesFromLive(live) {
  const out = {};
  for (const [zone, z] of Object.entries(CURVE_ZONES)) {
    for (const mode of CURVE_MODES) {
      for (const [group, leaf] of CURVE_LEAVES) {
        const value = liveNumber(live, curveLeaf(z, mode, group, leaf));
        if (value == null || !Number.isInteger(value)) continue;
        out[zone] ??= {};
        out[zone][mode] ??= {};
        out[zone][mode][group] ??= {};
        out[zone][mode][group][leaf] = value;
      }
    }
  }
  return out;
}

/** Leaves of `next` that differ from `base` (partial `SetCurves` JSON); `{}` when nothing changed. */
export function jsonDiff(base, next) {
  if (next === null || typeof next !== 'object' || Array.isArray(next)) return next;
  const out = {};
  for (const [key, value] of Object.entries(next)) {
    const before = base && typeof base === 'object' ? base[key] : undefined;
    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      const inner = jsonDiff(before, value);
      if (inner && Object.keys(inner).length) out[key] = inner;
    } else if (value !== before) {
      out[key] = value;
    }
  }
  return out;
}

/** A trigger with a single allowed value (e.g. force defrost) is an action, not a setting. */
export function isAction(entry) {
  return entry.class === 'trigger' || (Array.isArray(entry.allowed) && entry.allowed.length === 1);
}

/**
 * The draft a control starts from: the live read-back value, never a made-up default (spec §6, §7.5).
 * Returns `null` when the current value is unknown, so the user has to choose one.
 * Actions start from their only allowed value.
 */
export function draftValue(entry, live = null) {
  if (entry.type === 'json') return curvesFromLive(live);
  if (isAction(entry)) return entry.allowed?.[0] ?? 1;
  const key = readbackKeyOf(entry, live);
  if (!key) return null;
  let value = liveNumber(live, key);
  if (value == null) return null;
  if (entry.compare === 'holiday' && value > 1) value = 1;
  if (Array.isArray(entry.allowed) && !entry.allowed.includes(value)) return null;
  return value;
}

/**
 * The value to send for a draft: for `SetCurves` only the changed leaves.
 * `null` when the draft is identical to the current value (Apply stays disabled).
 */
export function changedValue(entry, baseline, value) {
  if (value == null) return null;
  if (isAction(entry)) return value;
  if (entry.type === 'json') {
    const diff = jsonDiff(baseline ?? {}, value);
    return diff && Object.keys(diff).length ? diff : null;
  }
  if (baseline != null && Number(baseline) === Number(value)) return null;
  return value;
}

export function formatDraft(entry, value) {
  if (value == null) return '';
  if (entry.type === 'json') return JSON.stringify(value);
  return String(value);
}

export function parseDraft(entry, text) {
  if (entry.type === 'json') {
    try {
      return JSON.parse(text);
    } catch {
      return null;
    }
  }
  if (typeof text === 'number') return text;
  const trimmed = String(text ?? '').trim();
  if (trimmed === '') return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

const SELECT_MAX = 8;

function enumerableRange(entry) {
  const range = entry.range;
  if (!range || entry.type === 'dec1' || entry.type === 'dec3' || entry.type === 'json') return null;
  if (range.min == null || range.max == null || range.min < 0) return null;
  const step = range.step || 1;
  const count = Math.floor((range.max - range.min) / step) + 1;
  if (count < 2 || count > SELECT_MAX) return null;
  return Array.from({ length: count }, (_, index) => range.min + index * step);
}

/** Values offered in a select, or `null` when a free (validated) number input fits better. */
export function selectValues(entry) {
  if (entry.type === 'json') return null;
  if (entry.type === 'bool') return entry.allowed ?? [0, 1];
  if (Array.isArray(entry.allowed) && entry.allowed.length) return entry.allowed;
  return enumerableRange(entry);
}

export function usesSelect(entry) {
  return selectValues(entry) !== null;
}

export function selectOptions(entry) {
  return selectValues(entry) ?? [];
}

/**
 * Label for one command value. Sources, in order: the read-back topic's catalog enum, the UI string table (`settings.value_<Name>_<v>`), On/Off for
 * booleans, and the number itself.
 * @param {object} entry catalog command
 * @param {number} value
 * @param {string} lang
 * @param {{topicByKey?: (key: string) => object | null, translate: Function}} helpers
 */
export function valueLabel(entry, value, lang, { topicByKey = () => null, translate }) {
  const key = String(value);
  const readback = entry.readback?.[0] ? topicByKey(entry.readback[0]) : null;
  const fromTopic = readback?.enum?.[key];
  if (fromTopic) return fromTopic[lang] || fromTopic.en || key;
  const tableKey = `settings.value_${entry.name || entry.path}_${key}`;
  const text = translate(lang, tableKey);
  if (text !== tableKey) return text;
  if (entry.type === 'bool' && (value === 0 || value === 1)) return translate(lang, value ? 'settings.on' : 'settings.off');
  return key;
}

/** Same risky rule as the backend command service (spec §6 step 2.9). */
export function isRisky(entry, value) {
  if (entry.class === 'trigger' || entry.class === 'retained_exception' || entry.pcb) return true;
  if (entry.name === 'SetHeatpump') return value === 0;
  return Boolean(entry.risky);
}

function fieldUsable(profile, path) {
  const parts = String(path).replace(/^profile\./, '').split('.');
  let current = profile;
  for (const part of parts) current = current?.[part];
  if (!current || typeof current !== 'object' || !('value' in current)) return false;
  return !current.unknown && !current.stale;
}

export function commandGate(entry, { profile = null, prefs = null, live = null, value = null } = {}) {
  if (live) {
    if (live.broker_connected === false) return 'broker_disconnected';
    if (live.device_online !== 'online') return 'device_offline';
  }
  if (prefs?.write_lock) return 'write_lock';
  if (entry.pcb) {
    if (!prefs?.pcb_enabled) return 'pcb_disabled';
    const pcb = profile?.pcb_emulation_active;
    if (!pcb || pcb.unknown || pcb.stale || pcb.value !== true) return 'pcb_emulation_inactive';
  }
  const have = activeFirmware(profile);
  const need = parseFirmware(entry.min_firmware).tuple;
  if (cmpVersion(need, have) > 0) return 'firmware_too_old';
  const requires = entry.applicability?.requires ?? [];
  if (requires.length && !entry.safe_under_unknown) {
    for (const path of requires) {
      if (!fieldUsable(profile, path)) return 'profile_unknown';
    }
  }
  if (entry.name === 'SetOperationMode' && (value === 7 || value === 8)) return 'read_only_value';
  return null;
}

export function groupCatalog(catalog) {
  const buckets = new Map(SPEC_CATEGORIES.map((category) => [category.id, []]));
  for (const entry of catalog?.commands ?? []) {
    buckets.get(entry.ui_group)?.push(entry);
  }
  for (const entry of catalog?.inputs ?? []) {
    buckets.get(entry.ui_group)?.push(entry);
  }
  return SPEC_CATEGORIES.map((category) => ({ ...category, items: buckets.get(category.id) ?? [] }));
}
