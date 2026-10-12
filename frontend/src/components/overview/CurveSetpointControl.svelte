<script>
  // Zone setpoint in "coupled" mode: direct control with a room sensor (thermostat/thermistor).
  // The firmware stores the active setpoint in the curve's cold-end target (Target_High), and the
  // request-temperature topic stays 0. So read that leaf and write it with a partial SetCurves,
  // the same path the curve screen uses; the read-back is that one leaf.
  import ApplyButton from '../ApplyButton.svelte';
  import CommandStatus from '../CommandStatus.svelte';
  import { api } from '../../lib/api.js';
  import { LIMITS, leafKey, zoneNum } from '../../lib/curvegeom.js';
  import { translate } from '../../lib/i18n/index.js';
  import { askConfirm } from '../../lib/stores.js';
  import { commandGate, recentWrites } from '../settings/grouping.js';

  let {
    zone = 'z1',
    mode = 'heat',
    /** catalog entry of SetCurves (gates: write lock, offline, firmware) */
    entry,
    profile = null,
    live = null,
    prefs = null,
    lang = 'en',
    commandMap = {},
    labelText = '',
    inputTestid = null,
    applyTestid = null,
    noteTestid = null,
  } = $props();

  const n = $derived(zoneNum(zone));
  const leaf = $derived(`main/${leafKey(zone, mode, 'cold', 'target')}`);
  const lim = $derived(LIMITS[mode].target);
  const liveValue = $derived.by(() => {
    const topic = live?.topics?.[leaf];
    return topic && !topic.sentinel && typeof topic.value === 'number' && Number.isFinite(topic.value) ? topic.value : null;
  });

  let draft = $state(null);
  let pending = $state(false);
  let localCommand = $state(null);
  let errorCode = $state('');

  const shown = $derived(draft ?? liveValue);
  const toSend = $derived(draft !== null && draft !== liveValue ? draft : null);
  const gate = $derived(entry ? commandGate(entry, { profile, prefs, live }) : 'unknown_command');
  const valid = $derived(toSend === null || (Number.isInteger(toSend) && toSend >= lim[0] && toSend <= lim[1]));
  const disabled = $derived(toSend === null || !valid || Boolean(gate) || pending);

  // follow the live value again once the read-back has caught up with the draft
  $effect(() => {
    if (draft !== null && !pending && localCommand && draft === liveValue) draft = null;
  });

  const keyOf = (row) => row?.keys?.[leaf] ?? row?.keys?.[leaf.replace('main/', '')] ?? null;

  /** Status of the latest SetCurves that wrote this leaf (per-key status when available). */
  const status = $derived.by(() => {
    let best = null;
    for (const row of Object.values(commandMap ?? {})) {
      if (row?.name !== 'SetCurves' || !keyOf(row)) continue;
      if (!best || (row.submitted_ts ?? 0) >= (best.submitted_ts ?? 0)) best = row;
    }
    const mine = localCommand && (commandMap?.[localCommand.id] ?? localCommand);
    const row = mine && (!best || (mine.submitted_ts ?? 0) >= (best.submitted_ts ?? 0)) ? mine : best;
    if (!row) return null;
    const key = keyOf(row);
    return { status: key?.status ?? row.status, detail: key ? null : row.detail };
  });

  function edit(value) {
    const v = Number(value);
    draft = Number.isFinite(v) ? Math.round(v) : null;
    errorCode = '';
  }

  async function submit() {
    if (disabled) return;
    const value = toSend;
    if (recentWrites(commandMap, 'SetCurves', Date.now()) >= 3) {
      const proceed = await askConfirm({
        title: translate(lang, 'settings.eepromTitle'),
        body: translate(lang, 'settings.eepromBody'),
      });
      if (!proceed) return;
    }
    pending = true;
    errorCode = '';
    try {
      const json = { [`zone${n}`]: { [mode]: { target: { high: value } } } };
      const result = await api.command({ name: 'SetCurves', value: json, confirm: false });
      localCommand = result ?? { id: null, name: 'SetCurves', status: 'pending', submitted_ts: Date.now() };
    } catch (err) {
      errorCode = err?.code || err?.message || 'failed';
    } finally {
      pending = false;
    }
  }
</script>

<article class="command compact" data-testid={`control-coupled-${zone}-${mode}`} data-gate={gate ?? undefined} data-leaf={leaf}>
  <div class="head">
    <label class="name" for={`coupled-${zone}-${mode}`}>{labelText}</label>
    <span class="current">
      {translate(lang, 'settings.current')}:
      {liveValue !== null ? `${liveValue} °C` : translate(lang, 'settings.noValue')}
    </span>
  </div>
  <div class="edit">
    <input
      id={`coupled-${zone}-${mode}`}
      type="range"
      min={lim[0]}
      max={lim[1]}
      step="1"
      value={shown ?? lim[0]}
      data-testid={inputTestid}
      data-valid={valid ? 'true' : 'false'}
      oninput={(event) => edit(event.currentTarget.value)}
    />
    <output class="readout" for={`coupled-${zone}-${mode}`}>{shown !== null ? `${shown} °C` : translate(lang, 'settings.noValue')}</output>
    <ApplyButton label={translate(lang, 'settings.apply')} {disabled} {pending} testid={applyTestid} onclick={submit} />
    {#if toSend !== null}
      <button type="button" class="link" onclick={() => (draft = null)}>{translate(lang, 'settings.undo')}</button>
    {/if}
    {#if status?.status}
      <CommandStatus status={status.status} detail={status.detail} />
    {/if}
  </div>
  <div class="notes">
    <p class="note" data-testid={noteTestid}>
      {translate(lang, 'overview.coupledNote', { key: leaf.replace('main/', '') })}
      <a href="#/curve">{translate(lang, 'overview.coupledLink')}</a>
    </p>
    {#if gate}
      <p class="warn">{translate(lang, 'settings.gateExplain', { code: gate })}</p>
    {/if}
    {#if errorCode}
      <p class="warn">{errorCode}</p>
    {/if}
  </div>
</article>

<style>
  .command {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas: 'head' 'edit' 'notes';
    row-gap: 0.375rem;
    padding: 0.5rem 0;
  }
  .head {
    grid-area: head;
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: baseline;
    column-gap: 0.75rem;
    min-width: 0;
  }
  .name {
    font-weight: 600;
  }
  .current {
    color: var(--text-secondary);
    font-size: 0.8125rem;
  }
  .edit {
    grid-area: edit;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem;
  }
  input[type='range'] {
    flex: 1 1 auto;
    min-width: 0;
  }
  .readout {
    min-width: 4.5rem;
    font-variant-numeric: tabular-nums;
  }
  .notes {
    grid-area: notes;
    min-width: 0;
  }
  .note,
  .warn {
    margin: 0;
    font-size: 0.75rem;
    color: var(--text-secondary);
  }
  .warn {
    color: var(--danger);
  }
  .link {
    background: none;
    border: none;
    color: var(--primary);
    padding: 0;
    cursor: pointer;
    font-size: 0.8125rem;
  }
</style>
