<script>
  import { translate } from '../../lib/i18n/index.js';

  // entries: [{ id, ts, summary, status, canRevert, onrevert }]
  let { lang = 'en', entries = [], notice = null } = $props();
  const t = (key, params) => translate(lang, `curve.${key}`, params);
</script>

<section class="log" data-testid="curve-log">
  <h3>{t('logTitle')}</h3>
  {#if !entries.length}
    <p>{t('logNone')}</p>
  {/if}
  <ul>
    {#each entries as e (e.id)}
      <li data-testid="log-entry" data-status={e.status}>
        <time>{new Date(e.ts).toLocaleString(lang)}</time>
        <span>{e.summary}</span>
        <button type="button" data-testid="revert" disabled={!e.canRevert} title={e.canRevert ? '' : t('revertUnknown')} onclick={e.onrevert}>{t('revert')}</button>
      </li>
    {/each}
  </ul>
  {#if notice}<p data-testid="revert-notice">{notice}</p>{/if}
  <p class="hint" data-testid="wait-hint">{t('waitHint')}</p>
</section>
