<script>
  import ApplyButton from '../ApplyButton.svelte';
  import CommandStatus from '../CommandStatus.svelte';
  import { api } from '../../lib/api.js';
  import { topicByKey as defaultTopicByKey } from '../../lib/catalog.js';
  import { resolveRange, validate } from '../../lib/encoding.js';
  import { presentTopic } from '../../lib/format.js';
  import { translate } from '../../lib/i18n/index.js';
  import { askConfirm } from '../../lib/stores.js';
  import { isCoupled, leafKey } from '../../lib/curvegeom.js';
  import {
    changedValue,
    commandGate,
    draftValue,
    entryId,
    formatDraft,
    isAction,
    isRisky,
    parseDraft,
    readbackKeyOf,
    recentWrites,
    selectValues,
    valueLabel,
  } from './grouping.js';

  let {
    entry,
    profile = null,
    live = null,
    prefs = null,
    lang = 'en',
    commandMap = {},
    /** 'row' (settings list) or 'compact' (quick controls) */
    variant = 'row',
    /** 'auto' or 'slider' (range input) */
    widget = 'auto',
    labelText = null,
    /** extra client-side reason to keep Apply disabled (shown as a note) */
    blockedNote = null,
    /** formats a numeric draft for the slider read-out */
    formatValue = null,
    inputTestid = null,
    applyTestid = null,
    /** catalog to resolve read-back topics (labels, units); defaults to the build-time catalog */
    catalogData = null,
  } = $props();

  const topicByKey = $derived.by(() => {
    if (!catalogData?.topics) return defaultTopicByKey;
    const index = new Map(catalogData.topics.map((topic) => [topic.key, topic]));
    return (key) => index.get(key) ?? null;
  });

  let touched = $state(false);
  let text = $state('');
  let pending = $state(false);
  let localCommand = $state(null);
  let errorCode = $state('');

  const id = $derived(entryId(entry));
  const action = $derived(isAction(entry));
  const baselineValue = $derived(draftValue(entry, live));
  const baseline = $derived(formatDraft(entry, baselineValue));
  const shown = $derived(touched ? text : baseline);
  const parsed = $derived(parseDraft(entry, shown));
  const toSend = $derived(changedValue(entry, baselineValue, parsed));
  const validation = $derived.by(() => {
    if (toSend != null) return validate(entry, toSend, profile);
    if (parsed != null) return { ok: true };
    return { ok: false, error: String(shown).trim() === '' ? 'empty' : 'bad_type' };
  });
  const gate = $derived(commandGate(entry, { profile, prefs, live, value: toSend ?? parsed }));
  const label = $derived(labelText ?? (entry.label?.[lang] || entry.label?.en || id));
  const values = $derived(selectValues(entry));
  const choose = $derived(widget !== 'slider' && values !== null && !action);
  const range = $derived(resolveRange(entry, profile));
  const disabled = $derived(
    toSend == null || !validation.ok || Boolean(gate) || Boolean(blockedNote) || pending,
  );

  // Request temperature in coupled mode (direct + room sensor): the active setpoint is the curve's
  // cold-end target and the request-temperature read-back stays 0, so point there instead.
  const coupled = $derived.by(() => {
    const m = /^SetZ([12])(Heat|Cool)RequestTemperature$/.exec(id ?? '');
    if (!m) return null;
    const zone = `z${m[1]}`;
    const mode = m[2].toLowerCase();
    if (!isCoupled(profile, zone, mode)) return null;
    const key = leafKey(zone, mode, 'cold', 'target');
    const topic = live?.topics?.[`main/${key}`];
    const value = topic && !topic.sentinel && typeof topic.value === 'number' ? topic.value : null;
    return { key, value };
  });

  const readbackKey = $derived(readbackKeyOf(entry, live));
  const readbackTopic = $derived(readbackKey ? topicByKey(readbackKey) : null);
  const unit = $derived(readbackTopic?.unit ?? null);
  const helpers = $derived({ topicByKey, translate });
  const options = $derived((values ?? []).map((value) => ({
    value: String(value),
    label: valueLabel(entry, value, lang, helpers),
  })));
  const current = $derived.by(() => {
    if (!readbackKey || entry.type === 'json') return null;
    const topic = live?.topics?.[readbackKey];
    if (!topic) return null;
    const presented = presentTopic(topic, { deviceOnline: live?.device_online, lang });
    if (values && typeof topic.value === 'number' && !topic.sentinel && !topic.enum_label) {
      const match = values.find((value) => value === draftValue(entry, live));
      if (match != null) return { ...presented, text: valueLabel(entry, match, lang, helpers) };
    }
    return presented;
  });
  const sliderText = $derived.by(() => {
    if (parsed == null) return translate(lang, 'settings.noValue');
    if (formatValue) return formatValue(parsed);
    return unit ? `${parsed} ${unit}` : String(parsed);
  });

  // When the read-back catches up with the submitted draft, follow the live value again.
  $effect(() => {
    if (touched && !pending && localCommand && toSend == null) touched = false;
  });

  const statusRow = $derived.by(() => {
    const rows = Object.values(commandMap ?? {}).filter((row) => row?.name === id);
    let best = null;
    for (const row of rows) {
      if (!best || (row.submitted_ts ?? 0) >= (best.submitted_ts ?? 0)) best = row;
    }
    if (!localCommand) return best;
    const same = rows.find((row) => row?.id != null && row.id === localCommand.id);
    if (same) {
      if (best && best !== same && (best.submitted_ts ?? 0) > (same.submitted_ts ?? 0)) return best;
      return same;
    }
    if (best && (best.submitted_ts ?? 0) > (localCommand.submitted_ts ?? 0)) return best;
    return localCommand;
  });

  function edit(value) {
    touched = true;
    text = value;
    errorCode = '';
  }

  function resetDraft() {
    touched = false;
    errorCode = '';
  }

  async function submit() {
    const value = changedValue(entry, baselineValue, parseDraft(entry, shown));
    if (value == null) return;
    const check = validate(entry, value, profile);
    const blocked = commandGate(entry, { profile, prefs, live, value });
    if (!check.ok || blocked || blockedNote) return;
    if (recentWrites(commandMap, id, Date.now()) >= 3) {
      const proceed = await askConfirm({
        title: translate(lang, 'settings.eepromTitle'),
        body: translate(lang, 'settings.eepromBody'),
      });
      if (!proceed) return;
    }
    const risky = isRisky(entry, value);
    if (risky) {
      const proceed = await askConfirm({
        title: translate(lang, 'settings.riskyTitle'),
        body: `${label}: ${entry.type === 'json' ? JSON.stringify(value) : valueLabel(entry, value, lang, helpers)}`,
      });
      if (!proceed) return;
    }
    pending = true;
    errorCode = '';
    try {
      const result = await api.command({ name: id, value, confirm: risky });
      localCommand = result ?? { name: id, status: 'pending', submitted_ts: Date.now() };
    } catch (err) {
      errorCode = err?.code || err?.message || 'failed';
    } finally {
      pending = false;
    }
  }
