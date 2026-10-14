<script>
  /** Energy screen (spec §7.3): kWh per day/month/year per mode, computed by the server
   * (GET /api/energy?period=) in its configured time zone. Estimate label when the main/ pair is used.
   * S0 WatthourTotal meters are shown as cumulative readings in kWh. No chart library: plain table.
   */
  import { language, profile, state as stateStore } from '../../lib/stores.js';
  import { api } from '../../lib/api.js';
  import { translate } from '../../lib/i18n/index.js';
  import { topicByKey } from '../../lib/catalog.js';
  import { POWER_MODES, hasExtra } from '../../lib/domain/power.js';
  import { s0Meters } from '../../lib/domain/rules.js';

  const PERIODS = ['day', 'month', 'year'];

  let period = $state('day');
  let result = $state(null);
  let loading = $state(false);
  let error = $state(null);

  const ready = $derived(Boolean($profile && $stateStore));
  const estimate = $derived(result ? result.estimate : !hasExtra($profile));

  // Reload when the profile arrives (has_extra decides the topics server-side) or the period changes.
  $effect(() => {
    if (!ready) return undefined;
    const chosen = period;
    void $profile?.has_extra?.value;
    let alive = true;
    loading = true;
    error = null;
    api.energy({ period: chosen }).then(
      (body) => {
        if (!alive) return;
        result = body;
        loading = false;
      },
      (err) => {
        if (!alive) return;
        error = err.message || String(err);
        result = null;
        loading = false;
      },
    );
    return () => {
      alive = false;
    };
  });

  const rows = $derived(
    Object.entries(result?.periods ?? {})
      .sort(([a], [b]) => (a < b ? 1 : -1))
      .flatMap(([label, modes]) =>
        POWER_MODES.filter((mode) => modes[mode]).map((mode) => ({ label, mode, ...modes[mode] })),
      ),
  );
  const totals = $derived({
    production: rows.reduce((sum, r) => sum + r.production_kwh, 0),
    consumption: rows.reduce((sum, r) => sum + r.consumption_kwh, 0),
  });
  // WatthourTotal is a cumulative meter reading in Wh
  const s0 = $derived(
    s0Meters.flatMap((key) => {
      const tv = meterValue(key);
      return tv ? [{ key, kwh: tv.value / 1000 }] : [];
    }),
  );

  function meterValue(key) {
    const tv = $stateStore?.topics?.[key];
    return tv && !tv.sentinel && typeof tv.value === 'number' && Number.isFinite(tv.value) ? tv : null;
  }

  function formatKwh(value) {
    if (value === undefined || value === null || Number.isNaN(value)) return translate($language, 'energy.no_data');
    return value.toFixed(value < 10 ? 2 : 1);
  }

  function formatCop(production, consumption) {
    return consumption > 0 ? (production / consumption).toFixed(2) : translate($language, 'energy.no_data');
  }
</script>

<svelte:head>
  <title>{translate($language, 'energy.title')}</title>
</svelte:head>

