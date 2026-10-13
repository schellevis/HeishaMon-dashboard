<script>
  import { onMount, onDestroy } from 'svelte';
  import { state as stateStore, profile, prefs, language } from '../../lib/stores.js';
  import { translate } from '../../lib/i18n/index.js';
  import { api } from '../../lib/api.js';
  import ChartContainer from './ChartContainer.svelte';
  import TimeRangeSelector from './TimeRangeSelector.svelte';
  import TopicSelector from './TopicSelector.svelte';
  import PresetSelector from './PresetSelector.svelte';
  import { catalog, topicByKey } from '../../lib/catalog.js';
  import { historyToUplot, getBreakChecker, insertBreaks } from '../../lib/uplot.js';
  
  /**
   * Charts screen implementation
   * Displays historical data for selected topics with configurable time ranges
   */
  
  // Time range state
  let from = $state(null);
  let to = $state(null);
  let resolution = $state(null); // null = auto
  let maxPoints = $state(1000);
  
  // Selected topics
  let selectedTopics = $state([]);
  
  // UI state
  let showTopicSelector = $state(false);
  let showPresetSelector = $state(false);
  let chartHeight = $state(400);
  let showLegend = $state(true);
  
  // Data state
  let csvUrl = $state('');
  
  // Track initial load
  let initialized = $state(false);
  
  // Auto-select topics based on profile on first load
  $effect(() => {
    if ($profile && !initialized && selectedTopics.length === 0) {
      // Auto-select some default topics for the current profile
      const defaultTopics = getDefaultTopics($profile);
      selectedTopics = defaultTopics.filter(key => {
        const visibility = $prefs?.topic_visibility?.[key] || 'visible';
        return visibility !== 'ignored';
      });
      initialized = true;
    }
  });
  
  // Update CSV URL when query changes
  $effect(() => {
    if (selectedTopics.length > 0 && from && to) {
      const params = new URLSearchParams({
        topics: selectedTopics.join(','),
        from,
        to,
        max_points: maxPoints,
      });
      if (resolution) {
        params.set('resolution', resolution);
      }
      csvUrl = `${api.historyCsvUrl({})}?${params.toString()}`;
    } else {
      csvUrl = '';
    }
  });
  
  // Get default topics based on profile
  function getDefaultTopics(profile) {
    if (!profile) return [];
    
    const defaults = [];
    
    // Always include outside temperature if available
    if (catalog.topics.some(t => t.key === 'main/Outside_Temp')) {
      defaults.push('main/Outside_Temp');
    }
    
    // Include water temperatures
    if (catalog.topics.some(t => t.key === 'main/Main_Outlet_Temp')) {
      defaults.push('main/Main_Outlet_Temp');
    }
    if (catalog.topics.some(t => t.key === 'main/Main_Inlet_Temp')) {
      defaults.push('main/Main_Inlet_Temp');
    }
    
    return defaults;
  }
  
  // Handle range change
  function handleRangeChange({ from: newFrom, to: newTo }) {
    from = newFrom;
    to = newTo;
  }
  
  // Handle resolution change
  function handleResolutionChange(newResolution) {
    resolution = newResolution;
  }
  
  // Handle topic selection
  function handleTopicSelection(topics) {
    selectedTopics = topics;
  }
  
  // Handle preset selection
  function handlePresetSelection(topics) {
    selectedTopics = topics;
    showTopicSelector = false;
    showPresetSelector = false;
  }
  
  // Toggle topic selector
  function toggleTopicSelector() {
    showTopicSelector = !showTopicSelector;
    showPresetSelector = false;
  }
  
  // Toggle preset selector
  function togglePresetSelector() {
    showPresetSelector = !showPresetSelector;
    showTopicSelector = false;
  }
  
  // Set default time range (last 24 hours)
  function setDefaultRange() {
    const now = Date.now();
    const twentyFourHoursAgo = now - (24 * 60 * 60 * 1000);
    from = twentyFourHoursAgo;
    to = now;
  }
  
  onMount(() => {
    setDefaultRange();
    
    // Load prefs and apply saved presets if any
    if ($prefs && $prefs.chart_presets && $prefs.chart_presets.length > 0) {
      // Could auto-load a saved preset, but for now we'll keep it manual
    }
  });
  
  onDestroy(() => {
    // Cleanup
  });
  
  // Chart plot height: smaller on phones; the legend is laid out below it by uPlot.
  $effect(() => {
    const narrow = typeof window !== 'undefined' && window.innerWidth < 640;
    chartHeight = narrow ? 280 : 400;
  });
