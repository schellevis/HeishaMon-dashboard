<script>
/** Energy screen (spec §7.3) — kWh per day/month/year per mode, computed client-side
 * from 1h rollups (avg × covered_seconds). Uses extra/ power topics when available,
 * otherwise main/ with estimate label. S0 totals shown alongside.
 * Empty splits are omitted. No uplot: bars are hand-written HTML/CSS.
 */
import { get } from 'svelte/store';
import { language, profile, state } from '../lib/stores.js';
import { api } from '../lib/api.js';
import { translate } from '../lib/i18n/index.js';
import { topicByKey } from '../lib/catalog.js';

// Power topic mapping — mirrors backend/heishamon_dashboard/derived.py
const MAIN_POWER = {
  heat: ['main/Heat_Power_Production', 'main/Heat_Power_Consumption'],
  cool: ['main/Cool_Power_Production', 'main/Cool_Power_Consumption'],
  dhw: ['main/DHW_Power_Production', 'main/DHW_Power_Consumption'],
};
const EXTRA_POWER = {
  heat: ['extra/Heat_Power_Production_Extra', 'extra/Heat_Power_Consumption_Extra'],
  cool: ['extra/Cool_Power_Production_Extra', 'extra/Cool_Power_Consumption_Extra'],
  dhw: ['extra/DHW_Power_Production_Extra', 'extra/DHW_Power_Consumption_Extra'],
};
const S0_TOPICS = ['s0/WatthourTotal/1', 's0/WatthourTotal/2'];

// Period configuration
const PERIODS = ['day', 'month', 'year'];
const MODES = ['heat', 'cool', 'dhw'];

/** Get power topics based on profile.has_extra */
function getPowerTopics(profileData) {
  if (!profileData) return { topics: MAIN_POWER, estimate: true };
  const hasExtra = profileData.has_extra?.value === true && !profileData.has_extra.unknown;
  return { topics: hasExtra ? EXTRA_POWER : MAIN_POWER, estimate: !hasExtra };
}

/** Compute energy in kWh from 1h rollup history points.
 * Each point is [bucket_start_ts, avg, covered_seconds].
 * Energy in Joules = avg * covered_seconds (sum over all points).
 * Convert to kWh by dividing by 3,600,000.
 * Returns { production_kwh, consumption_kwh } per mode.
 * Modes with no data (empty points or all null/zero) are omitted.
 */
function computeEnergyFromHistory(history, topics) {
  const result = {};
  for (const mode of MODES) {
    const [prodKey, consKey] = topics[mode];
    const prodSeries = history?.series?.[prodKey];
    const consSeries = history?.series?.[consKey];
    
    if (!prodSeries && !consSeries) continue;

    let prodJ = 0;
    let consJ = 0;

    if (prodSeries) {
      for (const [start, avg, covered] of prodSeries.points) {
        if (avg !== null && covered > 0) {
          prodJ += avg * covered;
        }
      }
    }
    if (consSeries) {
      for (const [start, avg, covered] of consSeries.points) {
        if (avg !== null && covered > 0) {
          consJ += avg * covered;
        }
      }
    }

    // Only include modes with actual data
    if (prodJ > 0 || consJ > 0) {
      // Convert Joules to kWh
      result[mode] = { 
        production_kwh: prodJ / 3_600_000, 
        consumption_kwh: consJ / 3_600_000 
      };
    }
  }
  return result;
}

/** Format kWh value */
function formatKwh(value, lang) {
  if (value === undefined || value === null || isNaN(value)) return translate(lang, 'energy.no_data');
  return value.toFixed(value < 10 ? 2 : 1);
}

/** Format COP value */
function formatCop(value, lang) {
  if (value === undefined || value === null || isNaN(value)) return translate(lang, 'energy.no_data');
  return value.toFixed(2);
}

// Reactive state
let lang = 'en';
let profileData = null;
let stateData = null;
let energyData = null;
let loading = true;
let error = null;
let selectedPeriod = 'day';

// Track profile and state changes
$:
  lang = get(language);

$:
  profileData = get(profile);

$:
  stateData = get(state);

// Compute power topics when profile changes
$:
  if (profileData) {
    const { topics: powerTopics, estimate } = getPowerTopics(profileData);
    const allPowerKeys = [];
    for (const mode of MODES) {
      allPowerKeys.push(...powerTopics[mode]);
    }
    const fetchKeys = [...allPowerKeys, ...S0_TOPICS];
    
    // Fetch energy data
    loadEnergy(fetchKeys, powerTopics);
  }

// Fetch history and compute energy
async function loadEnergy(fetchKeys, powerTopics) {
  if (!fetchKeys || !powerTopics) return;
  
  loading = true;
  error = null;
  
  try {
    const now = Date.now();
    const to = now;
    const from = now - 30 * 24 * 60 * 60 * 1000; // Last 30 days
    
    // Fetch 1h rollup history
    const history = await api.history({
      topics: fetchKeys,
      from,
      to,
      max_points: 10000,
    });
    
    // Compute energy from history
    if (history && history.series) {
      energyData = computeEnergyFromHistory(history, powerTopics);
    } else {
      energyData = {};
    }
    
    // Also fetch S0 values from state
    if (stateData?.topics) {
      const s0Values = {};
      for (const s0Key of S0_TOPICS) {
        const tv = stateData.topics[s0Key];
        if (tv && tv.value !== null && tv.value !== undefined && !isNaN(tv.value)) {
          s0Values[s0Key] = Number(tv.value);
        }
      }
      if (Object.keys(s0Values).length > 0) {
        energyData.s0 = s0Values;
      }
    }
    
  } catch (err) {
    error = err.message || String(err);
    energyData = null;
  } finally {
    loading = false;
  }
}

