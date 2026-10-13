import { topicByKey } from '../catalog.js';

/**
 * Catalog-derived presentation fields for one topic value. Used for the hello snapshot and for every
 * live update, so a value that changes (enum 0 -> 1, sentinel -> real reading) never keeps stale fields.
 */
export function normalizeTopicValue(key, raw, value, prev) {
  const meta = topicByKey(key);
  if (!meta) {
    return {
      kind: prev?.kind ?? 'text',
      unit: null,
      decimals: null,
      enum_label: null,
      catalogued: false,
      sentinel: false,
    };
  }
  const number = typeof value === 'number' && Number.isFinite(value);
  const sentinel = number && (meta.sentinels ?? []).includes(value);
  const label = meta.enum && number && !sentinel ? meta.enum[String(Math.trunc(value))] : null;
  return {
    kind: meta.kind ?? 'text',
    unit: meta.unit ?? null,
    decimals: meta.decimals ?? null,
    enum_label: label ? { en: label.en, nl: label.nl } : null,
    catalogued: true,
    sentinel,
  };
}
