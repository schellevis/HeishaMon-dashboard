<script>
  import { translate } from '../../lib/i18n/index.js';
  import { language } from '../../lib/stores.js';
  
  /**
   * Time range selector component
   * Provides controls for selecting time range and resolution
   */
  
  // Props are automatically available in Svelte 5
  let { from, to, resolution, onRangeChange, onResolutionChange } = $props();
  
  // Available range presets
  const rangePresets = [
    { key: '1h', label: 'range_1h', hours: 1 },
    { key: '6h', label: 'range_6h', hours: 6 },
    { key: '12h', label: 'range_12h', hours: 12 },
    { key: '1d', label: 'range_1d', hours: 24 },
    { key: '3d', label: 'range_3d', days: 3 },
    { key: '1w', label: 'range_1w', days: 7 },
    { key: '1m', label: 'range_1m', days: 30 },
    { key: '3m', label: 'range_3m', days: 90 },
    { key: '1y', label: 'range_1y', days: 365 },
  ];
  
  // Available resolutions
  const resolutions = [
    { key: null, label: 'resolution_auto' },
    { key: 'raw', label: 'resolution_raw' },
    { key: '1m', label: 'resolution_1m' },
    { key: '1h', label: 'resolution_1h' },
  ];
  
  // Active preset
  let activePreset = $state(null);
  
  // Calculate preset from current range
  function calculateActivePreset() {
    if (!from || !to) return null;
    
    const rangeMs = to - from;
    const rangeHours = rangeMs / (1000 * 60 * 60);
    const rangeDays = rangeHours / 24;
    
    // Find closest preset
    for (const preset of rangePresets) {
      if (preset.hours && Math.abs(rangeHours - preset.hours) < 1) {
        return preset.key;
      }
      if (preset.days && Math.abs(rangeDays - preset.days) < 1) {
        return preset.key;
      }
    }
    
    return null;
  }
  
  // Apply a range preset
  function applyPreset(preset) {
    const now = Date.now();
    
    if (preset.hours) {
      const fromTs = now - (preset.hours * 1000 * 60 * 60);
      onRangeChange({ from: fromTs, to: now });
    } else if (preset.days) {
      const fromTs = now - (preset.days * 1000 * 60 * 60 * 24);
      onRangeChange({ from: fromTs, to: now });
    }
  }
  
  // Format range display
  function formatRange() {
    if (!from || !to) return translate($language, 'charts.range_custom');
    
    const rangeMs = to - from;
    const rangeHours = rangeMs / (1000 * 60 * 60);
    const rangeDays = rangeHours / 24;
    
    const now = Date.now();
    const endDate = new Date(to);
    const startDate = new Date(from);
    
    // If range ends at now
    if (Math.abs(to - now) < 1000 * 60) {
      if (rangeHours < 1) {
        return `${Math.round(rangeHours * 60)} min`;
      } else if (rangeHours < 24) {
        return `${Math.round(rangeHours)} h`;
      } else if (rangeDays < 7) {
        return `${Math.round(rangeDays)} d`;
      } else if (rangeDays < 30) {
        return `${Math.round(rangeDays / 7)} w`;
      } else if (rangeDays < 365) {
        return `${Math.round(rangeDays / 30)} m`;
      } else {
        return `${Math.round(rangeDays / 365)} y`;
      }
    }
    
    // Custom range
    return `${startDate.toLocaleDateString($language)} - ${endDate.toLocaleDateString($language)}`;
  }
  
  // Handle zoom
  function zoomIn() {
    if (!from || !to) return;
    const center = (from + to) / 2;
    const range = to - from;
    const newRange = range * 0.8;
    onRangeChange({
      from: center - newRange / 2,
      to: center + newRange / 2,
    });
  }
  
  function zoomOut() {
    if (!from || !to) return;
    const center = (from + to) / 2;
    const range = to - from;
    const newRange = range * 1.2;
    onRangeChange({
      from: center - newRange / 2,
      to: center + newRange / 2,
    });
  }
  
  function panLeft() {
    if (!from || !to) return;
    const range = to - from;
    const shift = range * 0.1;
    onRangeChange({
      from: from - shift,
      to: to - shift,
    });
  }
  
  function panRight() {
    if (!from || !to) return;
    const range = to - from;
    const shift = range * 0.1;
    onRangeChange({
      from: from + shift,
      to: to + shift,
    });
  }
  
  // Reset to current preset
  function resetZoom() {
    const preset = rangePresets.find(p => p.key === activePreset);
    if (preset) {
      applyPreset(preset);
    } else {
      // Default to 24h
      applyPreset(rangePresets.find(p => p.key === '1d'));
    }
  }
  
  // Update active preset when from/to changes
  $effect(() => {
    activePreset = calculateActivePreset();
  });
  
  // Handle resolution change
  function handleResolutionChange(event) {
    onResolutionChange(event.target.value || null);
  }
</script>

<div class="time-range-selector">
  <div class="range-presets">
    {#each rangePresets as preset}
      <button
        class:active={activePreset === preset.key}
        onclick={() => applyPreset(preset)}
        title={translate($language, 'charts.' + preset.label)}
      >
        {translate($language, 'charts.' + preset.label)}
      </button>
    {/each}
  </div>
  
  <div class="range-controls">
    <button onclick={zoomIn} title={translate($language, 'charts.zoom_in')}>
      {translate($language, 'charts.zoom_in')}
    </button>
    <button onclick={zoomOut} title={translate($language, 'charts.zoom_out')}>
      {translate($language, 'charts.zoom_out')}
    </button>
    <button onclick={panLeft} title={translate($language, 'charts.pan_left')}>
      &lt;
    </button>
    <button onclick={panRight} title={translate($language, 'charts.pan_right')}>
      &gt;
    </button>
    <button onclick={resetZoom} title={translate($language, 'charts.reset_zoom')}>
      {translate($language, 'charts.reset_zoom')}
    </button>
  </div>
  
  <div class="resolution-selector">
    <span>{translate($language, 'charts.resolution_label')}: </span>
    <select
      value={resolution ?? ''}
      onchange={handleResolutionChange}
      data-testid="resolution-select"
    >
      {#each resolutions as res}
        <option value={res.key || ''} selected={(res.key || '') === (resolution ?? '')}>{translate($language, 'charts.' + res.label)}</option>
      {/each}
    </select>
  </div>
  
  <div class="range-display">
    {formatRange()}
  </div>
</div>

<style>
  .time-range-selector {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    align-items: center;
    padding: 8px 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 12px;
  }
  
  .range-presets {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
  }
  
  .range-presets button {
    padding: 4px 8px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg);
    color: var(--text);
    cursor: pointer;
    font-size: 12px;
  }
  
  .range-presets button:hover {
    background: var(--bg-hover);
  }
  
  .range-presets button.active {
    background: var(--primary);
    color: white;
    border-color: var(--primary);
  }
  
  .range-controls {
    display: flex;
    gap: 4px;
  }
  
  .range-controls button {
    padding: 4px 8px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg);
    color: var(--text);
    cursor: pointer;
    font-size: 12px;
  }
  
  .range-controls button:hover {
    background: var(--bg-hover);
  }
  
  .resolution-selector {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
  }
  
  .resolution-selector select {
    padding: 4px 8px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg);
    color: var(--text);
    cursor: pointer;
  }
  
  .range-display {
    margin-left: auto;
    padding: 4px 8px;
    background: var(--bg-secondary);
    border-radius: 4px;
    font-size: 12px;
    color: var(--text-secondary);
  }
</style>
