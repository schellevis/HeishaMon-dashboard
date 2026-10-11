<script>
  import { catalog as defaultCatalog } from '../lib/catalog.js';
  import { fullPrefs } from '../components/settings/prefs.js';
  import { sectionsWithTraffic, suggestIgnores } from '../components/topics/suggestions.js';
  import TopicRow from '../components/topics/TopicRow.svelte';
  import { api } from '../lib/api.js';
  import { translate } from '../lib/i18n/index.js';
  import {
    language,
    prefs as prefsStore,
    profile as profileStore,
    state as stateStore,
  } from '../lib/stores.js';

  let { catalogData = null, now = null } = $props();

  const source = $derived(catalogData ?? defaultCatalog);
  const clock = $derived(now ?? Date.now());
  const byKey = $derived(new Map((source.topics ?? []).map((topic) => [topic.key, topic])));
  const sections = $derived(sectionsWithTraffic($stateStore?.topics));
  const suggestions = $derived(suggestIgnores({
    catalog: source,
    topics: $stateStore?.topics,
    profile: $profileStore,
    now: clock,
  }));

  let points = $state({});

  const reasonKey = {
    sentinel: 'topics.reasonSentinel',
    extra_replaces: 'topics.reasonExtra',
    optional_pcb_off: 'topics.reasonOptional',
  };

  $effect(() => {
    const keys = Object.keys($stateStore?.topics ?? {});
    const from = clock - 24 * 60 * 60 * 1000;
    const to = clock;
    if (!keys.length || !(to > from)) return undefined;
    let alive = true;
    (async () => {
      const next = {};
      for (let index = 0; index < keys.length; index += 20) {
        const slice = keys.slice(index, index + 20);
        try {
          const history = await api.history({ topics: slice, from, to, max_points: 100 });
          for (const [key, series] of Object.entries(history?.series ?? {})) {
            next[key] = (series.points ?? [])
              .map((point) => (Array.isArray(point) ? point[1] : null))
              .filter((value) => typeof value === 'number');
          }
        } catch {
          /* sparkline stays empty when history is unavailable */
        }
      }
      if (alive) points = next;
    })();
    return () => {
      alive = false;
    };
  });

  async function setVisibility(key, value) {
    const next = fullPrefs($prefsStore);
    next.topic_visibility[key] = value;
    const saved = await api.putPrefs(next);
    prefsStore.set(saved ?? next);
  }
</script>

<section data-testid="screen-topics">
  <h1>{translate($language, 'topics.title')}</h1>
  <section data-testid="ignore-suggestions">
    <h2>{translate($language, 'topics.suggestions')}</h2>
    {#if suggestions.length === 0}
      <p>{translate($language, 'topics.suggestionsEmpty')}</p>
    {:else}
      <ul>
        {#each suggestions as suggestion (suggestion.key)}
          <li data-testid={`suggestion-${suggestion.key}`}>
            <span>{suggestion.key}</span>
            {#each suggestion.reasons as reason (reason)}
              <span data-reason={reason}>{translate($language, reasonKey[reason])}</span>
            {/each}
            <button type="button" data-testid={`suggest-${suggestion.key}`} onclick={() => setVisibility(suggestion.key, 'ignored')}>
              {translate($language, 'topics.ignore')}
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </section>
  {#each sections as section (section.prefix)}
    <section data-testid={`section-${section.prefix}`}>
      <h2>{translate($language, 'topics.section', { name: section.prefix })}</h2>
      {#each section.keys as key (key)}
        <TopicRow
          topicKey={key}
          topicValue={$stateStore.topics[key]}
          catalogTopic={byKey.get(key) ?? null}
          visibility={$prefsStore?.topic_visibility?.[key] ?? 'visible'}
          points={points[key] ?? []}
          lang={$language}
          deviceOnline={$stateStore?.device_online ?? 'unknown'}
          now={clock}
          onvisibility={setVisibility}
        />
      {/each}
    </section>
  {/each}
</section>
