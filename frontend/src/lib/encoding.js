/** Client-side mirror of spec §4.4 value encoding, for input validation. */

const INTEGER_TYPES = new Set(['int', 'bool', 'int2', 'int12']);

function fail(error) {
  return { ok: false, error };
}

function ok(payload) {
  return { ok: true, payload };
}

function parseInteger(value) {
  if (typeof value === 'number') {
    if (!Number.isInteger(value)) return fail('bad_type');
    return { ok: true, value };
  }
  if (typeof value === 'string') {
    const text = value.trim();
    if (!/^-?(?:0|[1-9]\d*)$/.test(text)) return fail('bad_type');
    return { ok: true, value: Number(text) };
  }
  return fail('bad_type');
}

function parseDecimal(value) {
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return fail('bad_type');
    return { ok: true, value };
  }
  if (typeof value === 'string') {
    const text = value.trim();
    if (!/^-?(?:0|[1-9]\d*)(?:\.\d+)?$/.test(text)) return fail('bad_type');
    const parsed = Number(text);
    if (!Number.isFinite(parsed)) return fail('bad_type');
    return { ok: true, value: parsed };
  }
  return fail('bad_type');
}

/** `round(v × scale)` within 1e-9 of `v × scale` (spec §4.4 dec1; same check for dec3). */
function fractionalDigitsOk(value, digits) {
  const scaled = value * 10 ** digits;
  return Math.abs(Math.round(scaled) - scaled) <= 1e-9;
}

function formatDec1(value) {
  const tenths = Math.round(value * 10);
  const sign = tenths < 0 ? '-' : '';
  const abs = Math.abs(tenths);
  return `${sign}${Math.trunc(abs / 10)}.${abs % 10}`;
}

function formatDec3(value) {
  const milli = Math.round(value * 1000);
  const sign = milli < 0 ? '-' : '';
  const abs = Math.abs(milli);
  const whole = Math.trunc(abs / 1000);
  const frac = abs % 1000;
  if (frac === 0) return `${sign}${whole}`;
  const fracText = String(frac).padStart(3, '0').replace(/0+$/, '');
  return `${sign}${whole}.${fracText}`;
}

function formatInt2(value) {
  const sign = value < 0 ? '-' : '';
  return sign + String(Math.abs(value)).padStart(2, '0');
}

function integerLeaves(value) {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
  return Object.values(value).every((leaf) => {
    if (leaf !== null && typeof leaf === 'object') return !Array.isArray(leaf) && integerLeaves(leaf);
    return typeof leaf === 'number' && Number.isInteger(leaf);
  });
}

/**
 * Encode a JSON value to the MQTT payload string.
 * @param {string} type catalog payload type
 * @param {number | string | object} value JSON value, or the literal text of one (`"2.0"`)
 * @returns {{ok: true, payload: string} | {ok: false, error: string}}
 */
export function encode(type, value) {
  if (INTEGER_TYPES.has(type)) {
    const parsed = parseInteger(value);
    if (!parsed.ok) return parsed;
    if (type === 'int2') return ok(formatInt2(parsed.value));
    return ok(String(parsed.value));
  }
  if (type === 'dec1' || type === 'dec3') {
    const parsed = parseDecimal(value);
    if (!parsed.ok) return parsed;
    const digits = type === 'dec1' ? 1 : 3;
    if (!fractionalDigitsOk(parsed.value, digits)) return fail('bad_type');
    if (type === 'dec3' && parsed.value < 0) return fail('out_of_range');
    return ok(type === 'dec1' ? formatDec1(parsed.value) : formatDec3(parsed.value));
  }
  if (type === 'json') {
    if (!integerLeaves(value)) return fail('bad_type');
    return ok(JSON.stringify(value));
  }
  return fail('bad_type');
}

function fieldValue(profile, path) {
  const parts = path.replace(/^profile\./, '').split('.');
  let current = profile;
  for (const part of parts) current = current?.[part];
  if (current && typeof current === 'object' && 'value' in current) {
    if (current.unknown || current.stale) return undefined;
    return current.value;
  }
  return current;
}

/** Active numeric range: the first matching conditional range, otherwise `entry.range`. */
export function resolveRange(entry, profile) {
  if (profile && Array.isArray(entry.conditional_ranges)) {
    for (const rule of entry.conditional_ranges) {
      const when = rule.when ?? {};
      const matched = Object.entries(when).every(([path, expected]) => fieldValue(profile, path) === expected);
      if (matched) return { min: rule.min, max: rule.max, step: rule.step };
    }
  }
  return entry.range ?? null;
}

function numericOf(value) {
  if (typeof value === 'number') return value;
  if (typeof value === 'string' && value.trim() !== '') return Number(value);
  return Number.NaN;
}

/**
 * Validate a catalog command or input entry and encode it.
 * @param {object} entry `{type, range?, allowed?, conditional_ranges?}`
 * @param {number | string | object} value
 * @param {object | null} profile installation profile, for conditional ranges
 */
export function validate(entry, value, profile = null) {
  const encoded = encode(entry.type, value);
  if (!encoded.ok) return encoded;
  if (entry.type === 'json') return encoded;

  const number = numericOf(value);
  if (Array.isArray(entry.allowed) && !entry.allowed.includes(number)) return fail('not_allowed_value');

  const range = resolveRange(entry, profile);
  if (range) {
    if ((range.min != null && number < range.min) || (range.max != null && number > range.max)) {
      return fail('out_of_range');
    }
    if (range.step != null && range.step !== 0) {
      const origin = range.min ?? 0;
      const steps = (number - origin) / range.step;
      if (Math.abs(Math.round(steps) - steps) > 1e-9) return fail('bad_step');
    }
  }
  return encoded;
}
