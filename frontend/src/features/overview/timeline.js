/** 24 h timeline data (spec R3.4): minute buckets reduced to a 5-minute grid, and activity runs. */
import { activityFrom } from '../../lib/domain/activity.js';
import { powerPairs } from '../../lib/domain/power.js';

export const STEP_MS = 5 * 60 * 1000;
// 24 h is served at 1-minute resolution and the backend keeps the newest max_points: 1500 covers a day.
export const HISTORY_POINTS = 1500;

export function timelineTopics(profile) {
  return {
    outside: 'main/Outside_Temp',
    flow: 'main/Main_Outlet_Temp',
    ret: 'main/Main_Inlet_Temp',
    target: 'main/Main_Target_Temp',
    // total power in = heat + cool + DHW consumption (spec R3.4)
    powerHeat: powerPairs(profile).pairs.heat[1],
    powerCool: powerPairs(profile).pairs.cool[1],
    powerDhw: powerPairs(profile).pairs.dhw[1],
    defrost: 'main/Defrosting_State',
    valve: 'main/ThreeWay_Valve_State',
    heatpump: 'main/Heatpump_State',
    mode: 'main/Operating_Mode_State',
  };
}

/** One history point as {ts, v, w}: w is covered seconds (1 for raw points); null without a covered value. */
export function pointValue(point, resolution) {
  if (!Array.isArray(point)) return null;
  const v = point[1];
  if (typeof v !== 'number' || !Number.isFinite(v)) return null;
  if (resolution === 'raw') return { ts: point[0], v, w: 1 };
  return point[2] > 0 ? { ts: point[0], v, w: point[2] } : null;
}

const REDUCE = {
  mean(items) {
    const w = items.reduce((sum, p) => sum + p.w, 0);
    return w > 0 ? items.reduce((sum, p) => sum + p.v * p.w, 0) / w : null;
  },
  any: (items) => (items.some((p) => p.v > 0) ? 1 : 0),
  half: (items) => (items.some((p) => p.v >= 0.5) ? 1 : 0),
  lastInteger(items) {
    for (let i = items.length - 1; i >= 0; i--) {
      const r = Math.round(items[i].v);
      if (Math.abs(items[i].v - r) <= 0.01) return r;
    }
    return null;
  },
};
const ROLE_REDUCER = { defrost: 'any', valve: 'any', heatpump: 'half', mode: 'lastInteger' };

/** Reduce each topic to one value per slot [from + i·step, from + (i+1)·step). */
export function toGrid(history, topics, from, to, stepMs) {
  const n = Math.max(1, Math.ceil((to - from) / stepMs));
  const xs = Array.from({ length: n }, (_, i) => (from + i * stepMs) / 1000);
  const cols = {};
  const truncated = [];
  for (const [role, key] of Object.entries(topics)) {
    const series = history?.series?.[key];
    if (series?.truncated) truncated.push(key);
    const slots = Array.from({ length: n }, () => []);
    for (const point of series?.points ?? []) {
      const p = pointValue(point, history?.resolution);
      if (!p) continue;
      const i = Math.floor((p.ts - from) / stepMs);
      if (i >= 0 && i < n) slots[i].push(p);
    }
    const breaks = series?.breaks ?? [];
    const reduce = REDUCE[ROLE_REDUCER[role] ?? 'mean'];
    cols[key] = slots.map((items, i) => {
      const start = from + i * stepMs;
      if (!items.length || breaks.some(([s, e]) => s < start + stepMs && e > start)) return null;
      return reduce(items);
    });
  }
  return { xs, cols, truncated };
}

/** Total power in per slot in kW: the sum of the known consumption topics, null when none is known. */
export function powerSum(cols, topics) {
  const keys = [topics.powerHeat, topics.powerCool, topics.powerDhw];
  return (cols[keys[0]] ?? []).map((_, i) => {
    const vals = keys.map((k) => cols[k]?.[i]).filter((v) => typeof v === 'number');
    return vals.length ? vals.reduce((a, b) => a + b, 0) / 1000 : null;
  });
}

/** Temperature axis range: the plotted values rounded out to 10 °C; 0–60 without data. */
export function tempRange(columns) {
  const vals = columns.flat().filter((v) => typeof v === 'number' && Number.isFinite(v));
  if (!vals.length) return [0, 60];
  const lo = Math.floor(Math.min(...vals) / 10) * 10;
  const hi = Math.ceil(Math.max(...vals) / 10) * 10;
  return [lo, hi > lo ? hi : lo + 10];
}

/** Activity runs for the band, strict: a slot lacking a needed input is 'unknown' (drawn as a gap). */
export function activityRuns(xs, cols, topics, stepSec = STEP_MS / 1000) {
  const runs = [];
  for (let i = 0; i < xs.length; i++) {
    const activity = activityFrom({
      defrost: cols[topics.defrost]?.[i] ?? null,
      valve: cols[topics.valve]?.[i] ?? null,
      heatpump: cols[topics.heatpump]?.[i] ?? null,
      mode: cols[topics.mode]?.[i] ?? null,
    }, { strict: true });
    const last = runs[runs.length - 1];
    if (last && last.activity === activity && last.to === xs[i]) last.to = xs[i] + stepSec;
    else runs.push({ from: xs[i], to: xs[i] + stepSec, activity });
  }
  return runs;
}
