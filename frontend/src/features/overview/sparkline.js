/** Sparkline helpers for overview tiles per spec §7.1.
 * Fetch 24h history from the API and extract values for rendering.
 */

import { api } from '../../lib/api.js';

const SLOTS = 96; // 15 min slots for 24 h
const DAY_MS = 24 * 60 * 60 * 1000;
const MAX_POINTS = 1500; // a full day of 1-minute buckets

/**
 * Reduce a history series to `n` equal slots: coverage-weighted mean per slot (raw points weigh 1),
 * null for an empty slot or a slot whose start lies inside a break.
 * §4.4 History: raw points are [ts, value]; 1m/1h points are [ts, avg|null, covered_seconds].
 * @returns {Array<number | null>}
 */
export function reduceToSlots(series, resolution, from, to, n = SLOTS) {
  const slot = (to - from) / n;
  const sums = new Array(n).fill(0);
  const weights = new Array(n).fill(0);
  for (const point of series?.points ?? []) {
    if (!point || point.length === 0) continue;
    const [ts, value, covered] = point;
    if (typeof value !== 'number' || Number.isNaN(value)) continue;
    const weight = resolution === 'raw' ? 1 : covered;
    if (!(weight > 0)) continue;
    const index = Math.floor((ts - from) / slot);
    if (index < 0 || index >= n) continue;
    sums[index] += value * weight;
    weights[index] += weight;
  }
  const breaks = series?.breaks ?? [];
  return sums.map((sum, i) => {
    const start = from + i * slot;
    if (breaks.some(([a, b]) => start >= a && start < b)) return null;
    return weights[i] > 0 ? sum / weights[i] : null;
  });
}

/**
 * Fetch 24h of history for a topic and reduce it to sparkline values.
 * @param {string} topicKey
 * @param {number} now
 * @returns {Promise<Array<number | null>>}
 */
export async function fetchSparklineValues(topicKey, now = Date.now()) {
  const from = now - DAY_MS;
  try {
    const history = await api.history({ topics: [topicKey], from, to: now, max_points: MAX_POINTS });
    const series = history?.series?.[topicKey];
    if (!series) return [];
    return reduceToSlots(series, history.resolution, from, now, SLOTS);
  } catch (error) {
    console.warn(`Sparkline fetch failed for ${topicKey}:`, error);
    return [];
  }
}

/**
 * Normalize sparkline values for SVG rendering.
 * @param {Array<number | null>} values
 * @param {number} width
 * @param {number} height
 * @returns {Array<{x: number, y: number} | null>}
 */
export function normalizeSparkline(values, width = 100, height = 40) {
  const validValues = values.filter((v) => v !== null && typeof v === 'number' && !isNaN(v));
  
  if (validValues.length === 0) {
    return [];
  }
  
  const min = Math.min(...validValues);
  const max = Math.max(...validValues);
  const range = max - min;
  const scale = range === 0 ? 1 : range;
  
  return values.map((v, i) => {
    if (v === null) return null;
    const x = (i / (values.length - 1)) * width;
    const y = height - ((v - min) / scale) * height;
    return { x, y };
  });
}
