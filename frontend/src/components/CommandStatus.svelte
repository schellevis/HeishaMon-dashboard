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
