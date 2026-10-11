<script>
  import { formatAge, presentTopic } from '../../lib/format.js';
  import { translate } from '../../lib/i18n/index.js';
  import Sparkline from './Sparkline.svelte';

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
  const name = $derived(catalogTopic?.label?.[lang] || catalogTopic?.label?.en || topicKey);
  const age = $derived(topicValue?.last_change == null ? '' : formatAge(Math.max(0, now - topicValue.last_change), lang));
</script>

<article
  data-testid={`topic-${topicKey}`}
  data-catalogued={catalogued ? 'true' : 'false'}
  data-raw={catalogued ? 'false' : 'true'}
  data-visibility={visibility}
>
  <h3>{name}</h3>
  {#if !catalogued}<p data-testid={`raw-badge-${topicKey}`}>{translate(lang, 'topics.raw')}</p>{/if}
  <p>
    {translate(lang, 'topics.value')}:
    <span class={presented.className}>{presented.text}</span>
    {#if catalogTopic?.unit}<span data-testid={`unit-${topicKey}`}> {catalogTopic.unit}</span>{/if}
  </p>
  <p>{translate(lang, 'topics.rawValue')}: <code data-testid={`raw-${topicKey}`}>{topicValue?.raw ?? ''}</code></p>
  <p data-last-change={topicValue?.last_change ?? ''}>{translate(lang, 'topics.lastChange')}: {age}</p>
  <Sparkline {points} />
  <label>
    {translate(lang, 'topics.visibility')}
    <select data-testid={`visibility-${topicKey}`} value={visibility} onchange={(event) => onvisibility(topicKey, event.currentTarget.value)}>
      <option value="visible">{translate(lang, 'topics.visible')}</option>
      <option value="hidden">{translate(lang, 'topics.hidden')}</option>
      <option value="ignored">{translate(lang, 'topics.ignored')}</option>
    </select>
  </label>
</article>
