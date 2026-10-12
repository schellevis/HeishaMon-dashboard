// Heating-curve geometry and maths (spec §3, §8). Mirrors backend/heishamon_dashboard/curve.py.
// A curve is { cold: { outside, target }, warm: { outside, target } }.
// Cold end = Outside_Low + Target_High; warm end = Outside_High + Target_Low (crosswise naming, §3).

export const LIMITS = {
  heat: { outside: [-20, 30], target: [15, 75] },
  cool: { outside: [15, 30], target: [5, 20] },
};
export const MODE_SETS = { heat: [0, 2, 4, 6], cool: [1, 5, 7, 8] };
export const ROOM_SENSOR_VALUES = [1, 2, 3];
/** Profile sensor values (profile.zone.zN.sensor) that are a room sensor (thermostat/thermistor). */
export const ROOM_SENSORS = ['ext_thermostat', 'int_thermostat', 'thermistor'];
export const SHIFT_RANGE = { min: -5, max: 5 };
export const MODEL_TOLERANCE = 1;
export const THRESHOLDS = {
  heaterOn: { key: 'main/Heater_On_Outdoor_Temp', command: 'SetHeaterOnOutdoorTemp', min: -15, max: 20 },
  heatingOff: { key: 'main/Heating_Off_Outdoor_Temp', command: 'SetHeatingOffOutdoorTemp', min: 5, max: 35 },
};

// [end, field] -> [key part, SetCurves json path]
const LEAVES = [
  ['cold', 'target', 'Target_High', ['target', 'high']],
  ['warm', 'target', 'Target_Low', ['target', 'low']],
  ['warm', 'outside', 'Outside_High', ['outside', 'high']],
  ['cold', 'outside', 'Outside_Low', ['outside', 'low']],
];

export function zoneNum(zone) {
  const m = /\d/.exec(String(zone));
  if (!m) throw new Error(`zone ${zone} has no number`);
  return Number(m[0]);
}

function modeOf(mode) {
  const m = String(mode).toLowerCase();
  if (!(m in LIMITS)) throw new Error(`mode ${mode} must be heat or cool`);
  return m;
}

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

/** Catalog-style leaf name, e.g. Z1_Heat_Curve_Target_High_Temp. */
export function leafKey(zone, mode, end, field) {
  const part = LEAVES.find((l) => l[0] === end && l[1] === field)[2];
  return `Z${zoneNum(zone)}_${cap(modeOf(mode))}_Curve_${part}_Temp`;
}

/** Cold/warm end from published values (a map key -> number, `main/` prefix optional); null if any is missing. */
export function curvePoints(values, zone, mode) {
  const bare = {};
  for (const [k, v] of Object.entries(values ?? {})) bare[k.split('/').pop()] = v;
  const curve = { cold: {}, warm: {} };
  for (const [end, field] of LEAVES) {
    const v = bare[leafKey(zone, mode, end, field)];
    if (v === undefined || v === null || typeof v !== 'number' || !Number.isFinite(v)) return null;
    curve[end][field] = v;
  }
  return curve;
}

/** Water target the model expects: straight line between the ends, flat beyond them (model assumption), plus shift. */
export function modelTarget(curve, shift, outside) {
  const c = curve.cold;
  const w = curve.warm;
  let base;
  if (outside <= c.outside || w.outside <= c.outside) base = c.target;
  else if (outside >= w.outside) base = w.target;
  else base = c.target + ((outside - c.outside) / (w.outside - c.outside)) * (w.target - c.target);
  return base + shift;
}

/** True when the reported target differs from the model by more than 1 °C. */
export function modelDisagrees(curve, shift, outside, reported) {
  if (!curve || ![outside, reported].every(Number.isFinite)) return false;
  return Math.abs(modelTarget(curve, shift ?? 0, outside) - reported) > MODEL_TOLERANCE;
}

const usable = (f) => !!f && !f.unknown && !f.stale;

/**
 * "Coupled" zone/mode: direct control with a room sensor (thermostat/thermistor). The firmware then
 * stores the direct setpoint in the curve's cold-end target (Target_High) and does not use the
 * warm-end target, so the target-ordering rule does not apply. False when anything is unknown/stale.
 */
