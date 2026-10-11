/** Settings grouping, drafts, and the client mirror of the §6 gates. */

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

/** Place a catalog command or input in a §7.5 group. PCB commands stay in Optional PCB. */
export function specCategory(entry) {
  if (entry.pcb) return 'pcb';
  const path = entry.path || '';
  if (path.startsWith('s0/')) return 's0';
  if (path.startsWith('opentherm/')) return 'opentherm';
  const name = entry.name || '';
  if (name.includes('Sterilization')) return 'sterilization';
  if (name.includes('Bivalent')) return 'bivalent';
  if (name.includes('DHW')) return 'dhw';
  if (name.includes('Heater')) return 'heaters';
  if (/^Set(Z[12]|Zones|Floor)/.test(name)) return 'zones';
  if (name.includes('Quiet') || name.includes('Schedule')) return 'quiet';
  if (name.includes('Pump')) return 'pump';
  if (name.includes('Solar')) return 'solar';
  return 'operation';
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

export function draftValue(entry) {
  if (entry.type === 'json') {
    return {
      zone1: {
        heat: {
          target: { high: 35, low: 25 },
          outside: { high: 15, low: -5 },
        },
      },
    };
  }
  if (entry.type === 'bool') {
    const allowed = entry.allowed ?? [0, 1];
    return allowed.includes(1) ? 1 : allowed[0];
  }
  if (Array.isArray(entry.allowed) && entry.allowed.length) return entry.allowed[0];
  const range = entry.range;
  if (!range) return 0;
  const step = range.step ?? 1;
  const origin = range.min ?? 0;
  const steps = step ? Math.round((origin - origin) / step) : 0;
  let value = origin + steps * step;
  if (entry.type === 'int' || entry.type === 'int2' || entry.type === 'int12') value = Math.round(value);
  return value;
}

export function formatDraft(entry, value) {
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

export function usesSelect(entry) {
  if (entry.type === 'json' || entry.type === 'dec1' || entry.type === 'dec3') return false;
  if (entry.type === 'bool') return true;
  return Array.isArray(entry.allowed) && entry.allowed.length > 0 && entry.allowed.length <= 8;
}

export function selectOptions(entry) {
  if (entry.type === 'bool') return entry.allowed ?? [0, 1];
  return entry.allowed ?? [];
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

export function recentWrites(commandMap, name, now) {
  const cutoff = now - 60 * 60 * 1000;
  return Object.values(commandMap ?? {}).filter((row) => (
    row?.name === name
    && (row.status === 'confirmed' || row.status === 'retried' || row.status === 'failed')
    && (row.submitted_ts ?? 0) >= cutoff
  )).length;
}

export function groupCatalog(catalog) {
  const buckets = new Map(SPEC_CATEGORIES.map((category) => [category.id, []]));
  for (const entry of catalog?.commands ?? []) {
    buckets.get(specCategory(entry))?.push(entry);
  }
  for (const entry of catalog?.inputs ?? []) {
    buckets.get(specCategory(entry))?.push(entry);
  }
  return SPEC_CATEGORIES.map((category) => ({ ...category, items: buckets.get(category.id) ?? [] }));
}
