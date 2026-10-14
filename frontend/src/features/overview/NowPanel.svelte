<script module>
  /** Server-local date (YYYY-MM-DD) of the response's `to`, in the response's time zone. */
  export function todayLabel(result) {
    if (!result?.tz || !Number.isFinite(result?.to)) return null;
    try {
      return new Intl.DateTimeFormat('en-CA', { timeZone: result.tz, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(result.to));
    } catch {
      return null;
    }
  }

  /** kWh consumed/produced and COP for today's period of `GET /api/energy?period=day`, all modes summed. */
  export function todayTotals(result) {
    const label = todayLabel(result);
    const modes = label ? result?.periods?.[label] : null;
    if (!modes) return null;
    let consumed = 0;
    let produced = 0;
    for (const m of Object.values(modes ?? {})) {
      consumed += m?.consumption_kwh ?? 0;
      produced += m?.production_kwh ?? 0;
    }
    return { consumed, produced, cop: consumed > 0 ? produced / consumed : null };
  }

  /** Which power pair the panel shows for an activity. */
  export function nowMode(activity) {
    if (activity === 'dhw') return 'dhw';
    if (activity === 'cooling') return 'cool';
    return 'heat';
  }
</script>

<script>
  import { api } from '../../lib/api.js';
  import { translate } from '../../lib/i18n/index.js';
  import { activityOf } from '../../lib/format.js';
  import { liveCop, powerPairs } from '../../lib/domain/power.js';

  let { stateData = null, profile = null, lang = 'en' } = $props();
  const t = (key, params) => translate(lang, `overview.${key}`, params);

  function watts(key) {
    const tv = stateData?.topics?.[key];
    return tv && !tv.sentinel && typeof tv.value === 'number' ? tv.value : null;
  }
  const mode = $derived(nowMode(activityOf(stateData, profile)));
  const pair = $derived(powerPairs(profile).pairs[mode]);
  const out = $derived(watts(pair[0]));
  const inn = $derived(watts(pair[1]));
  const cop = $derived(liveCop(stateData?.topics, profile, mode));
  const showBar = $derived(mode !== 'cool' && out !== null && inn !== null && out > inn);
  const MODE_KEY = { heat: 'nowHeating', dhw: 'nowDhw', cool: 'nowCooling' };
  const freq = $derived(watts('main/Compressor_Freq'));
  const pump = $derived(watts('main/Pump_Flow'));
  const kw = (w) => (w === null ? '—' : (w / 1000).toFixed(2));
  const total = $derived(Math.max(out ?? 0, inn ?? 0) || 1);

  let today = $state(null);
  const ENERGY_REFRESH_MS = 15 * 60 * 1000;
  $effect(() => {
    let alive = true;
    const load = () => api.energy({ period: 'day' }).then((r) => { if (alive) today = todayTotals(r); }, () => { if (alive) today = null; });
    load();
    const timer = setInterval(load, ENERGY_REFRESH_MS);
    return () => { alive = false; clearInterval(timer); };
  });
</script>

<div class="panel now">
  <div class="top">
    <div class="tag">{t('nowTitle')} · <span data-testid="now-mode">{t(MODE_KEY[mode])}</span></div>
    <div class="cop">
      <span class="big" data-testid="now-cop">{cop ? cop.value.toFixed(1) : '—'}</span>
      <span class="lbl"><span data-testid="now-cop-label">{mode === 'cool' ? 'EER' : t('cop')}</span><span class="num sub" data-testid="now-power">{t('powerOutIn', { out: kw(out), in: kw(inn) })}</span></span>
    </div>
    {#if showBar}
      <div class="bar" data-testid="now-bar" aria-hidden="true">
        <i style:width={`${((inn ?? 0) / total) * 100}%`} style:background="var(--ink-2)"></i>
        <i style:width={`${(Math.max(0, (out ?? 0) - (inn ?? 0)) / total) * 100}%`} style:background="var(--cold)"></i>
      </div>
      <div class="bar-note"><span>{t('fromGrid')}</span><span>{t('fromAir')}</span></div>
    {/if}
  </div>
  <div class="kv">
    <div><div class="tag">{t('compressorFreq')}</div><div class="v" data-testid="now-compressor">{freq === null ? '—' : freq}<small>Hz</small></div></div>
    <div><div class="tag">{t('pump')}</div><div class="v" data-testid="now-pump">{pump === null ? '—' : pump.toFixed(1)}<small>l/min</small></div></div>
    {#if today}
      <div><div class="tag">{t('today')}</div><div class="v" data-testid="now-today">{today.consumed.toFixed(1)}<small>{t('kwhIn')}</small></div></div>
      <div><div class="tag">{t('todayCop')}</div><div class="v">{today.cop === null ? '—' : today.cop.toFixed(1)}</div></div>
    {/if}
  </div>
</div>

<style>
  .top { padding: 18px; }
  .cop { display: flex; align-items: baseline; gap: 10px; }
  .big { font: 400 64px/0.9 var(--font-data); font-stretch: 75%; letter-spacing: -.03em; font-variant-numeric: tabular-nums; }
  .lbl { display: flex; flex-direction: column; gap: 3px; color: var(--ink-2); font-size: 12.5px; }
  .sub { font-size: 11px; white-space: nowrap; color: var(--ink-3); }
  .bar { height: 6px; border-radius: 3px; background: var(--panel-2); display: flex; overflow: hidden; margin: 14px 0 6px; }
  .bar i { display: block; height: 100%; }
  .bar-note { display: flex; justify-content: space-between; color: var(--ink-3); font-size: 11.5px; }
  .kv { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1px; background: var(--line); border-top: 1px solid var(--line); }
  .kv > div { background: var(--panel); padding: 11px 16px; }
  .v { font: 500 18px/1.2 var(--font-data); font-stretch: 87.5%; margin-top: 3px; }
  .v small { font-size: 11px; color: var(--ink-3); margin-left: 3px; font-weight: 400; }
</style>
