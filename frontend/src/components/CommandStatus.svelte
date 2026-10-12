<script>
  import { translate } from '../lib/i18n/index.js';
  import { language } from '../lib/stores.js';

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
</script>

<span data-testid="command-status" data-status={status}>
  {translate($language, keys[status] ?? status)}
  {#if detail}<span class="detail">{detail}</span>{/if}
</span>

<style>
  span[data-status] {
    display: inline-flex;
    gap: 0.25rem;
    align-items: baseline;
    padding: 0.1rem 0.5rem;
    border-radius: 999px;
    font-size: 0.75rem;
    background: var(--bg-secondary);
    color: var(--text-secondary);
    white-space: nowrap;
  }
  span[data-status='confirmed'] {
    background: #dcfce7;
    color: #166534;
  }
  span[data-status='failed'] {
    background: #fee2e2;
    color: #991b1b;
  }
  span[data-status='pending'],
  span[data-status='retried'] {
    background: #fef3c7;
    color: #92400e;
  }
  .detail {
    opacity: 0.8;
  }
</style>
