<script>
  import { translate } from '../../lib/i18n/index.js';
  import { presentTopic } from '../../lib/format.js';
  import { tileIds } from '../../lib/domain/rules.js';
  import { topicByKey } from '../../lib/catalog.js';
  import Sparkline from './Sparkline.svelte';
  import TempDot from '../../lib/ui/TempDot.svelte';

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
    {#if shown?.unit === '°C' && topic && !topic.sentinel}<TempDot value={topic.value} />{/if}{presented.text}
  </div>
  {#if sparkline}
    <Sparkline data={sparkline} />
  {/if}
</div>

<style>
  .tile {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--r);
    padding: 12px 14px;
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
  }
  .label {
    min-width: 0;
    line-height: 1.25;
    overflow-wrap: break-word;
    hyphens: auto;
    font: 500 10.5px/1.25 var(--font-data);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--ink-3);
  }
  .pin {
    background: none;
    border: none;
    color: var(--ink-3);
    cursor: pointer;
    font-size: 0.875rem;
    padding: 0 0.125rem;
    line-height: 1;
    flex: none;
  }
  .pin:hover {
    color: var(--warm-ink);
  }
  .value {
    font: 500 22px/1.2 var(--font-data);
    font-stretch: 87.5%;
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
    color: var(--ink-3);
  }
  @media (max-width: 480px) {
    .tile {
      padding: 10px 12px;
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
    color: var(--ink-3);
  }
</style>
