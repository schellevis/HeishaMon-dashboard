<script>
  import { translate } from '../../lib/i18n/index.js';
  import CommandStatus from '../CommandStatus.svelte';

  // `result`: { command: Command|null, error: string|null }
  let { lang = 'en', result = null, id = 'result' } = $props();
  const t = (key, params) => translate(lang, `curve.${key}`, params);
  const cmd = $derived(result?.command ?? null);
  const failed = $derived(cmd?.keys ? Object.entries(cmd.keys).filter(([, v]) => v.status === 'failed').map(([k]) => k) : []);
</script>

{#if result}
  <div class="result" data-testid="result-{id}">
    {#if result.error}
      <p role="alert">{t('rejected', { code: result.error })}</p>
    {:else if cmd}
      <CommandStatus status={cmd.status} detail={cmd.detail} />
      {#if cmd.keys}
        <ul data-testid="key-status" aria-label={t('keyStatus')}>
          {#each Object.entries(cmd.keys) as [key, v] (key)}
            <li data-key={key} data-status={v.status}>{key}: {v.expected} <CommandStatus status={v.status} /></li>
          {/each}
        </ul>
        {#if failed.length}
          <p role="alert" data-testid="keys-failed">{t('keysFailed', { keys: failed.join(', ') })}</p>
        {/if}
      {/if}
    {/if}
  </div>
{/if}