export function isCoupled(profile, zone, mode) {
  const m = modeOf(mode);
  const ctl = m === 'heat' ? profile?.heating_control : profile?.cooling_control;
  const sensor = profile?.zone?.[`z${zoneNum(zone)}`]?.sensor;
  return usable(ctl) && ctl.value === 'direct' && usable(sensor) && ROOM_SENSORS.includes(sensor.value);
}

/**
 * Error codes for a draft; empty when valid (ordering invariant and limits).
 * `opts.coupled` drops the target-ordering rule (limits and outside ordering still apply).
 */
export function validateDraft(draft, mode, opts = {}) {
  const lim = LIMITS[modeOf(mode)];
  const errors = [];
  for (const end of ['cold', 'warm']) {
    for (const field of ['outside', 'target']) {
      const v = draft[end][field];
      if (typeof v !== 'number' || !Number.isInteger(v)) errors.push(`not_integer:${end}.${field}`);
      else if (v < lim[field][0] || v > lim[field][1]) errors.push(`limit:${end}.${field}`);
    }
  }
  if (!errors.length) {
    if (draft.cold.outside + 1 > draft.warm.outside) errors.push('outside_order');
    if (!opts.coupled && draft.cold.target < draft.warm.target) errors.push('target_order');
  }
  return errors;
}

function stepped(curve, mode, coldD, warmD, opts) {
  const next = {
    cold: { outside: curve.cold.outside, target: curve.cold.target + coldD },
    warm: { outside: curve.warm.outside, target: curve.warm.target + warmD },
  };
  return validateDraft(next, mode, opts).length ? null : next;
}

/** Cold target +delta, warm target -delta (+1 steepens). null when refused as a whole. */
export const slopeStep = (curve, mode, delta, opts = {}) => stepped(curve, mode, delta, -delta, opts);
/** Both targets +delta. null when refused as a whole. */
export const levelStep = (curve, mode, delta, opts = {}) => stepped(curve, mode, delta, delta, opts);

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

/**
 * Move one handle to a (possibly fractional) position. Snaps to 1 °C, and stops at the last valid
 * integer: limits and the ordering invariant. Returns a new curve (unchanged if nothing is valid).
 * `end` is 'cold' | 'warm'; `field` is 'outside' | 'target'. `opts.coupled` drops target ordering.
 */
export function moveHandle(curve, mode, end, field, value, opts = {}) {
  const lim = LIMITS[modeOf(mode)][field];
  let lo = lim[0];
  let hi = lim[1];
  if (field === 'outside') {
    if (end === 'cold') hi = Math.min(hi, curve.warm.outside - 1);
    else lo = Math.max(lo, curve.cold.outside + 1);
  } else if (opts.coupled) {
    // coupled mode: the cold-end target is the setpoint; targets are independent
  } else if (end === 'cold') lo = Math.max(lo, curve.warm.target);
  else hi = Math.min(hi, curve.cold.target);
  if (lo > hi) return curve;
  const next = {
    cold: { ...curve.cold },
    warm: { ...curve.warm },
  };
  next[end][field] = clamp(Math.round(value), lo, hi);
  return next;
}

/** Partial SetCurves JSON with only changed leaves, plus keys (leaf name -> expected value). */
export function setcurvesDiff(current, draft, zone = 'z1', mode = 'heat') {
  const n = zoneNum(zone);
  const m = modeOf(mode);
  const json = {};
  const keys = {};
  for (const [end, field, , [grp, hl]] of LEAVES) {
    const value = draft[end][field];
    if (value === current[end][field]) continue;
    json[`zone${n}`] ??= {};
    json[`zone${n}`][m] ??= {};
    json[`zone${n}`][m][grp] ??= {};
    json[`zone${n}`][m][grp][hl] = value;
    keys[leafKey(n, m, end, field)] = value;
  }
  return { json, keys };
}

