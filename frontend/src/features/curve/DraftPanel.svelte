<script>
  import { translate } from '../../lib/i18n/index.js';
  import ApplyButton from '../../lib/ui/ApplyButton.svelte';

  // groups: [{ id, command, label, rows: [{ key, from, to }], applyLabel, onapply, pending, command: Command|null }]
  let { lang = 'en', groups = [], ondiscard = () => {}, eepromWarning = false } = $props();
  const t = (key, params) => translate(lang, `curve.${key}`, params);
  const nonEmpty = $derived(groups.filter((g) => g.rows.length));
</script>

<section class="draft panel" data-testid="draft-panel">
  <div class="panel-head"><h3>{t('draftTitle')}</h3></div>
  <div class="panel-body">
  {#if !nonEmpty.length}
    <p>{t('draftNone')}</p>
  {/if}
  {#each nonEmpty as group (group.id)}
    <div class="group" data-testid="draft-group-{group.id}">
      <h4>{group.label}</h4>
      <table>
        <thead><tr><th></th><th>{t('diffFrom')}</th><th>{t('diffTo')}</th></tr></thead>
        <tbody>
          {#each group.rows as row (row.key)}
            <tr><td>{row.key}</td><td>{row.from}</td><td>{row.to}</td></tr>
          {/each}
        </tbody>
      </table>
      <ApplyButton testid="apply-{group.id}" label={group.applyLabel} pending={group.pending} onclick={group.onapply} />
    </div>
  {/each}
  {#if nonEmpty.length}
    <button type="button" data-testid="discard-draft" onclick={ondiscard}>{t('discard')}</button>
  {/if}
  {#if eepromWarning}
    <p role="alert" data-testid="eeprom-warning">{t('eepromWarn')}</p>
  {/if}
  </div>
</section>
