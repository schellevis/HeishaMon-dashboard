<script>
  import { onDestroy, untrack } from 'svelte';
  import { api } from '../../lib/api.js';
  import { translate } from '../../lib/i18n/index.js';
  import { activityLabel } from '../../lib/format.js';
  import { createChart, themedAxes, timeAxes } from '../../lib/uplot.js';
  import { cssVar, resolvedTheme } from '../../lib/theme.js';
  import { ACTIVITY_VAR } from '../../lib/ui/thermal.js';
  import { HISTORY_POINTS, STEP_MS, activityRuns, powerSum, tempRange, timelineTopics, toGrid } from './timeline.js';

  let { profile = null, lang = 'en' } = $props();
  const t = (key) => translate(lang, `overview.${key}`);
  const REFRESH_MS = 5 * 60 * 1000;
  const BAND = 12;
  const HEIGHT = 250;

  let host = $state(null);
  let data = $state(null); // { xs, cols, truncated, topics, runs, power }
  let cursor = $state(null);
  let chart = null;
  let loadToken = 0;
  let renderToken = 0;
  let alive = true;

  async function load(profileNow) {
    const token = ++loadToken;
    const to = Date.now();
    const from = to - 24 * 3600 * 1000;
    const topics = timelineTopics(profileNow);
    try {
      const history = await api.history({ topics: Object.values(topics), from, to, max_points: HISTORY_POINTS });
      if (!alive || token !== loadToken) return;
      const grid = toGrid(history, topics, from, to, STEP_MS);
      data = { ...grid, topics, runs: activityRuns(grid.xs, grid.cols, topics), power: powerSum(grid.cols, topics) };
    } catch {
      if (alive && token === loadToken) data = null;
    }
  }

  // Load now, when the power source (has_extra) changes, and every 5 minutes; never per live message.
  const extra = $derived(profile?.has_extra?.value === true);
  $effect(() => {
    void extra;
    untrack(() => load(profile));
    const timer = setInterval(() => untrack(() => load(profile)), REFRESH_MS);
    return () => {
      loadToken++;
      clearInterval(timer);
    };
  });

  function bandPlugin(runs) {
    return {
      hooks: {
        drawClear: [(u) => {
          const ctx = u.ctx;
          const dpr = devicePixelRatio || 1;
          const y = u.bbox.top - (BAND + 8) * dpr;
          for (const r of runs) {
            if (r.activity === 'unknown') continue; // drawn as a gap, never as idle
            const x0 = u.valToPos(r.from, 'x', true);
            const x1 = u.valToPos(r.to, 'x', true);
            ctx.fillStyle = cssVar(ACTIVITY_VAR[r.activity]);
            ctx.fillRect(x0, y, Math.max(1, x1 - x0), BAND * dpr);
          }
        }],
      },
    };
  }

  function destroyChart() {
    chart?.destroy();
    chart = null;
  }

  async function draw(d, el, language) {
    const token = ++renderToken;
    destroyChart();
    if (!el || !d) return;
    const { xs, cols, topics, runs, power } = d;
    const temps = [cols[topics.target], cols[topics.outside], cols[topics.ret], cols[topics.flow]];
    const maxKw = Math.max(1, ...power.filter((v) => v !== null));
    const [xAxis] = timeAxes(language);
    let created;
    try {
      created = await createChart(el, {
        width: el.clientWidth || 800,
        height: HEIGHT,
        padding: [BAND + 14, 8, 0, 0],
        legend: { show: false },
        cursor: { y: false, points: { show: false } },
        scales: { x: { time: true }, t: { range: tempRange(temps) }, p: { range: [0, maxKw * 4] } },
        axes: themedAxes([xAxis, { scale: 't', size: 40, values: (u, v) => v.map((n) => `${n}°`) }]),
        series: [
          { label: t('lineTarget'), scale: 't', stroke: cssVar('--ink-3'), dash: [3, 3], width: 1.2 },
          { label: t('lineOutside'), scale: 't', stroke: cssVar('--cold'), width: 1.6 },
          { label: t('lineReturn'), scale: 't', stroke: cssVar('--cool'), width: 1.4 },
          { label: t('lineFlow'), scale: 't', stroke: cssVar('--warm'), width: 1.9 },
          { label: t('linePower'), scale: 'p', stroke: cssVar('--ink-3'), fill: cssVar('--line'), width: 1, stepped: true },
        ],
        data: [xs, ...temps, power],
        plugins: [bandPlugin(runs)],
        hooks: { setCursor: [(u) => { cursor = u.cursor.idx ?? null; }] },
      });
    } catch {
      return;
    }
    if (!alive || token !== renderToken) {
      created.destroy();
      return;
    }
    chart = created;
  }

  // Rebuild when data, host, language or theme change (chart colours are read from CSS at draw time)
  $effect(() => {
    const d = data;
    const el = host;
    const language = lang;
    void $resolvedTheme;
    untrack(() => draw(d, el, language));
  });

  $effect(() => {
    if (!host || typeof ResizeObserver === 'undefined') return undefined;
    const el = host;
    const ro = new ResizeObserver(() => chart?.setSize(el.clientWidth || 800, HEIGHT));
    ro.observe(el);
    return () => ro.disconnect();
  });

  onDestroy(() => {
    alive = false;
    loadToken++;
    renderToken++;
    destroyChart();
  });

  const at = $derived(data ? (cursor ?? data.xs.length - 1) : null);
  const fmt = (v, d = 1) => (v === null || v === undefined ? '—' : v.toFixed(d));
  const val = (role) => (data && at !== null ? data.cols[data.topics[role]][at] : null);
  const runAt = $derived(data && at !== null ? data.runs.find((r) => data.xs[at] >= r.from && data.xs[at] < r.to) : null);
  const timeAt = $derived(data && at !== null && cursor !== null
    ? new Date(data.xs[at] * 1000).toLocaleTimeString(lang === 'nl' ? 'nl-NL' : 'en-GB', { hour: '2-digit', minute: '2-digit' })
    : t('now'));
