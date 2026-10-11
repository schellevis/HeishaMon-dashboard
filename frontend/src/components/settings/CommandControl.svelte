<script>
  import ApplyButton from '../ApplyButton.svelte';
  import CommandStatus from '../CommandStatus.svelte';
  import { api } from '../../lib/api.js';
  import { validate } from '../../lib/encoding.js';
  import { presentTopic } from '../../lib/format.js';
  import { translate } from '../../lib/i18n/index.js';
  import { askConfirm } from '../../lib/stores.js';
  import {
    commandGate,
    draftValue,
    entryId,
    formatDraft,
    isRisky,
    parseDraft,
    recentWrites,
    selectOptions,
    usesSelect,
  } from './grouping.js';

  let {
    entry,
    profile = null,
    live = null,
    prefs = null,
    lang = 'en',
    commandMap = {},
  } = $props();

  let touched = $state(false);
  let text = $state('');
  let pending = $state(false);
  let localCommand = $state(null);
  let errorCode = $state('');

  const id = $derived(entryId(entry));
  const baseline = $derived(formatDraft(entry, draftValue(entry)));
  const shown = $derived(touched ? text : baseline);
  const parsed = $derived(parseDraft(entry, shown));
  const validation = $derived(validate(entry, parsed, profile));
  const gate = $derived(commandGate(entry, { profile, prefs, live, value: parsed }));
  const label = $derived(entry.label?.[lang] || entry.label?.en || id);
  const choose = $derived(usesSelect(entry));
  const options = $derived(selectOptions(entry));
  const disabled = $derived(!validation.ok || Boolean(gate) || pending);

  const readbackKey = $derived(entry.readback?.[0] ?? (entry.path && live?.topics?.[entry.path] ? entry.path : null));
  const current = $derived(readbackKey ? presentTopic(live?.topics?.[readbackKey], {
    deviceOnline: live?.device_online,
    lang,
  }) : null);

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

  async function submit() {
    const value = parseDraft(entry, shown);
    const check = validate(entry, value, profile);
    const blocked = commandGate(entry, { profile, prefs, live, value });
    if (!check.ok || blocked) return;
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
        body: translate(lang, 'settings.riskyBody'),
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

<article data-testid={`control-${id}`} data-gate={gate ?? undefined} data-name={id}>
  <label>
    <span class="name">{label}</span>
    {#if choose}
      <select data-testid={`value-${id}`} data-type={entry.type} data-valid={validation.ok ? 'true' : 'false'} value={shown} onchange={(event) => edit(event.currentTarget.value)}>
        {#each options as option (String(option))}
          <option value={String(option)} selected={String(option) === shown}>{option}</option>
        {/each}
      </select>
    {:else if entry.type === 'json'}
      <textarea data-testid={`value-${id}`} data-type="json" data-valid={validation.ok ? 'true' : 'false'} value={shown} oninput={(event) => edit(event.currentTarget.value)}></textarea>
      <span class="hint">{translate(lang, 'settings.jsonHint')}</span>
    {:else}
      <input data-testid={`value-${id}`} data-type={entry.type} data-valid={validation.ok ? 'true' : 'false'} value={shown} inputmode="decimal" oninput={(event) => edit(event.currentTarget.value)} />
    {/if}
  </label>
  <p class="current">
    {translate(lang, 'settings.current')}:
    {#if current}
      <span class={current.className}>{current.text}</span>
    {:else}
      {translate(lang, 'settings.noValue')}
    {/if}
  </p>
  {#if entry.min_firmware && entry.min_firmware !== '3.2.3'}
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
    <p data-testid={`gate-${id}`}>{translate(lang, 'settings.firmwareTooOld', { version: entry.min_firmware })}</p>
  {:else if gate}
    <p data-testid={`gate-${id}`}>{translate(lang, 'settings.gateExplain', { code: gate })}</p>
  {:else if touched && !validation.ok}
    <p data-testid={`validation-${id}`}>{translate(lang, 'settings.invalid', { code: validation.error })}</p>
  {/if}
  {#if statusRow?.status}
    <CommandStatus status={statusRow.status} detail={statusRow.detail} />
    {#if statusRow.status === 'sent'}
      <p class="note">{translate(lang, 'settings.sentNote')}</p>
    {/if}
  {/if}
  {#if errorCode}
    <p data-testid={`error-${id}`}>{errorCode}</p>
  {/if}
  <ApplyButton label={translate(lang, 'settings.apply')} disabled={disabled} pending={pending} testid={`apply-${id}`} onclick={submit} />
</article>