</script>

<article
  class="command"
  class:compact={variant === 'compact'}
  class:wide={entry.type === 'json'}
  data-testid={`control-${id}`}
  data-gate={gate ?? undefined}
  data-name={id}
  data-dirty={toSend != null ? 'true' : 'false'}
>
  <div class="head">
    <label class="name" for={`cmd-${variant}-${id}`}>{label}</label>
    {#if entry.type !== 'json' && !action}
      <span class="current">
        {translate(lang, 'settings.current')}:
        {#if coupled}
          <span data-testid={`coupled-current-${id}`}>{translate(lang, 'settings.coupledCurrent', { value: coupled.value ?? translate(lang, 'settings.noValue') })}</span>
        {:else if current}
          <span class={current.className}>{current.text}</span>
        {:else}
          {translate(lang, 'settings.noValue')}
        {/if}
      </span>
    {/if}
  </div>

  <div class="edit">
    {#if action}
      <!-- single-value action: the button is the control -->
    {:else if choose}
      <select
        id={`cmd-${variant}-${id}`}
        data-testid={inputTestid ?? `value-${id}`}
        data-type={entry.type}
        data-valid={validation.ok ? 'true' : 'false'}
        value={shown}
        onchange={(event) => edit(event.currentTarget.value)}
      >
        {#if shown === '' || !options.some((option) => option.value === shown)}
          <option value={shown} disabled selected>{shown === '' ? translate(lang, 'settings.choose') : valueLabel(entry, Number(shown), lang, helpers)}</option>
        {/if}
        {#each options as option (option.value)}
          <option value={option.value} selected={option.value === shown}>{option.label}</option>
        {/each}
      </select>
    {:else if entry.type === 'json'}
      <textarea
        id={`cmd-${variant}-${id}`}
        rows="3"
        data-testid={inputTestid ?? `value-${id}`}
        data-type="json"
        data-valid={validation.ok ? 'true' : 'false'}
        value={shown}
        oninput={(event) => edit(event.currentTarget.value)}
      ></textarea>
    {:else if widget === 'slider'}
      <input
        id={`cmd-${variant}-${id}`}
        type="range"
        min={range?.min}
        max={range?.max}
        step={range?.step ?? 1}
        value={shown === '' ? (range?.min ?? 0) : shown}
        data-testid={inputTestid ?? `value-${id}`}
        data-valid={validation.ok ? 'true' : 'false'}
        oninput={(event) => edit(event.currentTarget.value)}
      />
      <output class="readout" for={`cmd-${variant}-${id}`}>{sliderText}</output>
    {:else}
      <span class="number">
        <input
          id={`cmd-${variant}-${id}`}
          type="number"
          min={range?.min}
          max={range?.max}
          step={range?.step ?? 'any'}
          placeholder={range ? `${range.min ?? ''}…${range.max ?? ''}` : ''}
          data-testid={inputTestid ?? `value-${id}`}
          data-type={entry.type}
          data-valid={validation.ok ? 'true' : 'false'}
          value={shown}
          inputmode="decimal"
          oninput={(event) => edit(event.currentTarget.value)}
        />
        {#if unit}<span class="unit">{unit}</span>{/if}
      </span>
    {/if}
    <ApplyButton
      label={translate(lang, action ? 'settings.run' : 'settings.apply')}
      {disabled}
      {pending}
      testid={applyTestid ?? `apply-${id}`}
      onclick={submit}
    />
    {#if touched && toSend != null}
      <button type="button" class="link" data-testid={`reset-${id}`} onclick={resetDraft}>{translate(lang, 'settings.undo')}</button>
    {/if}
    {#if statusRow?.status}
      <CommandStatus status={statusRow.status} detail={statusRow.detail} />
    {/if}
  </div>

  <div class="notes">
    {#if coupled}
      <p class="note" data-testid={`coupled-note-${id}`}>
        {translate(lang, 'settings.coupledNote', { key: coupled.key })}
        <a href="#/curve">{translate(lang, 'settings.coupledLink')}</a>
      </p>
    {/if}
    {#if entry.type === 'json'}
      <p class="note">{translate(lang, 'settings.jsonHint')}</p>
    {/if}
    {#if range && !choose && widget !== 'slider' && entry.type !== 'json' && !action}
      <p class="note">{translate(lang, 'settings.range', { min: range.min ?? '…', max: range.max ?? '…', unit: unit ?? '' })}</p>
    {/if}
    {#if entry.min_firmware && entry.min_firmware !== '3.2.3' && variant !== 'compact'}
      <p class="note">{translate(lang, 'settings.minFirmware', { version: entry.min_firmware })}</p>
    {/if}
    {#if entry.range_source === 'encoding_domain'}
      <p class="note">{translate(lang, 'settings.encodingNote')}</p>
    {/if}
    {#if entry.class === 'retained_exception' && String(entry.path || '').startsWith('s0/')}
      <p class="note">{translate(lang, 'settings.s0Note')}</p>
      {#if current}
        <p class="note">{translate(lang, 'settings.s0Reading', { value: current.text || live?.topics?.[entry.path]?.raw || '' })}</p>
      {/if}
    {:else if entry.class === 'retained_exception'}
      <p class="note">{translate(lang, 'settings.retainedNote')}</p>
    {:else if entry.class === 'input'}
      <p class="note">{translate(lang, 'settings.inputNote')}</p>
    {/if}
    {#if gate === 'firmware_too_old'}
      <p class="warn" data-testid={`gate-${id}`}>{translate(lang, 'settings.firmwareTooOld', { version: entry.min_firmware })}</p>
    {:else if gate}
      <p class="warn" data-testid={`gate-${id}`}>{translate(lang, 'settings.gateExplain', { code: gate })}</p>
    {:else if blockedNote}
      <p class="note" data-testid={`blocked-${id}`}>{blockedNote}</p>
    {:else if touched && !validation.ok && validation.error !== 'empty'}
      <p class="warn" data-testid={`validation-${id}`}>{translate(lang, 'settings.invalid', { code: validation.error })}</p>
    {/if}
    {#if statusRow?.status === 'sent'}
      <p class="note">{translate(lang, 'settings.sentNote')}</p>
    {/if}
    {#if errorCode}
      <p class="warn" data-testid={`error-${id}`}>{errorCode}</p>
    {/if}
  </div>
</article>

<style>
  .command {
    display: grid;
    grid-template-columns: minmax(10rem, 1fr) auto;
    grid-template-areas:
      'head edit'
      'notes notes';
    align-items: center;
    gap: 0.25rem 1rem;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--border);
  }
  .command:last-child {
    border-bottom: none;
  }
  .command.wide {
    grid-template-columns: 1fr;
    grid-template-areas: 'head' 'edit' 'notes';
  }
  .head {
    grid-area: head;
    display: flex;
    flex-direction: column;
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
    justify-content: flex-end;
    gap: 0.5rem;
  }
  .wide .edit {
    justify-content: flex-start;
  }
  .notes {
    grid-area: notes;
    min-width: 0;
  }
  .notes:empty {
    display: none;
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
  select {
    min-width: 9rem;
    max-width: 16rem;
  }
  textarea {
    width: 100%;
    min-width: 0;
    font-family: ui-monospace, monospace;
    font-size: 0.8125rem;
  }
  .wide .edit textarea {
    flex: 1 1 100%;
  }
  .number {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
  }
  .number input {
    width: 6rem;
  }
  .unit {
    color: var(--text-secondary);
    font-size: 0.875rem;
  }
  input[type='range'] {
    width: 10rem;
  }
  .readout {
    min-width: 4.5rem;
    font-variant-numeric: tabular-nums;
  }
  .link {
    background: none;
    border: none;
    color: var(--primary);
    padding: 0;
    cursor: pointer;
    font-size: 0.8125rem;
  }
  .compact {
    padding: 0.5rem 0;
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas: 'head' 'edit' 'notes';
    row-gap: 0.375rem;
  }
  .compact .head {
    flex-direction: row;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: baseline;
    column-gap: 0.75rem;
  }
  .compact .edit {
    justify-content: flex-start;
  }
  .compact select {
    flex: 1 1 11rem;
    min-width: 0;
    max-width: none;
  }
  .compact input[type='range'] {
    flex: 1 1 auto;
    min-width: 0;
    width: auto;
  }
  @media (max-width: 640px) {
    .command {
      grid-template-columns: 1fr;
      grid-template-areas: 'head' 'edit' 'notes';
    }
    .edit {
      justify-content: flex-start;
    }
    input[type='range'] {
      flex: 1 1 8rem;
    }
  }
</style>
