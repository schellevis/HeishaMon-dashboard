<script>
  import { translate } from '../../lib/i18n/index.js';
  import { overlayModes } from '../../lib/curvegeom.js';

  let {
    lang = 'en',
    data = null,
    loading = false,
    error = null,
    range = '14',
    colorBy = 'water_minus_target',
    from = '',
    to = '',
    onrange = () => {},
    oncolor = () => {},
    oncustom = () => {},
  } = $props();

  const t = (key, params) => translate(lang, `curve.${key}`, params);
  const modes = $derived(overlayModes(data?.windows ?? []));
  const colorKey = {
    water_minus_target: 'colorWaterMinusTarget',
    cop: 'colorCop',
    freq: 'colorFreq',
    side: 'colorSide',
    room_minus_setpoint: 'colorRoom',
  };
  const maxHours = $derived(Math.max(1, ...(data?.histogram ?? []).map((h) => h.hours)));
  const hasNoCop = $derived(colorBy === 'cop' && (data?.windows ?? []).some((w) => w.cop === null || w.cop === undefined));
</script>

<section class="overlay" data-testid="overlay-panel">
  <h3>{t('overlayTitle')}</h3>
  <div role="group" aria-label={t('overlayRange')}>
    {#each [['7', 'range7'], ['14', 'range14'], ['30', 'range30'], ['custom', 'rangeCustom']] as [value, label] (value)}
      <button type="button" data-testid="range-{value}" aria-pressed={range === value} onclick={() => onrange(value)}>{t(label)}</button>
    {/each}
  </div>
  {#if range === 'custom'}
    <label>{t('rangeFrom')} <input type="date" data-testid="range-from" value={from} onchange={(e) => oncustom(e.currentTarget.value, to)} /></label>
    <label>{t('rangeTo')} <input type="date" data-testid="range-to" value={to} onchange={(e) => oncustom(from, e.currentTarget.value)} /></label>
  {/if}
  <label>
    {t('colorBy')}
    <select data-testid="color-by" value={colorBy} onchange={(e) => oncolor(e.currentTarget.value)}>
      {#each modes as m (m)}
        <option value={m} selected={m === colorBy}>{t(colorKey[m])}</option>
      {/each}
    </select>
  </label>
  {#if loading}
    <p data-testid="overlay-loading">{t('overlayLoading')}</p>
  {:else if error}
    <p role="alert" data-testid="overlay-error">{t('overlayError', { code: error })}</p>
  {:else if data && !data.windows.length}
    <p data-testid="overlay-empty">{t('overlayEmpty')}</p>
  {/if}
  {#if hasNoCop}<p data-testid="no-cop-note">{t('noCop')}</p>{/if}
  {#if colorBy === 'side' && data?.boundary_ts}
    <p>{t('sideBefore')} / {t('sideAfter')} · {t('sideBoundary')}</p>
  {/if}
  {#if data?.histogram?.length}
    <div class="histogram" data-testid="overlay-histogram" aria-label={t('histogram')}>
      <h4>{t('histogram')}</h4>
      {#each data.histogram as h (h.band_lo)}
        <div class="bar-row" data-band={h.band_lo}>
          <span>{h.band_lo}…{h.band_lo + 2} °C</span>
          <span class="bar" style="width: {(h.hours / maxHours) * 100}%"></span>
          <span>{t('hours', { hours: h.hours.toFixed(1) })}</span>
        </div>
      {/each}
    </div>
  {/if}
  <p class="hint">{t('overlayNote')}</p>
</section>
