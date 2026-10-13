<script>
  import { translate } from '../../lib/i18n/index.js';
  import { catalog, topicByKey } from '../../lib/catalog.js';
  import { profile, prefs, language } from '../../lib/stores.js';
  
  /**
   * Topic selector component
   * Allows users to select topics for charting
   */
  
  // Props are automatically available in Svelte 5
  let { selected, onSelect, maxTopics } = $props();
  
  // Filter state
  let filterText = $state('');
  let showIgnored = $state(false);
  
  // Get topic visibility from prefs
  let topicVisibility = $derived($prefs?.topic_visibility || {});
  
  // Profile for filtering
  let currentProfile = $derived($profile);
  
  // Available topics from catalog
  const allTopics = catalog.topics || [];
  
  // Filtered topics
  let filteredTopics = $derived(filterTopics());
  
  // Category groups
  let categories = $derived(groupByCategory(filteredTopics));
  
  function filterTopics() {
    if (!allTopics) return [];
    
    return allTopics.filter(topic => {
      const key = topic.key;
      
      // Filter by text
      if (filterText) {
        const search = filterText.toLowerCase();
        const label = (topic.label?.en || '').toLowerCase();
        if (!label.includes(search) && !key.toLowerCase().includes(search)) {
          return false;
        }
      }
      
      // Filter by ignored state
      const visibility = topicVisibility[key] || 'visible';
      if (!showIgnored && visibility === 'ignored') {
        return false;
      }
      
      // Filter by the user's feature overrides
      if (!isTopicRelevant(topic)) return false;
      
      return true;
    });
  }
  
  function groupByCategory(topics) {
    const groups = {};
    
    for (const topic of topics) {
      const category = topic.category || 'other';
      if (!groups[category]) {
        groups[category] = [];
      }
      groups[category].push(topic);
    }
    
    return groups;
  }
  
  // Check if a topic is relevant: only the user's feature overrides hide topics
  function isTopicRelevant(topic) {
    return !(topic.feature && $prefs?.feature_overrides?.[topic.feature] === 'hide');
  }
  
  // Get display name for a topic
  function getDisplayName(topic) {
    const visibility = topicVisibility[topic.key] || 'visible';
    const label = topic.label?.en || topic.key;
    
    let prefix = '';
    switch (visibility) {
      case 'ignored':
        prefix = '(ignored) ';
        break;
      case 'hidden':
        prefix = '(hidden) ';
        break;
    }
    
    return `${prefix}${label}`;
  }
  
  // Toggle topic selection
  function toggleTopic(key) {
    if (selected.includes(key)) {
      onSelect(selected.filter(k => k !== key));
    } else {
      if (selected.length >= maxTopics) return;
      onSelect([...selected, key]);
    }
  }
  
  // Select all visible topics
  function selectAll() {
    const visibleTopics = filteredTopics.filter(topic => {
      const visibility = topicVisibility[topic.key] || 'visible';
      return visibility !== 'ignored';
    });
    onSelect(visibleTopics.map(t => t.key).slice(0, maxTopics));
  }
  
  // Clear selection
  function clearSelection() {
    onSelect([]);
  }
  
  // Get category label
  function getCategoryLabel(category) {
    const labels = {
      temperature: 'Temperature',
      flow: 'Flow',
      pressure: 'Pressure',
      power: 'Power',
      energy: 'Energy',
      status: 'Status',
      settings: 'Settings',
      sensor: 'Sensors',
      derived: 'Derived',
      other: 'Other',
    };
    return labels[category] || category;
  }
</script>

