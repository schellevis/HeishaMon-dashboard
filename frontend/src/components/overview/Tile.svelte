<script>
  import { translate } from '../../lib/i18n/index.js';
  import { presentTopic } from '../../lib/format.js';
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

  const label = $derived(translate(lang, `overview.${key}`) ?? key);
  const presented = $derived(presentTopic(topic, { deviceOnline, lang }));

  function togglePin(event) {
    event.stopPropagation();
    if (isPinned) onUnpin(key);
    else onPin(key);
  }
</script>

<div class="tile" data-testid="tile-{key}" data-pinned={isPinned}>
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
  <div class="value" class:value-stale={presented.className}>
    {presented.text}
  </div>
  {#if sparkline}
    <Sparkline data={sparkline} />
  {/if}
</div>

<style>
  .tile {
    background: #1a1a1a;
    border-radius: 8px;
    padding: 0.75rem;
    color: #e5e5e5;
    font-size: 0.875rem;
    position: relative;
    min-width: 140px;
    flex: 0 0 140px;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
    color: #888;
    font-size: 0.75rem;
  }
  .label {
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .pin {
    background: none;
    border: none;
    color: #888;
    cursor: pointer;
    font-size: 0.875rem;
    padding: 0.125rem;
    line-height: 1;
  }
  .pin:hover {
    color: #ffd700;
  }
  .value {
    font-size: 1.5rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
  }
  .value-stale {
    color: #6b7280;
  }
</style>