</script>

<div class="charts-screen" data-testid="screen-charts">
  <h2>{translate($language, 'charts.charts_title')}</h2>
  
  <div class="chart-controls">
    <div class="control-bar">
      <TimeRangeSelector
        from={from}
        to={to}
        resolution={resolution}
        onRangeChange={handleRangeChange}
        onResolutionChange={handleResolutionChange}
      />
      
      <div class="control-actions">
        <button onclick={togglePresetSelector}>
          {translate($language, 'charts.presets_label')}
        </button>
        <button onclick={toggleTopicSelector}>
          {translate($language, 'charts.add_topic_label')}
        </button>
        {#if csvUrl && selectedTopics.length > 0}
          <a href={csvUrl} download class="csv-button">
            {translate($language, 'charts.csv_export_label')}
          </a>
        {/if}
      </div>
    </div>
    
    {#if showPresetSelector}
      <div class="selector-popup">
        <PresetSelector
          selectedTopics={selectedTopics}
          onSelectPreset={handlePresetSelection}
          onTopicsChange={handleTopicSelection}
        />
      </div>
    {/if}
    
    {#if showTopicSelector}
      <div class="selector-popup">
        <TopicSelector
          selected={selectedTopics}
          onSelect={handleTopicSelection}
          maxTopics={20}
        />
      </div>
    {/if}
  </div>
  
  <div class="chart-area">
    {#if selectedTopics.length > 0 && from && to}
      <ChartContainer
        topics={selectedTopics}
        from={from}
        to={to}
        maxPoints={maxPoints}
        resolution={resolution}
        height={chartHeight}
        showLegend={showLegend}
      />
    {:else if selectedTopics.length === 0}
      <div class="empty-state">
        <p>{translate($language, 'charts.no_topics_selected')}</p>
        <button onclick={toggleTopicSelector}>
          {translate($language, 'charts.add_topic_label')}
        </button>
      </div>
    {/if}
  </div>
</div>

<style>
  .charts-screen {
    padding: 0;
    height: 100%;
    display: flex;
    flex-direction: column;
  }
  
  .charts-screen h2 {
    margin: 0 0 16px 0;
    font-size: 20px;
  }
  
  .chart-controls {
    margin-bottom: 12px;
  }
  
  .control-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    align-items: center;
    justify-content: space-between;
  }
  
  .control-actions {
    display: flex;
    gap: 8px;
  }
  
  .control-actions button,
  .control-actions a {
    padding: 8px 12px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg);
    color: var(--text);
    cursor: pointer;
    font-size: 12px;
    text-decoration: none;
    display: flex;
    align-items: center;
  }
  
  .control-actions button:hover,
  .control-actions a:hover {
    background: var(--bg-hover);
  }
  
  .csv-button {
    background: var(--primary);
    color: white;
  }
  
  .csv-button:hover {
    background: var(--primary-dark);
  }
  
  .selector-popup {
    margin-top: 12px;
  }
  
  .chart-area {
    flex: 1;
    min-height: 0;
  }
  
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    min-height: 300px;
    border: 2px dashed var(--border);
    border-radius: 8px;
    background: var(--bg-secondary);
  }
  
  .empty-state p {
    color: var(--text-secondary);
    margin-bottom: 16px;
  }
  
  .empty-state button {
    padding: 12px 24px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--primary);
    color: white;
    cursor: pointer;
    font-size: 14px;
  }
  
  .empty-state button:hover {
    background: var(--primary-dark);
  }
</style>
