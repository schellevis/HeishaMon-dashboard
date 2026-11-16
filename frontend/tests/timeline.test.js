import { describe, expect, it } from 'vitest';
import { HISTORY_POINTS, STEP_MS, activityRuns, pointValue, powerSum, tempRange, timelineTopics, toGrid } from '../src/features/overview/timeline.js';
import { modeSets } from '../src/lib/domain/rules.js';

const MIN = 60_000;
const heat = modeSets.heating[0];
const t = timelineTopics(null);
const H = (series, resolution = '1m') => ({ resolution, series });
const S = (points, extra = {}) => ({ kind: 'number', points, breaks: [], ...extra });

describe('pointValue', () => {
  it('reads raw and rollup points with their weight', () => {
    expect(pointValue([1, 5], 'raw')).toEqual({ ts: 1, v: 5, w: 1 });
    expect(pointValue([1, 5.5, 60], '1m')).toEqual({ ts: 1, v: 5.5, w: 60 });
    expect(pointValue([1, 5.5, 0], '1m')).toBe(null);
    expect(pointValue([1, null, 60], '1m')).toBe(null);
  });
});

describe('toGrid', () => {
  it('asks for enough points for a full day of minute buckets', () => {
    expect(HISTORY_POINTS).toBeGreaterThanOrEqual(1441);
  });
  it('keeps the first and the last hour of a full day', () => {
    const day = 24 * 3600 * 1000;
    const pts = [];
    for (let ts = 0; ts < day; ts += MIN) pts.push([ts, 20, 60]);
    const g = toGrid(H({ [t.outside]: S(pts) }), t, 0, day, STEP_MS);
    expect(g.xs).toHaveLength(288); // 288 five-minute slots covering [from, to), spec R3.4
    expect(g.cols[t.outside][0]).toBe(20);
    expect(g.cols[t.outside][287]).toBe(20);
  });
  it('weights temperatures by coverage', () => {
    const g = toGrid(H({ [t.flow]: S([[0, 10, 60], [MIN, 40, 1]]) }), t, 0, STEP_MS, STEP_MS);
    expect(g.cols[t.flow][0]).toBeCloseTo((10 * 60 + 40) / 61);
  });
  it('keeps a short defrost or DHW run', () => {
    const g = toGrid(H({ [t.defrost]: S([[0, 0, 60], [MIN, 0.1, 60]]), [t.valve]: S([[0, 0.05, 60]]) }), t, 0, STEP_MS, STEP_MS);
    expect(g.cols[t.defrost][0]).toBe(1);
    expect(g.cols[t.valve][0]).toBe(1);
  });
  it('takes the last integer mode and drops fractional ones', () => {
    expect(toGrid(H({ [t.mode]: S([[0, 4, 60], [MIN, 2.5, 60]]) }), t, 0, STEP_MS, STEP_MS).cols[t.mode][0]).toBe(4);
    expect(toGrid(H({ [t.mode]: S([[0, 2.5, 60], [MIN, 0.4, 60]]) }), t, 0, STEP_MS, STEP_MS).cols[t.mode][0]).toBe(null);
  });
  it('blanks slots inside a break, empty slots and missing series', () => {
    const g = toGrid(H({ [t.flow]: S([[0, 30, 60], [STEP_MS + MIN, 31, 60]], { breaks: [[STEP_MS, 2 * STEP_MS]] }) }), t, 0, 3 * STEP_MS, STEP_MS);
    expect(g.cols[t.flow]).toEqual([30, null, null]);
    expect(g.cols[t.ret]).toEqual([null, null, null]);
  });
  it('blanks a slot that only partly overlaps an outage', () => {
    const g = toGrid(H({ [t.flow]: S([[0, 30, 60], [3 * MIN, 31, 60]], { breaks: [[MIN, 2 * MIN]] }) }), t, 0, STEP_MS, STEP_MS);
    expect(g.cols[t.flow]).toEqual([null]);
  });
  it('reports truncated series', () => {
    const g = toGrid(H({ [t.flow]: S([[0, 30, 60]], { truncated: true }) }), t, 0, STEP_MS, STEP_MS);
    expect(g.truncated).toEqual([t.flow]);
  });
});

describe('activityRuns', () => {
  const cols = (d, v, h, m) => ({ [t.defrost]: d, [t.valve]: v, [t.heatpump]: h, [t.mode]: m });
  it('merges equal neighbours and keeps a short defrost', () => {
    expect(activityRuns([0, 300, 600, 900], cols([0, 0, 1, 0], [0, 0, 0, 0], [1, 1, 1, 1], [heat, heat, heat, heat]), t)).toEqual([
      { from: 0, to: 600, activity: 'heating' },
      { from: 600, to: 900, activity: 'defrost' },
      { from: 900, to: 1200, activity: 'heating' },
    ]);
  });
  it('is unknown when an input needed to exclude a higher priority is missing', () => {
    expect(activityRuns([0], cols([null], [0], [1], [heat]), t)[0].activity).toBe('unknown');
    expect(activityRuns([0], cols([0], [null], [1], [heat]), t)[0].activity).toBe('unknown');
    expect(activityRuns([0], cols([0], [0], [1], [null]), t)[0].activity).toBe('unknown');
    expect(activityRuns([0], cols([1], [null], [null], [null]), t)[0].activity).toBe('defrost');
  });
  it('shows why the band is labelled approximate', () => {
    // 30 s of mode 0 and 30 s of mode 2 (both heating) average to 1, a cooling mode
    expect(modeSets.cooling).toContain(1);
    const g = toGrid(H({ [t.mode]: S([[0, 1, 60]]), [t.defrost]: S([[0, 0, 60]]), [t.valve]: S([[0, 0, 60]]), [t.heatpump]: S([[0, 1, 60]]) }), t, 0, STEP_MS, STEP_MS);
    expect(activityRuns(g.xs, g.cols, t)[0].activity).toBe('cooling');
  });
});

describe('powerSum and tempRange', () => {
  it('sums the known consumption topics in kW', () => {
    const cols = { [t.powerHeat]: [1000, null, null], [t.powerCool]: [null, null, null], [t.powerDhw]: [500, 2000, null] };
    expect(powerSum(cols, t)).toEqual([1.5, 2, null]);
  });
  it('fits the temperature axis to the data, rounded out to 10 °C', () => {
    expect(tempRange([[-7.5, 20], [48, null]])).toEqual([-10, 50]);
    expect(tempRange([[20]])).toEqual([20, 30]);
    expect(tempRange([[null], []])).toEqual([0, 60]);
  });
});

describe('timelineTopics', () => {
  it('stays within the 20-topic history limit', () => {
    expect(Object.values(timelineTopics(null)).length).toBeLessThanOrEqual(20);
  });
});
