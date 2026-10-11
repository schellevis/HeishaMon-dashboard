<script>
  import CommandControl from '../components/settings/CommandControl.svelte';
  import { catalog as defaultCatalog } from '../lib/catalog.js';
  import { categoryRelevant, groupCatalog } from '../components/settings/grouping.js';
  import { fullPrefs } from '../components/settings/prefs.js';
  import { api } from '../lib/api.js';
  import { translate } from '../lib/i18n/index.js';
  import {
    commands as commandsStore,
    language,
    prefs as prefsStore,
    profile as profileStore,
    state as stateStore,
  } from '../lib/stores.js';

  let { catalogData = null } = $props();

  const source = $derived(catalogData ?? defaultCatalog);
  const groups = $derived(groupCatalog(source));

  function openCategory(id) {
    const relevant = categoryRelevant(id, $profileStore);
    return relevant || $prefsStore?.feature_overrides?.[id] === 'show';
  }

  async function showAnyway(id) {
    const next = fullPrefs($prefsStore);
    next.feature_overrides[id] = 'show';
    const saved = await api.putPrefs(next);
    prefsStore.set(saved ?? next);
  }
</script>

<section data-testid="screen-settings">
  <h1>{translate($language, 'settings.title')}</h1>
  {#if $stateStore?.listen_only_suspected}
    <p data-testid="listen-only" role="status">{translate($language, 'settings.listenOnly')}</p>
  {/if}
  {#each groups as group (group.id)}
    {#if group.id === 'pcb'}
      {#if $prefsStore?.pcb_enabled && group.items.length}
        <section data-testid="category-pcb">
          <h2>{translate($language, group.labelKey)}</h2>
          <p data-testid="h74-note">{translate($language, 'settings.h74')}</p>
          {#each group.items as entry (entry.name || entry.path)}
            <CommandControl
              {entry}
              profile={$profileStore}
              live={$stateStore}
              prefs={$prefsStore}
              lang={$language}
              commandMap={$commandsStore}
            />
          {/each}
        </section>
      {/if}
    {:else if group.items.length}
      {@const opened = openCategory(group.id)}
      {#if opened}
        <details data-testid={`category-${group.id}`} data-collapsed="false" open>
          <summary>{translate($language, group.labelKey)}</summary>
          {#each group.items as entry (entry.name || entry.path)}
            <CommandControl
              {entry}
              profile={$profileStore}
              live={$stateStore}
              prefs={$prefsStore}
              lang={$language}
              commandMap={$commandsStore}
            />
          {/each}
        </details>
      {:else}
        <details data-testid={`category-${group.id}`} data-collapsed="true">
          <summary>{translate($language, group.labelKey)}</summary>
          <p>{translate($language, 'settings.collapsedHint')}</p>
          <button type="button" data-testid={`show-${group.id}`} onclick={() => showAnyway(group.id)}>
            {translate($language, 'settings.showAnyway')}
          </button>
          {#each group.items as entry (entry.name || entry.path)}
            <CommandControl
              {entry}
              profile={$profileStore}
              live={$stateStore}
              prefs={$prefsStore}
              lang={$language}
              commandMap={$commandsStore}
            />
          {/each}
        </details>
      {/if}
    {/if}
  {/each}
</section>
