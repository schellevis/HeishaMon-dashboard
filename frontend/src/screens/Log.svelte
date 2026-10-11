<script>
  import { onMount } from 'svelte';
  import CommandStatus from '../components/CommandStatus.svelte';
  import { api } from '../lib/api.js';
  import { translate } from '../lib/i18n/index.js';
  import { language } from '../lib/stores.js';

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
    matches(row.name) || matches(row.status) || matches(row.payload) || matches(row.detail)
  )));

  const shownEvents = $derived(source === 'commands' ? [] : eventRows.filter((row) => (
    matches(row.kind) || matches(JSON.stringify(row.detail ?? ''))
  )));
</script>

<section data-testid="screen-log">
  <h1>{translate($language, 'log.title')}</h1>
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
  {#if source !== 'events'}
    <section data-testid="log-commands">
      <h2>{translate($language, 'log.commands')}</h2>
      {#if shownCommands.length === 0}
        <p>{translate($language, 'log.empty')}</p>
      {:else}
        <ul>
          {#each shownCommands as row, index (`${row.id ?? row.name}-${index}`)}
            <li data-testid="log-command-row">
              <span>{row.name}</span>
              <CommandStatus status={row.status} detail={row.detail} />
              <code>{row.payload ?? ''}</code>
              <time>{row.submitted_ts ?? ''}</time>
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  {/if}
  {#if source !== 'commands'}
    <section data-testid="log-events">
      <h2>{translate($language, 'log.events')}</h2>
      {#if shownEvents.length === 0}
        <p>{translate($language, 'log.empty')}</p>
      {:else}
        <ul>
          {#each shownEvents as row, index (`${row.kind}-${row.ts}-${index}`)}
            <li data-testid="log-event-row">
              <span>{row.kind}</span>
              <time>{row.ts ?? ''}</time>
              <code>{JSON.stringify(row.detail ?? null)}</code>
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  {/if}
</section>
