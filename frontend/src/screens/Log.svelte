<script>
  import { onMount } from 'svelte';
  import CommandStatus from '../components/CommandStatus.svelte';
  import { api } from '../lib/api.js';
  import { translate } from '../lib/i18n/index.js';
  import { language } from '../lib/stores.js';
  import { commandByName } from '../lib/catalog.js';
  import { formatDateTime } from '../lib/time.js';

  function kindLabel(kind, lang) {
    const key = `log.kind_${kind}`;
    const text = translate(lang, key);
    return text === key ? kind : text;
  }

  function commandLabel(name, lang) {
    const entry = commandByName(name);
    return entry?.label?.[lang] || entry?.label?.en || name;
  }

  function detailText(detail) {
    if (detail == null) return '';
    if (typeof detail !== 'object') return String(detail);
    return Object.entries(detail)
      .filter(([, value]) => value !== null && value !== undefined)
      .map(([key, value]) => `${key}: ${typeof value === 'object' ? JSON.stringify(value) : value}`)
      .join(', ');
  }

  let commandRows = $state([]);
  let eventRows = $state([]);
  let source = $state('all');
  let query = $state('');

  onMount(() => {
    let alive = true;
    api.commands({ limit: 200 }).then((body) => {
      if (alive) commandRows = body?.commands ?? [];
    }).catch(() => {});
    api.events({ limit: 200 }).then((body) => {
      if (alive) eventRows = body?.events ?? [];
    }).catch(() => {});
    return () => {
      alive = false;
    };
  });

  const needle = $derived(query.trim().toLowerCase());

  function matches(text) {
    if (!needle) return true;
    return String(text ?? '').toLowerCase().includes(needle);
  }

  const shownCommands = $derived(source === 'events' ? [] : commandRows.filter((row) => (
    matches(row.name) || matches(commandLabel(row.name, $language)) || matches(row.status) || matches(row.payload) || matches(row.detail)
  )));

  const shownEvents = $derived(source === 'commands' ? [] : eventRows.filter((row) => (
    matches(row.kind) || matches(kindLabel(row.kind, $language)) || matches(JSON.stringify(row.detail ?? ''))
  )));
</script>

<section data-testid="screen-log" class="log">
  <h1>{translate($language, 'log.title')}</h1>
  <div class="filters">
  <label>
    {translate($language, 'log.filter')}
    <select data-testid="log-filter" bind:value={source}>
      <option value="all">{translate($language, 'log.all')}</option>
      <option value="commands">{translate($language, 'log.commands')}</option>
      <option value="events">{translate($language, 'log.events')}</option>
    </select>
  </label>
  <label>
    {translate($language, 'log.query')}
    <input data-testid="log-query" bind:value={query} />
  </label>
  </div>
  {#if source !== 'events'}
    <section class="card" data-testid="log-commands">
      <h2>{translate($language, 'log.commands')}</h2>
      {#if shownCommands.length === 0}
        <p>{translate($language, 'log.empty')}</p>
      {:else}
        <ul>
          {#each shownCommands as row, index (`${row.id ?? row.name}-${index}`)}
            <li data-testid="log-command-row">
              <time datetime={row.submitted_ts ? new Date(row.submitted_ts).toISOString() : undefined}>{formatDateTime(row.submitted_ts, $language)}</time>
              <span class="what"><span title={row.name}>{commandLabel(row.name, $language)}</span> <code class="key">{row.name}</code></span>
              <code>{row.prev_value != null ? `${row.prev_value} → ` : ''}{row.payload ?? ''}</code>
              <CommandStatus status={row.status} detail={null} />
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  {/if}
  {#if source !== 'commands'}
    <section class="card" data-testid="log-events">
      <h2>{translate($language, 'log.events')}</h2>
      {#if shownEvents.length === 0}
        <p>{translate($language, 'log.empty')}</p>
      {:else}
        <ul>
          {#each shownEvents as row, index (`${row.kind}-${row.ts}-${index}`)}
            <li data-testid="log-event-row" data-kind={row.kind}>
              <time datetime={row.ts ? new Date(row.ts).toISOString() : undefined}>{formatDateTime(row.ts, $language)}</time>
              <span class="what" title={row.kind}>{kindLabel(row.kind, $language)}</span>
              <code>{detailText(row.detail)}</code>
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  {/if}
</section>

<style>
  .log {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  h1 {
    margin: 0;
    font-size: 1.375rem;
  }
  .filters {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
  }
  .filters label {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    font-size: 0.875rem;
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
  .card > p {
    margin: 0;
    padding: 0.5rem 0.75rem;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  li {
    display: grid;
    grid-template-columns: 10.5rem minmax(10rem, 1fr) minmax(0, 2fr) auto;
    gap: 0.75rem;
    align-items: baseline;
    padding: 0.3rem 0.75rem;
    border-bottom: 1px solid var(--border);
    font-size: 0.875rem;
  }
  li:last-child {
    border-bottom: none;
  }
  time {
    font-variant-numeric: tabular-nums;
    color: var(--text-secondary);
    white-space: nowrap;
  }
  code {
    font-size: 0.8125rem;
    color: var(--text-secondary);
    overflow-wrap: anywhere;
  }
  .key {
    font-size: 0.75rem;
  }
  @media (max-width: 640px) {
    li {
      grid-template-columns: 1fr auto;
    }
    li code:not(.key) {
      grid-column: 1 / -1;
    }
  }
</style>
