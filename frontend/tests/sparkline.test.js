import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchSparklineValues, reduceToSlots } from '../src/features/overview/sparkline.js';
import { api } from '../src/lib/api.js';

const MIN = 60_000;
afterEach(() => vi.restoreAllMocks());

describe('sparklines cover 24 h', () => {
  it('asks for a full day of minute buckets', async () => {
    const spy = vi.spyOn(api, 'history').mockResolvedValue({ resolution: '1m', series: {} });
    await fetchSparklineValues('main/Outside_Temp', 24 * 3600 * 1000);
    expect(spy.mock.calls[0][0].max_points).toBeGreaterThanOrEqual(1441);
  });
  it('reduces to 96 slots with coverage-weighted means and gaps', () => {
    const from = 0;
    const slot = 15 * MIN;
    const series = { points: [[0, 10, 60], [MIN, 40, 1], [2 * slot, 20, 60]], breaks: [] };
    const out = reduceToSlots(series, '1m', from, from + 96 * slot, 96);
    expect(out).toHaveLength(96);
    expect(out[0]).toBeCloseTo((10 * 60 + 40) / 61);
    expect(out[1]).toBe(null);
    expect(out[2]).toBe(20);
  });
  it('keeps a slot inside a break empty', () => {
    const slot = 15 * MIN;
    const out = reduceToSlots({ points: [[slot + MIN, 5, 60]], breaks: [[slot, 2 * slot]] }, '1m', 0, 96 * slot, 96);
    expect(out[1]).toBe(null);
  });
});
