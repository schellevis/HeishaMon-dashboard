<script>
  import { translate } from '../../lib/i18n/index.js';
  import { presentTopic } from '../../lib/format.js';
  import { tileIds } from '../../lib/domain/rules.js';
  import { topicByKey } from '../../lib/catalog.js';
  import Sparkline from './Sparkline.svelte';

  let {
    key = '',
    topic = null,
    sparkline = null,
    lang = 'en',
    deviceOnline = 'unknown',
    onPin = () => {},
    onUnpin = () => {},
    isPinned = false,
  } = $props();

  // A built-in tile id is labelled from the UI strings; any other key is a catalogued topic.
  const catalogued = $derived(tileIds.includes(key) ? null : topicByKey(key));
  const label = $derived(catalogued ? (catalogued.label?.[lang] || catalogued.label?.en || key) : (translate(lang, `overview.${key}`) ?? key));
  const shown = $derived(catalogued && topic && !topic.unit && catalogued.unit ? { ...topic, unit: catalogued.unit } : topic);
  const presented = $derived(presentTopic(shown, { deviceOnline, lang }));

  function togglePin(event) {
    event.stopPropagation();
    if (isPinned) onUnpin(key);
    else onPin(key);
  }
</script>

<div class="tile" data-testid="tile-{key}" data-pinned={isPinned} lang={lang}>
  <header>
    <span class="label">{label}</span>
    <button type="button" class="pin" aria-label={isPinned ? translate(lang, 'overview.unpinTile') : translate(lang, 'overview.pinTile')} onclick={togglePin}>
      {#if isPinned}
        ★
      {:else}
       ☆
      {/if}
    </button>
  </header>
  <div class="value" class:text={topic?.kind !== 'number'} class:value-stale={presented.className}>
    {presented.text}
  </div>
  {#if sparkline}
    <Sparkline data={sparkline} />
  {/if}
</div>

<style>
  .tile {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--card-radius);
    padding: 0.625rem 0.75rem;
    font-size: 0.875rem;
    position: relative;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 0.25rem;
    margin-bottom: 0.25rem;
    color: var(--text-secondary);
    font-size: 0.8125rem;
  }
  .label {
    min-width: 0;
    line-height: 1.25;
    overflow-wrap: break-word;
    hyphens: auto;
  }
  .pin {
    background: none;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    font-size: 0.875rem;
    padding: 0 0.125rem;
    line-height: 1;
    flex: none;
  }
  .pin:hover {
    color: #b45309;
  }
  .value {
    font-size: 1.5rem;
    font-weight: 600;
    line-height: 1.2;
    margin-bottom: 0.25rem;
    min-width: 0;
    overflow-wrap: break-word;
    hyphens: auto;
    font-variant-numeric: tabular-nums;
  }
  .value.text {
    font-size: 0.9375rem;
  }
  .value-stale {
    color: #6b7280;
  }
  @media (max-width: 480px) {
    .tile {
      padding: 0.5rem 0.625rem;
    }
    header {
      font-size: 0.75rem;
    }
    .value {
      font-size: 1.25rem;
    }
    .value.text {
      font-size: 0.875rem;
    }
  }
  .tile :global(svg) {
    margin-top: auto;
    color: var(--primary);
  }
</style>
