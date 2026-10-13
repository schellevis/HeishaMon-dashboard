import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { describe, expect, it } from 'vitest';
import cases from '../../backend/tests/fixtures/rules_cases.json';
import raw from '../../backend/heishamon_dashboard/rules.json';
import { curveLeaf, curveLimits, modeSets, powerPairs, tileIds } from '../src/lib/domain/rules.js';
import { LIMITS, MODE_SETS, leafKey } from '../src/lib/curvegeom.js';
import { POWER_MODES } from '../src/lib/domain/power.js';

describe('rules.js reads rules.json', () => {
  it('exposes the raw values', () => {
    expect(curveLimits).toEqual(raw.curve_limits);
    expect(modeSets.heating).toEqual(raw.operating_modes.heating);
    expect(tileIds).toEqual(raw.tiles);
    expect(tileIds).toContain('outsideTemp');
  });

  it.each(cases.curve_validity)('curve validity %j', (c) => {
    const [lo, hi] = curveLimits[c.mode][c.group];
    expect(c.value >= lo && c.value <= hi).toBe(c.valid);
  });

  it.each(cases.leaf_names)('leaf name %j', (c) => {
    expect(curveLeaf(c.zone, c.mode, c.group, c.end)).toBe(c.topic);
    expect(`main/${leafKey(c.zone, c.mode, c.end, c.group)}`).toBe(c.topic);
  });

  it.each(cases.power_selection)('power selection %j', (c) => {
    const profile = { has_extra: { value: c.has_extra, unknown: false } };
    const { pairs, estimate } = powerPairs(profile);
    expect(pairs[c.mode]).toEqual(c.topics);
    expect(estimate).toBe(!c.has_extra);
  });

  it('keeps the legacy export names of curvegeom and power.js', () => {
    expect(LIMITS).toEqual(raw.curve_limits);
    expect(MODE_SETS).toEqual({ heat: raw.operating_modes.heating, cool: raw.operating_modes.cooling });
    expect(POWER_MODES).toEqual(['heat', 'cool', 'dhw']);
  });
});

// Mode sets and curve leaf patterns live in rules.json only (JS/Svelte sources).
const SRC = join(process.cwd(), 'src'); // vitest runs from frontend/
const SKIP = [`lib${sep}domain${sep}rules.js`];
const LITERALS = /[[{(]\s*0,\s*2,\s*4,\s*6\s*[\]})]|[[{(]\s*1,\s*5,\s*7,\s*8\s*[\]})]|[[{(]\s*3,\s*4,\s*5,\s*6,\s*8\s*[\]})]/;
const LEAF_BUILD = /["'`][^"'`\n]*_Curve_/;

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return walk(path);
    return /\.(js|svelte)$/.test(name) ? [path] : [];
  });
}

describe('no hard-coded rules in the frontend sources', () => {
  const files = walk(SRC).filter((p) => !SKIP.some((s) => p.endsWith(s)) && !p.includes(`${sep}i18n${sep}`));
  it('scans the source tree', () => expect(files.length).toBeGreaterThan(20));
  it.each(files.map((p) => [relative(SRC, p), p]))('%s', (_name, path) => {
    const text = readFileSync(path, 'utf8');
    expect(LITERALS.test(text), 'mode set literal outside rules.json').toBe(false);
    expect(LEAF_BUILD.test(text), 'curve leaf pattern outside rules.json').toBe(false);
  });
});
