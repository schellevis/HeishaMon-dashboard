/** Ignore suggestions. Listing them never writes preferences (spec §4.3, §7.6). */

const DAY_MS = 24 * 60 * 60 * 1000;

/** Power topics the extra block replaces when `extra/` is present. Identified by catalog id. */
export const EXTRA_REPLACED_IDS = ['TOP15', 'TOP16', 'TOP38', 'TOP39', 'TOP40', 'TOP41'];

function on(profile, field) {
  const node = profile?.[field];
  if (!node || node.unknown || node.stale) return false;
  return node.value === true;
}

function off(profile, field) {
  const node = profile?.[field];
  if (!node || node.unknown || node.stale) return false;
  return node.value === false;
}

export function suggestIgnores({ catalog, topics, profile, now }) {
  const byId = new Map((catalog?.topics ?? []).map((topic) => [topic.id, topic.key]));
  const replaced = new Set(EXTRA_REPLACED_IDS.map((id) => byId.get(id)).filter(Boolean));
  const extra = on(profile, 'has_extra');
  const pcbOff = off(profile, 'optional_pcb_setting');
  const rows = [];
  for (const [key, topic] of Object.entries(topics ?? {})) {
    const reasons = [];
    if (topic?.sentinel && topic.last_change != null && now - topic.last_change >= DAY_MS) reasons.push('sentinel');
    if (extra && replaced.has(key)) reasons.push('extra_replaces');
    if (pcbOff && key.startsWith('optional/')) reasons.push('optional_pcb_off');
    if (reasons.length) rows.push({ key, reasons });
  }
  rows.sort((a, b) => a.key.localeCompare(b.key));
  return rows;
}

const SECTION_ORDER = ['main', 'extra', 'optional', '1wire', 's0', 'opentherm'];

export function sectionPrefix(key) {
  const slash = key.indexOf('/');
  return slash === -1 ? key : key.slice(0, slash);
}

/** Sections are built only from topics that have traffic, so empty sections are absent. */
export function sectionsWithTraffic(topics) {
  const groups = new Map();
  for (const key of Object.keys(topics ?? {})) {
    const prefix = sectionPrefix(key);
    if (!groups.has(prefix)) groups.set(prefix, []);
    groups.get(prefix).push(key);
  }
  const prefixes = [...groups.keys()].sort((a, b) => {
    const ai = SECTION_ORDER.indexOf(a);
    const bi = SECTION_ORDER.indexOf(b);
    if (ai === -1 && bi === -1) return a.localeCompare(b);
    if (ai === -1) return 1;
    if (bi === -1) return -1;
    return ai - bi;
  });
  return prefixes.map((prefix) => ({
    prefix,
    keys: groups.get(prefix).sort((a, b) => a.localeCompare(b)),
  }));
}