<div class="topic-selector">
  <div class="selector-header">
    <div class="filter-controls">
      <input
        type="text"
        bind:value={filterText}
        placeholder={translate($language, 'charts.filter_topics_placeholder')}
      />
      <label>
        <input type="checkbox" bind:checked={showIgnored} />
        {translate($language, 'charts.show_all')}
      </label>
    </div>
    
    <div class="selection-count">
      {selected.length} / {maxTopics} {translate($language, 'charts.selected_topics_label')}
    </div>
  </div>
  
  {#if selected.length > 0}
    <div class="selected-list">
      <h4>{translate($language, 'charts.selected_topics_label')}:</h4>
      <div class="selected-topics">
        {#each selected as key}
          {@const topic = topicByKey(key)}
          {#if topic}
            <span class="topic-tag">
              {getDisplayName(topic)}
              <button onclick={() => toggleTopic(key)}>×</button>
            </span>
          {/if}
        {/each}
      </div>
    </div>
  {/if}
  
  <div class="available-list">
    {#if filterText && filteredTopics.length === 0}
      <div class="no-results">
        {translate($language, 'charts.no_topics_selected')}
      </div>
    {:else}
      {#each Object.entries(categories) as [category, categoryTopics]}
        <details class="category-group">
          <summary>
            {getCategoryLabel(category)} ({categoryTopics.length})
          </summary>
          <div class="category-topics">
            {#each categoryTopics as topic}
              <label class:disabled={selected.length >= maxTopics && !selected.includes(topic.key)}>
                <input
                  type="checkbox"
                  checked={selected.includes(topic.key)}
                  onchange={() => toggleTopic(topic.key)}
                  disabled={selected.length >= maxTopics && !selected.includes(topic.key)}
                />
                <span class="topic-label" title={topic.key}>
                  {getDisplayName(topic)}
                </span>
                {#if topic.unit}
                  <span class="topic-unit">{topic.unit}</span>
                {/if}
              </label>
            {/each}
          </div>
        </details>
      {/each}
    {/if}
  </div>
  
  <div class="selection-actions">
    <button onclick={clearSelection}>
      {translate($language, 'charts.clear_selection')}
    </button>
  </div>
</div>

<style>
  .topic-selector {
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--bg);
    max-height: 500px;
    overflow: auto;
  }
  
  .selector-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px;
    border-bottom: 1px solid var(--border);
  }
  
  .filter-controls {
    display: flex;
    gap: 12px;
    align-items: center;
  }
  
  .filter-controls input[type="text"] {
    padding: 6px 12px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg);
    color: var(--text);
    min-width: 150px;
  }
  
  .filter-controls label {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    cursor: pointer;
  }
  
  .selection-count {
    font-size: 12px;
    color: var(--text-secondary);
  }
  
  .selected-list {
    padding: 12px;
    border-bottom: 1px solid var(--border);
  }
  
  .selected-list h4 {
    margin: 0 0 8px 0;
    font-size: 12px;
    color: var(--text-secondary);
  }
  
  .selected-topics {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  
  .topic-tag {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 8px;
    background: var(--primary);
    color: white;
    border-radius: 4px;
    font-size: 12px;
  }
  
  .topic-tag button {
    background: none;
    border: none;
    color: white;
    cursor: pointer;
    padding: 0 0 0 4px;
    font-size: 12px;
  }
  
  .topic-tag button:hover {
    text-decoration: line-through;
  }
  
  .available-list {
    padding: 8px;
  }
  
  .no-results {
    padding: 12px;
    color: var(--text-secondary);
    text-align: center;
    font-style: italic;
  }
  
  .category-group {
    margin-bottom: 8px;
  }
  
  .category-group summary {
    padding: 6px 12px;
    cursor: pointer;
    font-size: 12px;
    font-weight: 500;
    color: var(--text);
    background: var(--bg-secondary);
    border-radius: 4px;
  }
  
  .category-group summary:hover {
    background: var(--bg-hover);
  }
  
  .category-topics {
    padding: 8px 12px;
    display: grid;
    gap: 4px;
  }
  
  .category-topics label {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 8px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 12px;
  }
  
  .category-topics label:hover {
    background: var(--bg-hover);
  }
  
  .category-topics label.disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .category-topics label input[type="checkbox"] {
    margin: 0;
    accent-color: var(--primary);
  }
  
  .topic-label {
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  
  .topic-unit {
    color: var(--text-secondary);
    font-size: 11px;
  }
  
  .selection-actions {
    padding: 8px 12px;
    border-top: 1px solid var(--border);
  }
  
  .selection-actions button {
    padding: 6px 12px;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg);
    color: var(--text);
    cursor: pointer;
    font-size: 12px;
  }
  
  .selection-actions button:hover {
    background: var(--bg-hover);
  }
</style>
