<script>
  import { onMount, onDestroy, untrack } from 'svelte';
  import { createChart, historyToUplot, insertBreaks, themedAxes } from '../../lib/uplot.js';
  import { api } from '../../lib/api.js';
  import { language, system } from '../../lib/stores.js';
  import { catalog } from '../../lib/catalog.js';
  import { translate } from '../../lib/i18n/index.js';
  import { resolvedTheme } from '../../lib/theme.js';
  
  /**
   * Chart container component
   * Handles chart rendering, data loading, and updates
   */
  
  // Props are automatically available in Svelte 5
  let { topics, from, to, maxPoints, resolution, height, showLegend } = $props();
  
  let chartInstance = null;
  let containerElement;
  let chartContainer = $state(null);
  let loading = $state(false);
  let error = $state(null);
  let historyData = $state(null);
  
  
  // Resize observer
  let resizeObserver = null;
  
  // Debounce resize
  let resizeTimeout = null;
  
  function debounce(fn, delay) {
    return function() {
      clearTimeout(resizeTimeout);
      resizeTimeout = setTimeout(() => fn.apply(this, arguments), delay);
    };
  }
  
  // Format a value based on topic info
  function formatValue(value, topicInfo) {
    if (value === null || value === undefined) return '—';
    
    if (topicInfo) {
      const { decimals, unit } = topicInfo;
      
      if (decimals !== null && decimals !== undefined) {
        const multiplier = Math.pow(10, decimals);
        const rounded = Math.round(value * multiplier) / multiplier;
        let formatted = rounded.toString();
        
        // Add trailing zeros if needed
        if (decimals > 0) {
          const dotIndex = formatted.indexOf('.');
          if (dotIndex === -1) {
            formatted += '.';
          }
          while (formatted.length - dotIndex - 1 < decimals) {
            formatted += '0';
          }
        }
        
        if (unit) {
          return `${formatted} ${unit}`;
        }
        return formatted;
      }
    }
    
    return String(value);
  }
  
  let loadToken = 0;

  // Load history data from API
  async function loadData() {
    if (topics.length === 0) {
      historyData = null;
      return;
    }
    
    const myLoad = ++loadToken;
    loading = true;
    error = null;
    
    try {
      const params = {
        topics: topics.join(','),
        from,
        to,
        max_points: maxPoints,
      };
      
      if (resolution) {
        params.resolution = resolution;
      }
      
      const res = await api.history(params);
      if (myLoad !== loadToken) return;
      historyData = res;
    } catch (err) {
      if (myLoad !== loadToken) return;
      error = err.message || String(err);
      historyData = null;
    } finally {
      if (myLoad === loadToken) loading = false;
    }
  }
  
  let renderToken = 0;

  function destroyChart() {
    if (chartInstance) {
      chartInstance.destroy();
      chartInstance = null;
    }
  }

  // Create the chart once per data load (called from a single effect, never reads chartInstance reactively)
  async function buildChart(data, el, legend, lang, timeZone) {
    const token = ++renderToken;
    destroyChart();
    if (!el || !data) return;
    const w = el.clientWidth || 800;
    const h = height || 300;
    const opts = historyToUplot(data, catalog, { lang, timeZone });
    opts.axes = themedAxes(opts.axes);
    opts.width = w;
    opts.height = h;
    opts.legend.show = legend;
    const created = await createChart(el, opts);
    if (token !== renderToken) {
      created.destroy();
      return;
    }
    chartInstance = created;
  }

  // Resizes adjust the existing chart in place
  function handleResize() {
    if (!chartInstance || !chartContainer) return;
    chartInstance.setSize(chartContainer.clientWidth || 800, height || 300);
  }

  onMount(() => {
    if (window.ResizeObserver && chartContainer) {
      resizeObserver = new ResizeObserver(debounce(handleResize, 100));
      resizeObserver.observe(chartContainer);
    }
  });

  onDestroy(() => {
    renderToken++;
    destroyChart();
    if (resizeObserver) {
      resizeObserver.disconnect();
      resizeObserver = null;
    }
    if (resizeTimeout) clearTimeout(resizeTimeout);
  });

  // Reload when the query changes (reads only props; loadData state writes are untracked)
  $effect(() => {
    topics; from; to; maxPoints; resolution;
    untrack(() => loadData());
  });

  // Rebuild the chart when data, container or legend flag changes
  $effect(() => {
    const data = historyData;
    const el = chartContainer;
    const legend = showLegend;
    const lang = $language;
    void $resolvedTheme;
    const timeZone = $system?.tz || undefined;
    untrack(() => buildChart(data, el, legend, lang, timeZone));
  });

  // Status message, interpolated as text (never markup)
  let status = $derived.by(() => {
    if (loading) return { kind: 'loading', text: translate($language, 'charts.loading') };
    if (error) return { kind: 'error', text: String(error) };
    if (!historyData) return { kind: 'empty', text: translate($language, 'charts.no_data') };
    return null;
  });
</script>

<div class="chart-container-wrapper" bind:this={containerElement}>
  {#if topics.length > 0}
    <div class="chart-container" bind:this={chartContainer} data-testid="chart-container"></div>
  {:else}
    <div class="chart-placeholder">
      {translate($language, 'charts.no_topics_selected')}
    </div>
  {/if}
  
  {#if status}
    <div class="status {status.kind}">{status.text}</div>
  {/if}
</div>

<style>
  .chart-container-wrapper {
    position: relative;
    width: 100%;
    height: 100%;
  }
  
  .chart-container {
    width: 100%;
  }
  
  .chart-placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    background: var(--panel-2);
    border: 1px dashed var(--line-2);
    border-radius: 4px;
    color: var(--ink-2);
  }
  
  .status {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    padding: 12px 24px;
    border-radius: 4px;
    background: color-mix(in srgb, var(--ground) 85%, transparent);
    color: var(--ink);
    font-size: 14px;
  }
  
  .status.loading {
    background: color-mix(in srgb, var(--ground) 85%, transparent);
  }
  
  .status.error {
    background: color-mix(in srgb, var(--fail) 85%, transparent);
  }
</style>