// Initial check for estimate flag (for display before data loads)
$: estimateFlag = profileData ? getPowerTopics(profileData).estimate : true;
</script>

<svelte:head>
  <title>{translate(lang, 'energy.title')}</title>
</svelte:head>

<div class="screen" data-testid="screen-energy">
  <h1>{translate(lang, 'energy.title')}</h1>
  


  {#if loading}
    <p data-testid="loading">{translate(lang, 'common.loading') || 'Loading...'}</p>
  {:else if error}
    <p class="error" data-testid="error">{error}</p>
  {:else if energyData === null || Object.keys(energyData).length === 0}
    <p data-testid="no-data">{translate(lang, 'energy.no_data')}</p>
  {:else}
    <div class="energy-view">
      <!-- Period selector -->
      <div class="period-selector" data-testid="period-selector">
        {#each PERIODS as p}
          <button 
            class:active={selectedPeriod === p}
            on:click={() => { selectedPeriod = p; }}
            data-testid={`period-${p}`}
          >
            {translate(lang, `energy.${p}`)}
          </button>
        {/each}
      </div>

      <!-- S0 meters display -->
      {#if energyData.s0 && Object.keys(energyData.s0).length > 0}
        <section class="s0-section" data-testid="s0-section">
          <h2>{translate(lang, 'energy.s0_meters')}</h2>
          <div class="s0-values">
            {#each Object.entries(energyData.s0) as [key, value]}
              <div class="s0-value" data-testid={`s0-${key.replace(/\//g, '-')}`}>
                {topicByKey(key)?.label?.[lang] || key}: {value.toFixed(1)} {translate(lang, 'energy.kwh')}
              </div>
            {/each}
          </div>
        </section>
      {/if}

      <!-- Energy table -->
      <section class="energy-table" data-testid="energy-table">
        <h2>{translate(lang, 'energy.chart_title')}</h2>
        <table>
          <thead>
            <tr>
              <th>{translate(lang, 'energy.mode')}</th>
              <th>{translate(lang, 'energy.produced')}</th>
              <th>{translate(lang, 'energy.consumed')}</th>
              <th>{translate(lang, 'energy.cop')}</th>
            </tr>
          </thead>
          <tbody>
            {#each MODES as mode}
              {#if energyData[mode]}
                <tr data-testid={`energy-row-${mode}`}>
                  <td data-testid={`mode-${mode}`}>{translate(lang, `energy.${mode}`)}</td>
                  <td data-testid={`prod-${mode}`}>
                    {formatKwh(energyData[mode].production_kwh, lang)} {translate(lang, 'energy.kwh')}
                  </td>
                  <td data-testid={`cons-${mode}`}>
                    {formatKwh(energyData[mode].consumption_kwh, lang)} {translate(lang, 'energy.kwh')}
                  </td>
                  <td data-testid={`cop-${mode}`}>
                    {#if energyData[mode].consumption_kwh && energyData[mode].consumption_kwh > 0}
                      {formatCop(energyData[mode].production_kwh / energyData[mode].consumption_kwh, lang)}
                    {:else}
                      {translate(lang, 'energy.no_data')}
                    {/if}
                  </td>
                </tr>
              {:else}
                <!-- Empty splits are omitted -->
              {/if}
            {/each}
          </tbody>
          <tfoot>
            <tr>
              <td><strong>{translate(lang, 'energy.total')}</strong></td>
              <td data-testid="total-prod">
                <strong>
                  {formatKwh(
                    MODES.reduce((sum, m) => sum + (energyData[m]?.production_kwh || 0), 0),
                    lang
                  )} {translate(lang, 'energy.kwh')}
                </strong>
              </td>
              <td data-testid="total-cons">
                <strong>
                  {formatKwh(
                    MODES.reduce((sum, m) => sum + (energyData[m]?.consumption_kwh || 0), 0),
                    lang
                  )} {translate(lang, 'energy.kwh')}
                </strong>
              </td>
              <td></td>
            </tr>
          </tfoot>
        </table>
      </section>

      <!-- Summary -->
      {#if estimateFlag}
        <p class="estimate-label" data-testid="estimate-label">
          {translate(lang, 'energy.estimate')}
        </p>
      {/if}
    </div>
  {/if}
</div>

<style>
  .screen {
    padding: 1rem;
    max-width: 1200px;
    margin: 0 auto;
  }
  h1 {
    margin-bottom: 1rem;
  }
  .error {
    color: #d32f2f;
  }
  .period-selector {
    margin: 1rem 0;
    display: flex;
    gap: 0.5rem;
  }
  .period-selector button {
    padding: 0.5rem 1rem;
    border: 1px solid #ccc;
    background: #f5f5f5;
    cursor: pointer;
  }
  .period-selector button.active {
    background: #1976d2;
    color: white;
    border-color: #1976d2;
  }
  .s0-section {
    margin: 2rem 0 1.5rem;
    padding: 1rem;
    background: #f5f5f5;
    border-radius: 4px;
  }
  .s0-values {
    display: flex;
    gap: 2rem;
    flex-wrap: wrap;
  }
  .s0-value {
    padding: 0.5rem 1rem;
    background: white;
    border-radius: 4px;
    border: 1px solid #ddd;
  }
  .energy-table {
    margin-top: 1.5rem;
  }
  table {
    width: 100%;
    border-collapse: collapse;
  }
  th, td {
    padding: 0.75rem;
    text-align: left;
    border-bottom: 1px solid #ddd;
  }
  th {
    background: #f5f5f5;
    font-weight: bold;
  }
  tr:hover {
    background: #f9f9f9;
  }
  .estimate-label {
    margin-top: 1rem;
    color: #666;
    font-style: italic;
  }
</style>
