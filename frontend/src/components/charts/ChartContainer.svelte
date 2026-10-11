<script>
  import { onMount, onDestroy, untrack } from 'svelte';
  import { createChart, historyToUplot, insertBreaks } from '../../lib/uplot.js';
  import { api } from '../../lib/api.js';
  import { state as stateStore, profile, prefs, language } from '../../lib/stores.js';
  import { translate } from '../../lib/i18n/index.js';
  
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
  async function buildChart(data, el, legend) {
    const token = ++renderToken;
    destroyChart();
    if (!el || !data) return;
    const w = el.clientWidth || 800;
    const h = el.clientHeight || height || 300;
    const opts = historyToUplot(data);
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
    chartInstance.setSize(chartContainer.clientWidth || 800, chartContainer.clientHeight || height || 300);
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
    untrack(() => buildChart(data, el, legend));
  });

  // Render status message
  function renderStatus() {
    if (loading) {
      return `<div class="status loading">${translate($language, 'charts.loading')}</div>`;
    }
    
    if (error) {
      return `<div class="status error">${error}</div>`;
    }
    
    if (!historyData) {
      return `<div class="status empty">${translate($language, 'charts.no_data')}</div>`;
    }
    
    return null;
  }
</script>

<div class="chart-container-wrapper" bind:this={containerElement}>
  {#if topics.length > 0}
    <div class="chart-container" bind:this={chartContainer} style={`height: ${height}px`} data-testid="chart-container"></div>
  {:else}
    <div class="chart-placeholder">
      {translate($language, 'charts.no_topics_selected')}
    </div>
  {/if}
  
  {@html renderStatus()}
</div>

<style>
  .chart-container-wrapper {
    position: relative;
    width: 100%;
    height: 100%;
  }
  
  .chart-container {
    width: 100%;
    height: 100%;
  }
  
  .chart-placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    background: var(--bg-secondary);
    border: 1px dashed var(--border);
    border-radius: 4px;
    color: var(--text-secondary);
  }
  
  .status {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    padding: 12px 24px;
    border-radius: 4px;
    background: rgba(0, 0, 0, 0.8);
    color: white;
    font-size: 14px;
  }
  
  .status.loading {
    background: rgba(0, 0, 0, 0.7);
  }
  
  .status.error {
    background: rgba(255, 0, 0, 0.8);
  }
</style>