/** Leaf names -> values contained in a (partial) SetCurves object. */
export function leavesOfJson(json) {
  const out = {};
  for (const [zk, zv] of Object.entries(json ?? {})) {
    const n = /^zone(\d)$/.exec(zk)?.[1];
    if (!n) continue;
    for (const [mode, mv] of Object.entries(zv ?? {})) {
      if (!(mode in LIMITS)) continue;
      for (const [end, field, , [grp, hl]] of LEAVES) {
        const v = mv?.[grp]?.[hl];
        if (typeof v === 'number') out[leafKey(n, mode, end, field)] = v;
      }
    }
  }
  return out;
}

/** Apply leaf values (leaf name -> value) onto a curve for this zone/mode. */
export function applyLeaves(curve, leaves, zone, mode) {
  const next = { cold: { ...curve.cold }, warm: { ...curve.warm } };
  for (const [end, field] of LEAVES) {
    const k = leafKey(zone, mode, end, field);
    if (k in leaves) next[end][field] = leaves[k];
  }
  return next;
}

// ---------------------------------------------------------------- chart geometry

export const X_RANGE = { heat: [-25, 35], cool: [10, 35] };
export const Y_RANGE = { heat: [10, 80], cool: [0, 25] };

export function makeScale(domain, range) {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const to = (v) => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);
  to.invert = (px) => d0 + ((px - r0) / (r1 - r0)) * (d1 - d0);
  return to;
}

/** Polyline points [outside, water] of the configured curve, flat beyond both ends, across x domain. */
export function curveLine(curve, shift, xDomain) {
  const [x0, x1] = xDomain;
  const s = shift ?? 0;
  return [
    [x0, curve.cold.target + s],
    [curve.cold.outside, curve.cold.target + s],
    [curve.warm.outside, curve.warm.target + s],
    [x1, curve.warm.target + s],
  ];
}

/** Compact old -> new rows for a diff table. */
export function diffRows(current, draft, zone, mode) {
  const rows = [];
  for (const [end, field] of LEAVES) {
    if (current[end][field] !== draft[end][field]) {
      rows.push({
        key: leafKey(zone, mode, end, field),
        end,
        field,
        from: current[end][field],
        to: draft[end][field],
      });
    }
  }
  return rows;
}

// ---------------------------------------------------------------- overlay

/** Colour-by modes the overlay offers; room_minus_setpoint only when `hasRoom`. */
export function overlayModes(windows) {
  const modes = ['water_minus_target', 'cop', 'freq'];
  if (windows.some((w) => w.side !== null && w.side !== undefined)) modes.push('side');
  if (windows.some((w) => w.room_minus_setpoint !== null && w.room_minus_setpoint !== undefined)) modes.push('room_minus_setpoint');
  return modes;
}

/** Diverging colour for a deviation in °C (blue below, red above, grey zero). */
export function deviationColor(v) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '#9aa0a6';
  const t = Math.min(1, Math.abs(v) / 5);
  const l = 85 - 40 * t;
  return v < 0 ? `hsl(215 70% ${l}%)` : `hsl(8 75% ${l}%)`;
}

export function sequentialColor(v, lo, hi) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '#9aa0a6';
  const t = hi > lo ? Math.min(1, Math.max(0, (v - lo) / (hi - lo))) : 0.5;
  return `hsl(${200 - 160 * t} 65% ${70 - 25 * t}%)`;
}

/** Colour and label of one window for a colour-by mode. */
export function windowColor(w, by, ranges = {}) {
  switch (by) {
    case 'cop':
      return w.cop === null || w.cop === undefined ? { color: '#9aa0a6', noCop: true } : { color: sequentialColor(w.cop, ranges.copLo ?? 1, ranges.copHi ?? 6) };
    case 'freq':
      return { color: sequentialColor(w.freq, ranges.freqLo ?? 0, ranges.freqHi ?? 100) };
    case 'side':
      if (w.side === 'before') return { color: '#8e6bbf' };
      if (w.side === 'after') return { color: '#2b8a6e' };
      return { color: 'none', outlined: true };
    case 'room_minus_setpoint':
      return { color: deviationColor(w.room_minus_setpoint) };
    default:
      return { color: deviationColor(w.water_minus_target) };
  }
}
