<script>
  import { translate } from '../i18n/index.js';
  import { language } from '../stores.js';

  let { status = 'pending', detail = null } = $props();

  const keys = {
    pending: 'common.commandPending',
    retried: 'common.commandRetried',
    confirmed: 'common.commandConfirmed',
    sent: 'common.commandSent',
    noop: 'common.commandNoop',
    superseded: 'common.commandSuperseded',
    failed: 'common.commandFailed',
  };

  // known machine-readable details get a sentence; anything else (per-key JSON, codes) is shown as is
  const detailKeys = { broker_disconnected: 'common.commandDetail_broker_disconnected', rate_limited: 'common.commandDetail_rate_limited' };
</script>

<span data-testid="command-status" data-status={status}>
  {translate($language, keys[status] ?? status)}
  {#if detail}<span class="detail">{detailKeys[detail] ? translate($language, detailKeys[detail]) : detail}</span>{/if}
</span>

<style>
  span[data-status] {
    display: inline-flex;
    gap: 0.25rem;
    align-items: baseline;
    padding: 0.1rem 0.5rem;
    border-radius: 999px;
    font-size: 0.75rem;
    background: var(--panel-2);
    color: var(--ink-2);
    white-space: nowrap;
  }
  span[data-status='confirmed'] {
    background: color-mix(in srgb, var(--ok) 16%, transparent);
    color: var(--ok-ink);
  }
  span[data-status='failed'] {
    background: color-mix(in srgb, var(--fail) 16%, transparent);
    color: var(--fail-ink);
  }
  span[data-status='pending'],
  span[data-status='retried'] {
    background: color-mix(in srgb, var(--pending) 16%, transparent);
    color: var(--pending-ink);
  }
  .detail {
    opacity: 0.8;
  }
</style>
