import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/svelte';
import { flushSync } from 'svelte';
import uPlot from 'uplot';
import Timeline24h from '../src/features/overview/Timeline24h.svelte';
import { api } from '../src/lib/api.js';
import { setTheme } from '../src/lib/theme.js';

// createChart can be held open to simulate a slow chart build
const gate = vi.hoisted(() => ({ hold: null }));
vi.mock('../src/lib/uplot.js', async (importOriginal) => {
  const m = await importOriginal();
  return { ...m, createChart: async (...args) => { if (gate.hold) await gate.hold; return m.createChart(...args); } };
});

const MIN = 60_000;
afterEach(() => {
  gate.hold = null;
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function dayHistory(now, flow = 30, extra = {}) {
  const pts = [];
  for (let ts = now - 24 * 3600 * 1000; ts < now; ts += MIN) pts.push([ts, flow, 60]);
  return { resolution: '1m', series: { 'main/Main_Outlet_Temp': { kind: 'number', points: pts, breaks: [] }, ...extra } };
}
function deferred() {
  let resolve;
  const promise = new Promise((r) => { resolve = r; });
  return { promise, resolve };
}
const live = (from) => uPlot.instances.slice(from).filter((u) => !u.destroyed);

describe('Timeline24h', () => {
  it('asks for a full day, draws one chart and reads out the newest slot', async () => {
    const history = vi.spyOn(api, 'history').mockResolvedValue(dayHistory(Date.now()));
    const before = uPlot.instances.length;
    render(Timeline24h, { profile: null, lang: 'en' });
    await waitFor(() => expect(uPlot.instances.length).toBe(before + 1));
    expect(history.mock.calls[0][0].max_points).toBe(1500);
    const readout = screen.getByTestId('timeline-readout').textContent;
    expect(readout).toContain('now');
    expect(readout).toContain('30.0°');
    expect(screen.getByTestId('timeline-approx')).toBeTruthy();
  });
  it('destroys its chart on unmount', async () => {
    vi.spyOn(api, 'history').mockResolvedValue(dayHistory(Date.now()));
    const before = uPlot.instances.length;
    const { unmount } = render(Timeline24h, { profile: null, lang: 'en' });
    await waitFor(() => expect(uPlot.instances.length).toBe(before + 1));
    const chart = uPlot.instances.at(-1);
    unmount();
    expect(chart.destroyed).toBe(true);
  });
  it('reads out the slot under the cursor, including target and power, and "now" when it leaves', async () => {
    const now = Date.now();
    const target = [];
    const power = [];
    for (let ts = now - 24 * 3600 * 1000; ts < now; ts += MIN) { target.push([ts, 35, 60]); power.push([ts, 600, 60]); }
    vi.spyOn(api, 'history').mockResolvedValue(dayHistory(now, 30, {
      'main/Main_Target_Temp': { kind: 'number', points: target, breaks: [] },
      'main/Heat_Power_Consumption': { kind: 'number', points: power, breaks: [] },
    }));
    const before = uPlot.instances.length;
    render(Timeline24h, { profile: null, lang: 'en' });
    await waitFor(() => expect(uPlot.instances.length).toBe(before + 1));
    const chart = uPlot.instances.at(-1);
    chart.cursor.idx = 0;
    flushSync(() => chart.opts.hooks.setCursor[0](chart));
    const readout = screen.getByTestId('timeline-readout').textContent;
    expect(readout).not.toMatch(/\bnow\b/); // word match: the activity label 'unknown' contains 'now'
    expect(readout).toContain('35.0°');
    expect(readout).toContain('0.60 kW');
    chart.cursor.idx = null;
    flushSync(() => chart.opts.hooks.setCursor[0](chart));
    expect(screen.getByTestId('timeline-readout').textContent).toContain('now');
  });
  it('refreshes every five minutes', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const history = vi.spyOn(api, 'history').mockResolvedValue(dayHistory(Date.now()));
    render(Timeline24h, { profile: null, lang: 'en' });
    await waitFor(() => expect(history).toHaveBeenCalledTimes(1));
    await vi.advanceTimersByTimeAsync(5 * 60 * 1000);
    expect(history).toHaveBeenCalledTimes(2);
  });
  it('keeps the newest power source when responses arrive out of order', async () => {
    const first = deferred();
    const second = deferred();
    vi.spyOn(api, 'history').mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const F = (value) => ({ value, unknown: false, stale: false });
    const { rerender } = render(Timeline24h, { profile: { has_extra: F(false) }, lang: 'en' });
    await rerender({ profile: { has_extra: F(true) }, lang: 'en' });
    second.resolve(dayHistory(Date.now(), 40));
    await waitFor(() => expect(screen.getByTestId('timeline-readout').textContent).toContain('40.0°'));
    first.resolve(dayHistory(Date.now(), 30));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByTestId('timeline-readout').textContent).toContain('40.0°');
  });
  it('destroys a chart whose slow build is superseded by a theme switch, and one finished after unmount', async () => {
    setTheme('night');
    vi.spyOn(api, 'history').mockResolvedValue(dayHistory(Date.now()));
    const hold = deferred();
    gate.hold = hold.promise;
    const before = uPlot.instances.length;
    const { unmount } = render(Timeline24h, { profile: null, lang: 'en' });
    await waitFor(() => expect(screen.getByTestId('timeline-readout')).toBeTruthy());
    setTheme('day'); // second build starts while the first still waits
    flushSync();
    hold.resolve();
    await waitFor(() => expect(uPlot.instances.length).toBeGreaterThanOrEqual(before + 2));
    expect(live(before)).toHaveLength(1);
    const slow = deferred();
    gate.hold = slow.promise;
    setTheme('night');
    flushSync();
    unmount();
    slow.resolve();
    await new Promise((r) => setTimeout(r, 20));
    expect(live(before)).toHaveLength(0);
  });
  it('ignores a history response that arrives after unmount', async () => {
    let resolve;
    vi.spyOn(api, 'history').mockReturnValue(new Promise((r) => { resolve = r; }));
    const before = uPlot.instances.length;
    const { unmount } = render(Timeline24h, { profile: null, lang: 'en' });
    unmount();
    resolve(dayHistory(Date.now()));
    await new Promise((r) => setTimeout(r, 20));
    expect(uPlot.instances.length).toBe(before);
  });
});
