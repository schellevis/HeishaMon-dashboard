<script>
  import { activityLabel, activityOf, errorText, formatAge, modeLabel, operatingModeValue } from '../lib/format.js';
  import { translate } from '../lib/i18n/index.js';
  import { resolvedTheme, setTheme } from '../lib/theme.js';
  import { language, prefs, profile, state as deviceState, system, updatePrefs } from '../lib/stores.js';

  let { now = undefined } = $props();
  let clock = $state(Date.now());

  $effect(() => {
    if (now != null) return;
    const timer = setInterval(() => {
      clock = Date.now();
    }, 1000);
    return () => clearInterval(timer);
  });

  let shownNow = $derived(now ?? clock);
  let offline = $derived($deviceState?.device_online === 'offline');
  let deviceLabel = $derived(
    $deviceState?.device_online === 'online'
      ? translate($language, 'common.online')
      : $deviceState?.device_online === 'offline'
        ? translate($language, 'common.offline')
        : translate($language, 'common.unknown'),
  );
  let brokerLabel = $derived(
    $deviceState?.broker_connected
      ? translate($language, 'common.brokerConnected')
      : translate($language, 'common.brokerDisconnected'),
  );
  let ageText = $derived(
    $deviceState?.last_device_message == null
      ? translate($language, 'common.ageUnknown')
      : formatAge(Math.max(0, shownNow - $deviceState.last_device_message), $language),
  );
  let errorLabel = $derived(errorText($deviceState) ?? translate($language, 'common.errorNone'));
  let mode = $derived(modeLabel(operatingModeValue($deviceState, $profile), $language));
  let activity = $derived(activityLabel(activityOf($deviceState, $profile), $language));
  const nextTheme = $derived($resolvedTheme === 'night' ? 'day' : 'night');
  // Restart the pulse animation on every new device message.
  let pulseKey = $derived($deviceState?.last_device_message ?? 0);
  let firmware = $derived($profile?.firmware?.value ?? null);

  async function toggleWriteLock() {
    if (!$prefs) return;
    await updatePrefs((cur) => ({ write_lock: !cur.write_lock }));
  }
</script>

<div class="status" data-testid="status-bar">
  <span class="item" data-testid="device-status" class:value-stale={offline}>
    {#key pulseKey}<span class="pulse" class:off={$deviceState?.device_online !== 'online'} aria-hidden="true"></span>{/key}
    <span class="val">{deviceLabel}</span>
    {#if offline}<span class="tag age">{ageText}</span>{/if}
  </span>
  <span class="item tag" data-testid="last-message">{translate($language, 'common.lastMessage')}: {ageText}</span>
  <span class="item" data-testid="operating-mode" class:value-stale={offline}><span class="tag">{translate($language, 'common.operatingMode')}</span> <span class="val">{mode}</span></span>
  <span class="item hide-m" data-testid="activity" class:value-stale={offline}><span class="tag">{translate($language, 'common.activity')}</span> <span class="val">{activity}</span></span>
  <span class="item hide-m" data-testid="error-code" class:value-stale={offline}><span class="tag">{translate($language, 'common.errorCode')}</span> <span class="val">{errorLabel}</span></span>
  <span class="item hide-m" data-testid="broker-status"><span class="tag">MQTT</span> <span class="val">{brokerLabel}</span></span>
  {#if firmware}<span class="item hide-m"><span class="tag">HeishaMon</span> <span class="val">{firmware}</span></span>{/if}
  <span class="grow"></span>
  {#if $system && $system.last_flush_ok === false}
    <span class="item flush" data-testid="flush-error">
      {translate($language, 'common.flushFailed')}{ $system.last_flush_error ? `: ${$system.last_flush_error}` : ''}
    </span>
  {/if}
  <button
    type="button"
    class="chip"
    class:locked={$prefs?.write_lock === true}
    class:unlocked={$prefs?.write_lock === false}
    data-testid="write-lock"
    aria-pressed={$prefs?.write_lock === true}
    disabled={$prefs == null}
    onclick={toggleWriteLock}
  >
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 11h14v9H5zM8 11V8a4 4 0 0 1 8 0v3" /></svg>
    {translate($language, 'common.writeLock')}:
    {$prefs?.write_lock ? translate($language, 'common.writeLockOn') : translate($language, 'common.writeLockOff')}
  </button>
  <button type="button" class="chip" data-testid="theme-toggle" title={translate($language, 'common.themeToggle')} onclick={() => setTheme(nextTheme)}>
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 8a4 4 0 1 0 0 8 4 4 0 1 0 0-8M12 3v2M12 19v2M3 12h2M19 12h2" /></svg>
    {translate($language, nextTheme === 'day' ? 'common.themeDay' : 'common.themeNight')}
  </button>
  <div class="langs" data-testid="language-switch" role="group" aria-label={translate($language, 'common.language')}>
    <button type="button" class="chip" data-testid="lang-en" aria-pressed={$language === 'en'} onclick={() => language.set('en')}>
      {translate($language, 'common.langEn')}
    </button>
    <button type="button" class="chip" data-testid="lang-nl" aria-pressed={$language === 'nl'} onclick={() => language.set('nl')}>
      {translate($language, 'common.langNl')}
    </button>
  </div>
</div>

<style>
  .status {
    display: flex; flex-wrap: wrap; align-items: center; gap: 8px 18px;
    padding: 10px 24px; border-bottom: 1px solid var(--line); background: var(--ground);
    position: sticky; top: 0; z-index: 5; min-width: 0;
  }
  .item { display: inline-flex; align-items: baseline; gap: 7px; white-space: nowrap; }
  .val { font: 500 12.5px var(--font-data); font-stretch: 87.5%; }
  .grow { flex: 1; }
  .pulse { width: 8px; height: 8px; border-radius: 50%; background: var(--ok); align-self: center; animation: beat .9s ease-out; }
  .pulse.off { background: var(--ink-3); animation: none; }
  @keyframes beat { from { box-shadow: 0 0 0 0 color-mix(in srgb, var(--ok) 70%, transparent); } to { box-shadow: 0 0 0 8px transparent; } }
  .chip { display: inline-flex; align-items: center; gap: 7px; padding: 5px 10px; border-radius: 999px; font-size: 12.5px; }
  .chip svg { width: 14px; height: 14px; stroke: currentColor; fill: none; stroke-width: 1.8; }
  .chip.locked { border-color: color-mix(in srgb, var(--ok) 55%, var(--line-2)); }
  .chip.unlocked { border-color: var(--pending); color: var(--pending-ink); }
  .langs { display: inline-flex; gap: 4px; }
  .flush { color: var(--fail-ink); }
  @media (max-width: 759px) {
    .status { padding: 8px 14px; gap: 8px 12px; }
    .hide-m { display: none; }
  }
</style>
