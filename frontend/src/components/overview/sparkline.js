/** Sparkline helpers for overview tiles per spec §7.1.
 * Fetch 24h history from the API and extract values for rendering.
 */

import { api } from '../../lib/api.js';

const SPARKLINE_POINTS = 96; // ~15 min intervals for 24h

/**
 * Fetch 24h of history for a topic and extract sparkline values.
 * §4.4 History: at raw resolution points are [ts, value]; at 1m/1h resolution [ts, avg|null, covered_seconds].
 * Render null/zero-coverage points as gaps (null).
 * @param {string} topicKey
 * @param {number} now
 * @returns {Promise<Array<number | null>>}
 */
export async function fetchSparklineValues(topicKey, now = Date.now()) {
  const twentyFourHoursAgo = now - 24 * 60 * 60 * 1000;
  
  try {
    const history = await api.history({
      topics: [topicKey],
      from: twentyFourHoursAgo,
      to: now,
      max_points: SPARKLINE_POINTS,
    });

    const series = history?.series?.[topicKey];
    if (!series) return [];

    const points = series.points ?? [];
    const resolution = history.resolution;

    // Map points to values, rendering null/zero coverage as gaps
    return points.map((point) => {
      if (!point || point.length === 0) return null;
      
      if (resolution === 'raw') {
        // [ts, value]
        const value = point[1];
        if (value === null || value === undefined || typeof value !== 'number' || isNaN(value)) {
          return null;
        }
        return value;
      } else {
        // 1m or 1h: [ts, avg|null, covered_seconds]
        const avg = point[1];
        const coveredSeconds = point[2];
        
        if (avg === null || coveredSeconds === 0 || coveredSeconds === null || coveredSeconds === undefined) {
          return null;
        }
        return typeof avg === 'number' && !isNaN(avg) ? avg : null;
      }
    });
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
