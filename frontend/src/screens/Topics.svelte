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
  let ticking = $state(Date.now());
  $effect(() => {
    if (now != null) return undefined;
    const timer = setInterval(() => { ticking = Date.now(); }, 10_000);
    return () => clearInterval(timer);
  });
  const clock = $derived(now ?? ticking);
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

  // Sparklines: one batched fetch per topic set, refreshed every 5 minutes. The key list is a
  // derived string, so live value messages (which replace the state object) do not refetch.
  const SPARKLINE_REFRESH_MS = 5 * 60 * 1000;
  const BATCH = 20; // server limit per /api/history request
  const keyList = $derived(Object.keys($stateStore?.topics ?? {}).sort().join('\n'));

  $effect(() => {
    const keys = keyList ? keyList.split('\n') : [];
    if (!keys.length) return undefined;
    let alive = true;
    const load = async () => {
      const to = now ?? Date.now();
      const from = to - 24 * 60 * 60 * 1000;
      const next = {};
      for (let index = 0; index < keys.length && alive; index += BATCH) {
        const slice = keys.slice(index, index + BATCH);
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
    };
    load();
    const timer = now == null ? setInterval(load, SPARKLINE_REFRESH_MS) : null;
    return () => {
      alive = false;
      if (timer) clearInterval(timer);
    };
  });

  async function setVisibility(key, value) {
    const next = fullPrefs($prefsStore);
    next.topic_visibility[key] = value;
    const saved = await api.putPrefs(next);
    prefsStore.set(saved ?? next);
  }
</script>

<section data-testid="screen-topics" class="topics">
  <h1>{translate($language, 'topics.title')}</h1>
  <section class="card suggestions" data-testid="ignore-suggestions">
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
    <section class="card" data-testid={`section-${section.prefix}`}>
      <h2>{translate($language, 'topics.section', { name: section.prefix })} <span class="count">{section.keys.length}</span></h2>
      <div class="head" aria-hidden="true">
        <span>{translate($language, 'topics.name')}</span>
        <span>{translate($language, 'topics.value')}</span>
        <span>{translate($language, 'topics.rawValue')}</span>
        <span>{translate($language, 'topics.lastChange')}</span>
        <span>24 h</span>
        <span>{translate($language, 'topics.visibility')}</span>
      </div>
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

<style>
  .topics {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  h1 {
    margin: 0;
    font-size: 1.375rem;
  }
  .card {
    border: 1px solid var(--border);
    border-radius: var(--card-radius);
    overflow: hidden;
  }
  h2 {
    margin: 0;
    padding: 0.5rem 0.75rem;
    font-size: 1rem;
    background: var(--bg-secondary);
  }
  .count {
    font-weight: 400;
    font-size: 0.8125rem;
    color: var(--text-secondary);
  }
  .suggestions p,
  .suggestions ul {
    margin: 0;
    padding: 0.5rem 0.75rem;
    font-size: 0.875rem;
  }
  .suggestions ul {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .suggestions li {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    align-items: center;
  }
  .suggestions li span[data-reason] {
    color: var(--text-secondary);
    font-size: 0.8125rem;
  }
  .head {
    display: grid;
    grid-template-columns: var(--topic-cols);
    gap: 0.75rem;
    padding: 0.25rem 0.75rem;
    font-size: 0.75rem;
    color: var(--text-secondary);
    border-bottom: 1px solid var(--border);
  }
  .topics {
    --topic-cols: minmax(12rem, 2.2fr) minmax(6rem, 1fr) minmax(4rem, 0.7fr) 5.5rem 100px 7.5rem;
  }
  @media (max-width: 900px) {
    .head {
      display: none;
    }
  }
</style>