<div class="screen" data-testid="screen-energy">
  <h1>{translate($language, 'energy.title')}</h1>

  <div class="period-selector" data-testid="period-selector">
    {#each PERIODS as p}
      <button
        type="button"
        class:active={period === p}
        onclick={() => { period = p; }}
        data-testid={`period-${p}`}
      >
        {translate($language, `energy.${p}`)}
      </button>
    {/each}
  </div>

  {#if s0.length}
    <section class="s0-section panel" data-testid="s0-section">
      <div class="panel-head"><h2>{translate($language, 'energy.s0_meters')}</h2></div>
      <div class="panel-body">
      <p class="hint">{translate($language, 'energy.s0_cumulative')}</p>
      <div class="s0-values">
        {#each s0 as meter}
          <div class="s0-value" data-testid={`s0-${meter.key.replace(/\//g, '-')}`}>
            {topicByKey(meter.key)?.label?.[$language] || meter.key}: {meter.kwh.toFixed(1)} {translate($language, 'energy.kwh')}
          </div>
        {/each}
      </div>
      </div>
    </section>
  {/if}

  {#if !ready || loading}
    <p data-testid="loading">{translate($language, 'energy.loading')}</p>
  {:else if error}
    <p class="error" data-testid="error">{error}</p>
  {:else if !rows.length}
    <p data-testid="no-data">{translate($language, 'energy.no_data')}</p>
  {:else}
    <section class="energy-table panel" data-testid="energy-table">
      <div class="panel-head"><h2>{translate($language, 'energy.chart_title')}</h2></div>
      <div class="table-scroll panel-body">
      <table>
        <thead>
          <tr>
            <th>{translate($language, 'energy.period')}</th>
            <th>{translate($language, 'energy.mode')}</th>
            <th>{translate($language, 'energy.produced')}</th>
            <th>{translate($language, 'energy.consumed')}</th>
            <th>{translate($language, 'energy.cop')}</th>
          </tr>
        </thead>
        <tbody>
          {#each rows as row (row.label + row.mode)}
            <tr data-testid={`energy-row-${row.label}-${row.mode}`}>
              <td>{row.label}</td>
              <td data-testid={`mode-${row.mode}`}>{translate($language, `energy.${row.mode}`)}</td>
              <td data-testid={`prod-${row.label}-${row.mode}`}>{formatKwh(row.production_kwh)} {translate($language, 'energy.kwh')}</td>
              <td data-testid={`cons-${row.label}-${row.mode}`}>{formatKwh(row.consumption_kwh)} {translate($language, 'energy.kwh')}</td>
              <td data-testid={`cop-${row.label}-${row.mode}`}>{formatCop(row.production_kwh, row.consumption_kwh)}</td>
            </tr>
          {/each}
        </tbody>
        <tfoot>
          <tr>
            <td colspan="2"><strong>{translate($language, 'energy.total')}</strong></td>
            <td data-testid="total-prod"><strong>{formatKwh(totals.production)} {translate($language, 'energy.kwh')}</strong></td>
            <td data-testid="total-cons"><strong>{formatKwh(totals.consumption)} {translate($language, 'energy.kwh')}</strong></td>
            <td></td>
          </tr>
        </tfoot>
      </table>
      </div>
    </section>
  {/if}

  {#if estimate}
    <p class="estimate-label" data-testid="estimate-label">{translate($language, 'energy.estimate')}</p>
  {/if}
</div>

<style>
  .screen {
    padding: 1rem;
    max-width: 1200px;
    margin: 0 auto;
  }
  h1 {
    margin: 0 0 1rem;
    font: 600 22px/1.1 var(--font-ui);
  }
  .error {
    color: var(--fail-ink);
  }
  .period-selector {
    margin: 1rem 0;
    display: flex;
    gap: 0.5rem;
  }
  .period-selector button {
    padding: 0.5rem 1rem;
  }
  .period-selector button.active {
    background: var(--ink);
    color: var(--ground);
    border-color: var(--ink);
  }
  .s0-section {
    margin: 1.5rem 0;
  }
  .s0-values {
    display: flex;
    gap: 2rem;
    flex-wrap: wrap;
  }
  .s0-value {
    padding: 0.5rem 1rem;
    background: var(--panel-2);
    border-radius: var(--r-control);
    border: 1px solid var(--line);
    font-family: var(--font-data);
  }
  .energy-table {
    margin-top: 1.5rem;
  }
  .table-scroll {
    overflow-x: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
  }
  th, td {
    padding: 0.5rem;
    text-align: left;
    border-bottom: 1px solid var(--line);
  }
  th {
    background: var(--panel-2);
    font-weight: 500;
  }
  td { font-family: var(--font-data); font-variant-numeric: tabular-nums; }
  tr:hover {
    background: var(--panel-2);
  }
  .hint {
    margin: 0 0 0.5rem;
    color: var(--ink-3);
    font-size: 0.9em;
  }
  .estimate-label {
    margin-top: 1rem;
    color: var(--ink-3);
    font-style: italic;
  }
</style>
