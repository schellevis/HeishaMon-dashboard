<script>
  import { onMount } from 'svelte';
  import { api } from '../../lib/api.js';
  import { formatAge } from '../../lib/format.js';
  import { translate } from '../../lib/i18n/index.js';
  import { language, prefs as prefsStore, system as systemStore, updatePrefs } from '../../lib/stores.js';

  let flushId = $state('');
  let flushError = $state('');
  let flushing = $state(false);
  let now = $state(Date.now());

  onMount(() => {
    let alive = true;
    api.system().then((body) => {
      if (alive && body) systemStore.set(body);
    }).catch(() => {});
    return () => {
      alive = false;
    };
  });

  const statsEntries = $derived(Object.entries($systemStore?.stats ?? {}).filter(([, value]) => value != null && typeof value !== 'object'));
  const flushAge = $derived($systemStore?.last_flush_ts == null
    ? translate($language, 'system.never')
    : formatAge(Math.max(0, now - $systemStore.last_flush_ts), $language));

  async function flushNow() {
    flushing = true;
    flushError = '';
    try {
      const result = await api.flush();
      flushId = result?.flush_id ?? '';
    } catch (err) {
      flushError = err?.code || err?.message || '';
    } finally {
      flushing = false;
    }
  }

  async function togglePcb(event) {
    await updatePrefs({ pcb_enabled: event.currentTarget.checked });
  }
</script>

<section data-testid="screen-system" class="system">
  <h1>{translate($language, 'system.title')}</h1>
  <div class="panel panel-body status">
  <p data-testid="system-broker">
    {translate($language, 'system.broker')}:
    {$systemStore?.broker_connected ? translate($language, 'system.connected') : translate($language, 'system.disconnected')}
  </p>
  <p data-testid="system-device">
    {translate($language, 'system.device')}: {$systemStore?.device_online ?? translate($language, 'system.unknown')}
  </p>
  <p data-testid="system-firmware">
    {translate($language, 'system.firmware')}: {$systemStore?.firmware ?? translate($language, 'system.unknown')}
    {#if $systemStore?.firmware_assumed}
      <span>{translate($language, 'system.firmwareAssumed')}</span>
    {/if}
  </p>
  {#if $systemStore?.listen_only_suspected}
    <p data-testid="listen-only" role="status">{translate($language, 'system.listenOnly')}</p>
  {/if}
  </div>
  <section data-testid="system-stats" class="panel">
    <div class="panel-head"><h2>{translate($language, 'system.stats')}</h2></div>
    <div class="panel-body">
    {#if statsEntries.length === 0}
      <p>{translate($language, 'system.unknown')}</p>
    {:else}
      <dl>
        {#each statsEntries as [key, value] (key)}
          <div>
            <dt>{key}</dt>
            <dd>{value}</dd>
          </div>
        {/each}
      </dl>
    {/if}
    </div>
  </section>
  <div class="panel panel-body status">
  <p data-testid="system-db">{translate($language, 'system.dbSize')}: {$systemStore?.db_bytes ?? 0}</p>
  <p data-testid="system-flush-age">{translate($language, 'system.lastFlush')}: {flushAge}</p>
  <p data-testid="system-flush-state">
    {#if $systemStore && $systemStore.last_flush_ok === false}
      {translate($language, 'system.flushFailed')}
      {#if $systemStore.last_flush_error}: {$systemStore.last_flush_error}{/if}
    {:else}
      {translate($language, 'system.flushOk')}
    {/if}
  </p>
  <p data-testid="system-interval">
    {translate($language, 'system.flushInterval')}: {$systemStore?.flush_interval_s ?? ''}
  </p>
  <p data-testid="system-buffer">
    {translate($language, 'system.buffer')}: {$systemStore?.buffer?.samples ?? 0}
  </p>
  <p data-testid="system-dropped">
    {translate($language, 'system.dropped')}: {$systemStore?.dropped?.samples ?? 0} / {$systemStore?.dropped?.ingest ?? 0}
  </p>
  <button type="button" data-testid="flush-now" disabled={flushing} onclick={flushNow}>
    {translate($language, 'system.flushNow')}
  </button>
  {#if flushId}<p data-testid="flush-id">{translate($language, 'system.flushStarted', { id: flushId })}</p>{/if}
  {#if flushError}<p data-testid="flush-error">{flushError}</p>{/if}
  <label>
    {translate($language, 'system.pcbToggle')}
    <input data-testid="pcb-enabled" type="checkbox" checked={$prefsStore?.pcb_enabled === true} onchange={togglePcb} />
  </label>
  <p>{translate($language, 'system.pcbHelp')}</p>
  </div>
</section>

<style>
  .system { display: flex; flex-direction: column; gap: 0.75rem; max-width: 60rem; }
  h1 { margin: 0; font: 600 22px/1.1 var(--font-ui); }
  .status p { margin: 0 0 0.35rem; }
  .status p[data-testid='listen-only'] { color: var(--pending-ink); }
  dl { margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(14rem, 1fr)); gap: 0.5rem 1.5rem; }
  dt { color: var(--ink-3); font: 11px var(--font-data); }
  dd { margin: 0; font-family: var(--font-data); overflow-wrap: anywhere; }
</style>
