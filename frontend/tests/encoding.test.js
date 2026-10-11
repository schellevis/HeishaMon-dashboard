import { describe, expect, it } from 'vitest';
import { encode, validate } from '../src/lib/encoding.js';

// Mirrors the T06 encoding table (plan) and the §4.4 value-encoding rules.
// Integer types reject the JSON literal 2.0. JS numbers cannot tell 2 from 2.0,
// so that case is passed as the literal text "2.0".

describe('encoding mirror (§4.4, T06 table)', () => {
  it('SetPoolTemp dec1: 20.5 → "20.5", 20 → "20.0", 20.25 → bad_type', () => {
    expect(encode('dec1', 20.5)).toEqual({ ok: true, payload: '20.5' });
    expect(encode('dec1', 20)).toEqual({ ok: true, payload: '20.0' });
    expect(encode('dec1', 20.25)).toEqual({ ok: false, error: 'bad_type' });
  });

  it('SetDHWTemp int: 2.0 → bad_type', () => {
    expect(encode('int', '2.0')).toEqual({ ok: false, error: 'bad_type' });
    expect(encode('int', 2)).toEqual({ ok: true, payload: '2' });
  });

  it('SetSterilizationTemp int2: 55 → "55"', () => {
    expect(encode('int2', 55)).toEqual({ ok: true, payload: '55' });
    expect(encode('int2', 5)).toEqual({ ok: true, payload: '05' });
  });

  it('SetSterilizationMaxTime int12: 5 → "5"', () => {
    expect(encode('int12', 5)).toEqual({ ok: true, payload: '5' });
  });

  it('s0/WatthourTotal dec3: 123456.789 → "123456.789", 5000 → "5000"', () => {
    expect(encode('dec3', 123456.789)).toEqual({ ok: true, payload: '123456.789' });
    expect(encode('dec3', 5000)).toEqual({ ok: true, payload: '5000' });
  });

  it('opentherm dec1: 7.5 → "7.5"', () => {
    expect(encode('dec1', 7.5)).toEqual({ ok: true, payload: '7.5' });
  });

  it('SetCurves json is compact with integer leaves', () => {
    const value = {
      zone1: { heat: { target: { high: 45, low: 30 }, outside: { high: 15, low: -10 } } },
    };
    expect(encode('json', value)).toEqual({
      ok: true,
      payload: '{"zone1":{"heat":{"target":{"high":45,"low":30},"outside":{"high":15,"low":-10}}}}',
    });
    expect(encode('json', { zone1: { heat: { target: { high: 20.5 } } } })).toEqual({
      ok: false,
      error: 'bad_type',
    });
  });

  it('bool encodes 0 and 1 as integer payloads', () => {
    expect(encode('bool', 1)).toEqual({ ok: true, payload: '1' });
    expect(encode('bool', 0)).toEqual({ ok: true, payload: '0' });
    expect(encode('bool', '2.0')).toEqual({ ok: false, error: 'bad_type' });
  });

  it('dec3 rejects a negative and a four-decimal value', () => {
    expect(encode('dec3', -1)).toEqual({ ok: false, error: 'out_of_range' });
    expect(encode('dec3', 1.2345)).toEqual({ ok: false, error: 'bad_type' });
  });
});

describe('validate (§4.4 input validation)', () => {
  const dhw = { type: 'int', range: { min: 40, max: 75, step: 1 }, allowed: null };

  it('rejects out of range and off-step values', () => {
    expect(validate(dhw, 39)).toEqual({ ok: false, error: 'out_of_range' });
    expect(validate({ type: 'int', range: { min: 5, max: 60, step: 5 } }, 6)).toEqual({
      ok: false,
      error: 'bad_step',
    });
    expect(validate(dhw, 50)).toEqual({ ok: true, payload: '50' });
  });

  it('rejects a value outside the allowed set', () => {
    expect(validate({ type: 'bool', allowed: [0, 1] }, 2)).toEqual({
      ok: false,
      error: 'not_allowed_value',
    });
    expect(validate({ type: 'bool', allowed: [0, 1] }, 1)).toEqual({ ok: true, payload: '1' });
  });

  it('uses a conditional range when the profile matches', () => {
    const entry = {
      type: 'int',
      range: { min: 20, max: 65, step: 1 },
      conditional_ranges: [
        { when: { 'profile.heating_control': 'curve' }, min: -5, max: 5, step: 1 },
      ],
    };
    const curve = { heating_control: { value: 'curve', unknown: false, stale: false } };
    const direct = { heating_control: { value: 'direct', unknown: false, stale: false } };
    expect(validate(entry, 10, curve)).toEqual({ ok: false, error: 'out_of_range' });
    expect(validate(entry, 3, curve)).toEqual({ ok: true, payload: '3' });
    expect(validate(entry, 10, direct)).toEqual({ ok: false, error: 'out_of_range' });
    expect(validate(entry, 21, direct)).toEqual({ ok: true, payload: '21' });
  });
});
