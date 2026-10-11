<script>
  import { api } from '../lib/api.js';
  import { activityLabel, activityOf, errorText, formatAge, modeLabel, operatingModeValue } from '../lib/format.js';
  import { translate } from '../lib/i18n/index.js';
  import { language, prefs, profile, state as deviceState, system } from '../lib/stores.js';

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
  let staleClass = $derived(offline ? 'value-stale' : '');

  async function toggleWriteLock() {
    if (!$prefs) return;
    const next = { ...$prefs, write_lock: !$prefs.write_lock };
    const saved = await api.putPrefs(next);
    prefs.set(saved);
  }
</script>

<div class="status" data-testid="status-bar">
  <span data-testid="device-status" class={staleClass}>
    {deviceLabel}
    {#if offline}<span class="age">{ageText}</span>{/if}
  </span>
  <span data-testid="broker-status">{brokerLabel}</span>
  <span data-testid="last-message">{translate($language, 'common.lastMessage')}: {ageText}</span>
  <span data-testid="error-code" class={staleClass}>{translate($language, 'common.errorCode')}: {errorLabel}</span>
  <span data-testid="operating-mode" class={staleClass}>{translate($language, 'common.operatingMode')}: {mode}</span>
  <span data-testid="activity" class={staleClass}>{translate($language, 'common.activity')}: {activity}</span>
  <button
    type="button"
    data-testid="write-lock"
    aria-pressed={$prefs?.write_lock === true}
    disabled={$prefs == null}
    onclick={toggleWriteLock}
  >
    {translate($language, 'common.writeLock')}:
    {$prefs?.write_lock ? translate($language, 'common.writeLockOn') : translate($language, 'common.writeLockOff')}
  </button>
  <div data-testid="language-switch" role="group" aria-label={translate($language, 'common.language')}>
    <button type="button" data-testid="lang-en" aria-pressed={$language === 'en'} onclick={() => language.set('en')}>
      {translate($language, 'common.langEn')}
    </button>
    <button type="button" data-testid="lang-nl" aria-pressed={$language === 'nl'} onclick={() => language.set('nl')}>
      {translate($language, 'common.langNl')}
    </button>
  </div>
  {#if $system && $system.last_flush_ok === false}
    <span data-testid="flush-error">
      {translate($language, 'common.flushFailed')}{ $system.last_flush_error ? `: ${$system.last_flush_error}` : ''}
    </span>
  {/if}
</div>

<style>
  .status {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    align-items: center;
    padding: 0.5rem 1rem;
    min-width: 0;
  }
  .age {
    margin-left: 0.35rem;
  }
</style>
