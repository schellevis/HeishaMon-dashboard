<script>
  import { formatAge, presentTopic } from '../../lib/format.js';
  import { translate } from '../../lib/i18n/index.js';
  import Sparkline from './Sparkline.svelte';
  import TempDot from '../../lib/ui/TempDot.svelte';

  const SENTINEL_KEY = { '-1': 'topics.sentinelUnknown', '-128': 'topics.sentinelAbsent', '-78': 'topics.sentinelNotConnected', '-127': 'topics.sentinelUnused' };

  let {
    topicKey,
    topicValue,
    catalogTopic = null,
    visibility = 'visible',
    points = [],
    lang = 'en',
    deviceOnline = 'unknown',
    now = Date.now(),
    onvisibility = () => {},
  } = $props();

  const catalogued = $derived(Boolean(catalogTopic));
  const presented = $derived(presentTopic(topicValue, { deviceOnline, now, lang }));
  const unit = $derived(catalogTopic?.unit ?? null);
  const valueText = $derived(unit && presented.text.endsWith(` ${unit}`)
    ? presented.text.slice(0, -(unit.length + 1))
    : presented.text);
  const slash = $derived(topicKey.indexOf('/') + 1);
  const name = $derived(catalogTopic?.label?.[lang] || catalogTopic?.label?.en || topicKey);
  const age = $derived(topicValue?.last_change == null ? '' : formatAge(Math.max(0, now - topicValue.last_change), lang));
</script>

<article
  class="row"
  data-testid={`topic-${topicKey}`}
  data-catalogued={catalogued ? 'true' : 'false'}
  data-raw={catalogued ? 'false' : 'true'}
  data-visibility={visibility}
>
  <div class="name">
    <h3>{name}</h3>
    <code class="key">{#if slash}<span class="prefix">{topicKey.slice(0, slash)}</span>{/if}{topicKey.slice(slash)}</code>
    {#if !catalogued}<span class="badge" data-testid={`raw-badge-${topicKey}`}>{translate(lang, 'topics.raw')}</span>{/if}
  </div>
  <div class="value" title={translate(lang, 'topics.value')}>
    {#key topicValue?.last_change}
      <span class="val flash">
        {#if topicValue?.sentinel}
          <span class="sentinel-badge" data-testid={`sentinel-${topicKey}`}>{topicValue.raw}{#if SENTINEL_KEY[topicValue.raw]}{" · "}{translate(lang, SENTINEL_KEY[topicValue.raw])}{/if}</span>
        {:else}
          {#if unit === '°C'}<TempDot value={topicValue?.value ?? null} />{/if}<span class={presented.className}>{valueText}</span>
        {/if}
      </span>
    {/key}{#if unit && !topicValue?.sentinel}<span class="unit" data-testid={`unit-${topicKey}`}> {unit}</span>{/if}
  </div>
  <div class="raw" title={translate(lang, 'topics.rawValue')}><code data-testid={`raw-${topicKey}`}>{topicValue?.raw ?? ''}</code></div>
  <div class="age" data-last-change={topicValue?.last_change ?? ''} title={translate(lang, 'topics.lastChange')}>{age}</div>
  <div class="spark"><Sparkline {points} /></div>
  <select
    data-testid={`visibility-${topicKey}`}
    aria-label={`${translate(lang, 'topics.visibility')}: ${name}`}
    value={visibility}
    onchange={(event) => onvisibility(topicKey, event.currentTarget.value)}
  >
    <option value="visible">{translate(lang, 'topics.visible')}</option>
    <option value="hidden">{translate(lang, 'topics.hidden')}</option>
    <option value="ignored">{translate(lang, 'topics.ignored')}</option>
  </select>
</article>

<style>
  .row {
    display: grid;
    grid-template-columns: var(--topic-cols);
    gap: 0.75rem;
    align-items: center;
    padding: 0.3rem 0.75rem;
    border-bottom: 1px solid var(--line);
    font-size: 0.875rem;
  }
  .row:last-child {
    border-bottom: none;
  }
  .row[data-visibility='ignored'] {
    opacity: 0.55;
  }
  .name {
    min-width: 0;
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    column-gap: 0.5rem;
  }
  h3 {
    margin: 0;
    font-size: 0.875rem;
    font-weight: 600;
  }
  .key {
    font: 12px var(--font-data);
    color: var(--ink-2);
    overflow-wrap: anywhere;
  }
  .badge {
    font-size: 0.6875rem;
    padding: 0 0.375rem;
    border-radius: 999px;
    background: color-mix(in srgb, var(--pending) 14%, transparent);
  }
  .prefix { color: var(--ink-3); }
  .val.flash { animation: flash 1.2s; }
  @keyframes flash { from { background: color-mix(in srgb, var(--warm) 25%, transparent); } }
  .sentinel-badge { font: 10.5px var(--font-data); border: 1px solid var(--line-2); border-radius: 4px; padding: 1px 5px; color: var(--ink-2); }
  .value {
    font-family: var(--font-data);
    text-align: right;
    font-variant-numeric: tabular-nums;
    overflow-wrap: anywhere;
  }
  .unit {
    color: var(--ink-2);
    margin-left: 0.2em;
  }
  .raw code {
    font-size: 0.75rem;
    color: var(--ink-2);
    overflow-wrap: anywhere;
  }
  .age {
    font-size: 0.75rem;
    color: var(--ink-2);
  }
  .spark {
    color: var(--warm-ink);
    line-height: 0;
  }
  select {
    font-size: 0.8125rem;
    padding: 0.15rem 0.25rem;
  }
  @media (max-width: 900px) {
    .row {
      grid-template-columns: minmax(0, 1fr) auto;
      grid-template-areas:
        'name value'
        'meta select';
      row-gap: 0.125rem;
    }
    .name { grid-area: name; }
    .value { grid-area: value; text-align: right; }
    .raw, .spark { display: none; }
    .age { grid-area: meta; }
    select { grid-area: select; }
  }
</style>
