<script>
  import CommandControl from './CommandControl.svelte';
  import { catalog as defaultCatalog } from '../../lib/catalog.js';
  import { categoryRelevant, groupCatalog } from './grouping.js';
  import { translate } from '../../lib/i18n/index.js';
  import {
    commands as commandsStore,
    language,
    prefs as prefsStore,
    profile as profileStore,
    updatePrefs,
    state as stateStore,
  } from '../../lib/stores.js';

  let { catalogData = null } = $props();

  const source = $derived(catalogData ?? defaultCatalog);
  const groups = $derived(groupCatalog(source));

  function openCategory(id) {
    const relevant = categoryRelevant(id, $profileStore);
    return relevant || $prefsStore?.feature_overrides?.[id] === 'show';
  }

  async function showAnyway(id) {
    await updatePrefs((cur) => ({ feature_overrides: { ...cur.feature_overrides, [id]: 'show' } }));
  }
</script>

{#snippet rows(items)}
  <div class="rows">
    {#each items as entry (entry.name || entry.path)}
      <CommandControl
        {entry}
        profile={$profileStore}
        live={$stateStore}
        prefs={$prefsStore}
        lang={$language}
        commandMap={$commandsStore}
        catalogData={source}
      />
    {/each}
  </div>
{/snippet}

<section data-testid="screen-settings" class="settings">
  <h1>{translate($language, 'settings.title')}</h1>
  {#if $stateStore?.listen_only_suspected}
    <p class="banner" data-testid="listen-only" role="status">{translate($language, 'settings.listenOnly')}</p>
  {/if}
  {#each groups as group (group.id)}
    {#if group.id === 'pcb'}
      {#if $prefsStore?.pcb_enabled && group.items.length}
        <section class="card panel" data-testid="category-pcb">
          <div class="panel-head"><h2>{translate($language, group.labelKey)}</h2></div>
          <p class="hint" data-testid="h74-note">{translate($language, 'settings.h74')}</p>
          {@render rows(group.items)}
        </section>
      {/if}
    {:else if group.items.length}
      {@const opened = openCategory(group.id)}
      {#if opened}
        <details class="card panel" data-testid={`category-${group.id}`} data-collapsed="false" open>
          <summary class="panel-head">{translate($language, group.labelKey)} <span class="count">{group.items.length}</span></summary>
          {@render rows(group.items)}
        </details>
      {:else}
        <details class="card panel" data-testid={`category-${group.id}`} data-collapsed="true">
          <summary class="panel-head">{translate($language, group.labelKey)} <span class="count">{group.items.length}</span></summary>
          <div class="hint">
            {translate($language, 'settings.collapsedHint')}
            <button type="button" data-testid={`show-${group.id}`} onclick={() => showAnyway(group.id)}>
              {translate($language, 'settings.showAnyway')}
            </button>
          </div>
          {@render rows(group.items)}
        </details>
      {/if}
    {/if}
  {/each}
</section>

<style>
  .settings {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    max-width: 60rem;
  }
  h1 {
    margin: 0 0 0.25rem;
    font: 600 22px/1.1 var(--font-ui);
  }
  .card {
    overflow: hidden;
  }
  summary {
    cursor: pointer;
    list-style: none;
  }
  summary::-webkit-details-marker { display: none; }
  details[open] > summary {
    border-bottom: 1px solid var(--line);
  }
  .count {
    font-weight: 400;
    color: var(--ink-2);
    font-size: 0.8125rem;
  }
  .hint {
    padding: 0.5rem 0.75rem;
    font-size: 0.8125rem;
    color: var(--ink-2);
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    align-items: center;
    margin: 0;
  }
  .banner {
    margin: 0;
    padding: 0.5rem 0.75rem;
    border-radius: 6px;
    background: color-mix(in srgb, var(--pending) 14%, transparent);
    border: 1px solid var(--pending);
  }
</style>
