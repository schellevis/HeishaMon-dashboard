<script>
  import { translate } from '../../lib/i18n/index.js';
  import { LIMITS, levelStep, moveHandle, slopeStep } from '../../lib/curvegeom.js';

  let { lang = 'en', mode = 'heat', shown = null, coupled = false, onchange = () => {} } = $props();

  let editorMode = $state('two-point');
  const t = (key, params) => translate(lang, `curve.${key}`, params);
  const lim = $derived(LIMITS[mode]);

  function typed(end, field, event) {
    const raw = event.currentTarget.value;
    const parsed = Number(raw);
    if (raw === '' || !Number.isFinite(parsed)) {
      event.currentTarget.value = String(shown[end][field]);
      return;
    }
    const next = moveHandle(shown, mode, end, field, parsed, { coupled });
    event.currentTarget.value = String(next[end][field]);
    if (next !== shown) onchange(next);
  }

  const steps = $derived(
    shown
      ? {
          'level-minus': levelStep(shown, mode, -1, { coupled }),
          'level-plus': levelStep(shown, mode, 1, { coupled }),
          'slope-minus': slopeStep(shown, mode, -1, { coupled }),
          'slope-plus': slopeStep(shown, mode, 1, { coupled }),
        }
      : {},
  );

  function step(name) {
    if (steps[name]) onchange(steps[name]);
  }
</script>

{#if shown}
  <div class="editor panel panel-body" data-testid="curve-editor">
    <div role="group" aria-label={t('editorMode')}>
      <button type="button" data-testid="editor-two-point" aria-pressed={editorMode === 'two-point'} onclick={() => (editorMode = 'two-point')}>{t('twoPoint')}</button>
      <button type="button" data-testid="editor-slope-level" aria-pressed={editorMode === 'slope-level'} onclick={() => (editorMode = 'slope-level')}>{t('slopeLevel')}</button>
    </div>

    {#if editorMode === 'two-point'}
      {#each ['cold', 'warm'] as end (end)}
        <fieldset>
          <legend>{end === 'cold' ? t('coldEnd') : t('warmEnd')}</legend>
          <label>
            {t('outsideField')}
            <input
              type="number"
              step="1"
              min={lim.outside[0]}
              max={lim.outside[1]}
              data-testid="input-{end}-outside"
              value={shown[end].outside}
              onchange={(e) => typed(end, 'outside', e)}
            />
          </label>
          <label>
            {t('targetField')}
            <input
              type="number"
              step="1"
              min={lim.target[0]}
              max={lim.target[1]}
              data-testid="input-{end}-target"
              value={shown[end].target}
              onchange={(e) => typed(end, 'target', e)}
            />
          </label>
        </fieldset>
      {/each}
    {:else}
      {#each ['level', 'slope'] as kind (kind)}
        <div class="stepper">
          <span>{t(kind)}</span>
          <button type="button" data-testid="{kind}-minus" disabled={!steps[`${kind}-minus`]} title={steps[`${kind}-minus`] ? '' : t('stepRefused')} onclick={() => step(`${kind}-minus`)}>{t('minus')}</button>
          <button type="button" data-testid="{kind}-plus" disabled={!steps[`${kind}-plus`]} title={steps[`${kind}-plus`] ? '' : t('stepRefused')} onclick={() => step(`${kind}-plus`)}>{t('plus')}</button>
        </div>
      {/each}
    {/if}
    <p class="hint" data-testid="editor-hint">{coupled ? t('invariantHintCoupled') : t('invariantHint')} {mode === 'heat' ? t('limitsHeat') : t('limitsCool')}</p>
  </div>
{/if}