</script>

<div class="panel" data-testid="timeline">
  <div class="panel-head">
    <h2>{t('timelineTitle')}</h2>
    {#if data && at !== null}
      <div class="read" data-testid="timeline-readout">
        <b>{timeAt}</b>
        {#if runAt}<span>{#if runAt.activity !== 'unknown'}<i style:background={`var(${ACTIVITY_VAR[runAt.activity]})`}></i>{/if}{runAt.activity === 'unknown' ? t('activityUnknown') : activityLabel(runAt.activity, lang)}</span>{/if}
        <span><i style:background="var(--warm)"></i>{t('lineFlow')} <b>{fmt(val('flow'))}°</b></span>
        <span><i style:background="var(--cool)"></i>{t('lineReturn')} <b>{fmt(val('ret'))}°</b></span>
        <span><i style:background="var(--cold)"></i>{t('lineOutside')} <b>{fmt(val('outside'))}°</b></span>
        <span><i class="dash"></i>{t('lineTarget')} <b>{fmt(val('target'))}°</b></span>
        <span><i style:background="var(--ink-3)"></i>{t('linePower')} <b>{fmt(data.power[at], 2)} kW</b></span>
      </div>
    {/if}
  </div>
  <div class="body">
    {#if data}<div bind:this={host} class="host"></div>{:else}<p class="empty">{t('timelineEmpty')}</p>{/if}
    {#if data}
      <p class="note" data-testid="timeline-approx">{t('timelineApprox')}{#if data.truncated.length} · <span data-testid="timeline-incomplete">{t('timelineIncomplete')}</span>{/if}</p>
    {/if}
  </div>
</div>
<style>
  .read { display: flex; gap: 6px 16px; flex-wrap: wrap; font-size: 12px; color: var(--ink-2); }
  .read b { font: 500 12px var(--font-data); font-stretch: 87.5%; color: var(--ink); }
  .read i { display: inline-block; width: 10px; height: 3px; border-radius: 2px; vertical-align: middle; margin-right: 5px; }
  .read i.dash { background: repeating-linear-gradient(90deg, var(--ink-3) 0 3px, transparent 3px 6px); }
  .body { padding: 8px; }
  .host { width: 100%; min-height: 250px; }
  .empty { color: var(--ink-3); margin: 16px 8px; }
  .note { color: var(--ink-3); font-size: 11.5px; margin: 4px 8px 0; }
</style>
