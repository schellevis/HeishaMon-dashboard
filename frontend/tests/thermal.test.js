import { describe, expect, it } from 'vitest';
import { ACTIVITY_VAR, RAMP, mixRgb, tempColor } from '../src/lib/ui/thermal.js';

describe('thermal ramp', () => {
  it('hits the stops exactly', () => {
    expect(tempColor(15)).toBe('rgb(79,163,224)');
    expect(tempColor(28)).toBe('rgb(143,184,201)');
    expect(tempColor(38)).toBe('rgb(240,160,75)');
    expect(tempColor(55)).toBe('rgb(229,83,61)');
  });
  it('clamps outside the ramp', () => {
    expect(tempColor(-20)).toBe(tempColor(15));
    expect(tempColor(80)).toBe(tempColor(55));
  });
  it('interpolates between stops', () => {
    expect(tempColor(46.5)).toBe(mixRgb([240, 160, 75], [229, 83, 61], 0.5));
  });
  it('returns the idle pipe colour for missing values', () => {
    expect(tempColor(null)).toBe('var(--pipe-idle)');
    expect(tempColor(Number.NaN)).toBe('var(--pipe-idle)');
  });
  it('has four ascending stops and a colour per activity', () => {
    expect(RAMP.map(([t]) => t)).toEqual([15, 28, 38, 55]);
    expect(Object.keys(ACTIVITY_VAR).sort()).toEqual(['cooling', 'defrost', 'dhw', 'heating', 'idle']);
  });
});
