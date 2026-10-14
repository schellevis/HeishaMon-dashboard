<script>
  import { translate } from '../../lib/i18n/index.js';
  import {
    THRESHOLDS,
    X_RANGE,
    Y_RANGE,
    curveLine,
    makeScale,
    moveHandle,
    windowColor,
  } from '../../lib/curvegeom.js';

  let {
    lang = 'en',
    mode = 'heat',
    current = null,
    draft = null,
    shift = 0,
    showShift = false,
    directSetpoint = null,
    inactive = false, // draw the curve inactive even without a direct setpoint
    editable = true,
    outside = null,
    reportedTarget = null,
    actualWater = null,
    thresholds = null, // { heaterOn: { value }, heatingOff: { value } } heat tabs only
    switchMarkers = null, // { heatToCool, coolToHeat } read-only
    overlay = null, // { windows, median }
    colorBy = 'water_minus_target',
    coupled = false, // direct mode + room sensor: no target-ordering rule
    onchange = () => {},
    onthreshold = () => {},
  } = $props();

  const W = 640;
  const H = 360;
  const M = { left: 44, right: 14, top: 24, bottom: 34 };
  const xd = $derived(X_RANGE[mode]);
  const yd = $derived(Y_RANGE[mode]);
  const sx = $derived(makeScale(xd, [M.left, W - M.right]));
  const sy = $derived(makeScale(yd, [H - M.bottom, M.top]));
  const t = (key, params) => translate(lang, `curve.${key}`, params);

  const shown = $derived(draft ?? current);
  const changed = $derived(draft && current && JSON.stringify(draft) !== JSON.stringify(current));
  const points = (line) => line.map(([x, y]) => `${sx(x)},${sy(y)}`).join(' ');
  const xTicks = $derived(ticks(xd, 5));
  const yTicks = $derived(ticks(yd, 10));

  function ticks([a, b], step) {
    const out = [];
    for (let v = Math.ceil(a / step) * step; v <= b; v += step) out.push(v);
    return out;
  }

  let svg = $state(null);
  let dragging = $state(null);

  function toData(event) {
    const rect = svg?.getBoundingClientRect?.();
    if (!rect || !rect.width || !rect.height) return null;
    const px = ((event.clientX - rect.left) * W) / rect.width;
    const py = ((event.clientY - rect.top) * H) / rect.height;
    return { x: sx.invert(px), y: sy.invert(py) };
  }

  function start(kind, event) {
    if (!editable && kind.startsWith('curve')) return;
    dragging = kind;
    event.preventDefault?.();
  }

  function applyPoint(kind, x, y) {
    if (kind === 'curve:cold' || kind === 'curve:warm') {
      const end = kind.split(':')[1];
      let next = moveHandle(shown, mode, end, 'outside', x, { coupled });
      next = moveHandle(next, mode, end, 'target', y, { coupled });
      onchange(next);
    } else if (kind.startsWith('threshold:')) {
      moveThreshold(kind.split(':')[1], x);
    }
  }

  function moveThreshold(name, x) {
    const lim = THRESHOLDS[name];
    onthreshold(name, Math.min(lim.max, Math.max(lim.min, Math.round(x))));
  }

  function move(event) {
    if (!dragging) return;
    const p = toData(event);
    if (p) applyPoint(dragging, p.x, p.y);
  }

  function stop() {
    dragging = null;
  }

  function key(kind, event) {
    const dx = { ArrowLeft: -1, ArrowRight: 1 }[event.key] ?? 0;
    const dy = { ArrowDown: -1, ArrowUp: 1 }[event.key] ?? 0;
    if (!dx && !dy) return;
    event.preventDefault();
    if (kind.startsWith('threshold:')) {
      const name = kind.split(':')[1];
      moveThreshold(name, thresholds[name].value + dx);
      return;
    }
    if (!editable) return;
    const end = kind.split(':')[1];
    let next = shown;
    if (dx) next = moveHandle(next, mode, end, 'outside', shown[end].outside + dx, { coupled });
    if (dy) next = moveHandle(next, mode, end, 'target', shown[end].target + dy, { coupled });
    onchange(next);
  }

  const thresholdLabel = { heaterOn: 'heaterOnBelow', heatingOff: 'heatingOffAbove' };
  /** Labels of markers in the right half are drawn to the left of the line, so they stay inside the chart. */
  const flip = (value) => sx(value) > (M.left + W - M.right) / 2;
  /** Short label: the note's lead-in before its colon ("Model assumption"). */
  const assumptionLabel = $derived(t('assumptionNote').split(':')[0]);
  const hasLive = $derived(Number.isFinite(outside));
</script>

<svg
  bind:this={svg}
  class="curve-chart"
  data-testid="curve-chart"
  viewBox="0 0 {W} {H}"
  role="img"
  aria-label={t('chartLabel')}
  onpointermove={move}
  onpointerup={stop}
  onpointercancel={stop}
  onpointerleave={stop}
>
  {#each xTicks as v (v)}
    <line x1={sx(v)} x2={sx(v)} y1={M.top} y2={H - M.bottom} class="grid" />
    <text x={sx(v)} y={H - M.bottom + 14} text-anchor="middle" class="tick">{v}</text>
  {/each}
  {#each yTicks as v (v)}
    <line x1={M.left} x2={W - M.right} y1={sy(v)} y2={sy(v)} class="grid" />
    <text x={M.left - 6} y={sy(v) + 3} text-anchor="end" class="tick">{v}</text>
  {/each}
  <text x={W / 2} y={H - 4} text-anchor="middle" class="axis">{t('axisOutside')}</text>
  <text x={M.left - 30} y={M.top - 10} class="axis" data-testid="axis-water">{t('axisWater')}</text>

  {#if overlay}
    {#each overlay.windows ?? [] as w (w.start_ts)}
      {@const c = windowColor(w, colorBy, overlay.ranges)}
      <circle
        data-testid="overlay-point"
        data-color={c.color}
        data-no-cop={c.noCop ? 'true' : null}
        cx={sx(w.outside)}
        cy={sy(w.water)}
        r="3"
        fill={c.color}
        stroke={c.outlined ? 'var(--ink-2)' : 'none'}
        opacity="0.75"
      >
        <title>{t('windowTitle', { outside: w.outside.toFixed(1), water: w.water.toFixed(1), target: w.target.toFixed(1) })}</title>
      </circle>
    {/each}
    {#if overlay.median?.length}
      <polyline
        data-testid="overlay-median"
        class="median"
        points={points(overlay.median.map((m) => [m.band_lo + 1, m.value]))}
      />
    {/if}
  {/if}

  {#if shown}
    <rect class="flat" x={M.left} y={M.top} width={Math.max(0, sx(shown.cold.outside) - M.left)} height={H - M.top - M.bottom} />
    <rect class="flat" x={sx(shown.warm.outside)} y={M.top} width={Math.max(0, W - M.right - sx(shown.warm.outside))} height={H - M.top - M.bottom} />
    <text class="tick label" x={M.left + 4} y={H - M.bottom - 6}>{assumptionLabel}</text>
    {#if changed}
      <polyline data-testid="ghost-line" class="ghost" points={points(curveLine(current, 0, xd))} />
    {/if}
    {#if directSetpoint === null && !inactive}
      <polyline data-testid="curve-line" class="curve" class:changed={changed} points={points(curveLine(shown, 0, xd))} />
      {#if showShift && shift}
        <polyline data-testid="shift-line" class="shift" points={points(curveLine(shown, shift, xd))} />
      {/if}
    {:else}
      <polyline data-testid="curve-line" class="curve inactive-line" points={points(curveLine(shown, 0, xd))} />
      {#if directSetpoint !== null}
      <line
        data-testid="direct-line"
        class="direct"
        x1={M.left}
        x2={W - M.right}
        y1={sy(directSetpoint)}
        y2={sy(directSetpoint)}
      />
      {/if}
    {/if}
    {#each ['cold', 'warm'] as end (end)}
      <circle
        data-testid="handle-{end}"
        class="handle {end}"
        class:changed={Boolean(current) && (shown[end].outside !== current[end].outside || shown[end].target !== current[end].target)}
        class:readonly={!editable}
        cx={sx(shown[end].outside)}
        cy={sy(shown[end].target)}
        r="8"
        tabindex="0"
        role="slider"
        aria-label={end === 'cold' ? t('coldEnd') : t('warmEnd')}
        aria-valuenow={shown[end].target}
        aria-valuetext="{shown[end].outside} °C → {shown[end].target} °C"
        onpointerdown={(e) => start(`curve:${end}`, e)}
        onkeydown={(e) => key(`curve:${end}`, e)}
      />
    {/each}
  {/if}

  {#if thresholds}
    {#each Object.keys(thresholds) as name, index (name)}
      {#if Number.isFinite(thresholds[name].value)}
        <g>
          <line class="threshold" x1={sx(thresholds[name].value)} x2={sx(thresholds[name].value)} y1={M.top} y2={H - M.bottom} />
          <rect
            data-testid="marker-{name}"
            class="threshold-grip"
            x={sx(thresholds[name].value) - 6}
            y={M.top}
            width="12"
            height="18"
            tabindex="0"
            role="slider"
            aria-label={t(thresholdLabel[name])}
            aria-valuenow={thresholds[name].value}
            onpointerdown={(e) => start(`threshold:${name}`, e)}
            onkeydown={(e) => key(`threshold:${name}`, e)}
          />
          <text
            data-testid="label-{name}"
            x={sx(thresholds[name].value) + (flip(thresholds[name].value) ? -9 : 9)}
            y={M.top + 12 + index * 14}
            text-anchor={flip(thresholds[name].value) ? 'end' : 'start'}
            class="tick label"
          >{t(thresholdLabel[name])} {thresholds[name].value}</text>
        </g>
      {/if}
    {/each}
  {/if}

  {#if switchMarkers}
    {#each [['heatToCool', switchMarkers.heatToCool], ['coolToHeat', switchMarkers.coolToHeat]] as [name, v] (name)}
      {#if Number.isFinite(v)}
        <g data-testid="switch-{name}">
          <line class="threshold readonly" x1={sx(v)} x2={sx(v)} y1={M.top} y2={H - M.bottom} />
          <text x={sx(v) + (flip(v) ? -4 : 4)} y={H - M.bottom - 6} text-anchor={flip(v) ? 'end' : 'start'} class="tick label">{t(name)} {v} ({t('readOnly')})</text>
        </g>
      {/if}
    {/each}
  {/if}

  {#if hasLive}
    <line data-testid="live-outside" class="live" x1={sx(outside)} x2={sx(outside)} y1={M.top} y2={H - M.bottom} />
    {#if Number.isFinite(reportedTarget)}
      <circle data-testid="live-target" class="live-target" cx={sx(outside)} cy={sy(reportedTarget)} r="5">
        <title>{t('liveTarget')} {reportedTarget} °C</title>
      </circle>
    {/if}
    {#if Number.isFinite(actualWater)}
      <circle data-testid="live-water" class="live-water" cx={sx(outside)} cy={sy(actualWater)} r="5">
        <title>{t('liveWater')} {actualWater} °C</title>
      </circle>
    {/if}
  {/if}
</svg>

<style>
  .curve-chart { width: 100%; height: auto; touch-action: none; }
  .grid { stroke: var(--line); stroke-width: 1; }
  .tick, .axis { font-size: 10px; fill: currentColor; }
  .label { paint-order: stroke; stroke: var(--panel); stroke-width: 3px; stroke-linejoin: round; fill: var(--ink-3); }
  .curve { fill: none; stroke: var(--ink); stroke-width: 2.6; }
  .curve.changed { stroke: var(--pending); }
  .curve.inactive-line { stroke-dasharray: 2 4; opacity: 0.6; }
  .ghost { fill: none; stroke: var(--ink-3); stroke-width: 2; stroke-dasharray: 6 5; }
  .shift { fill: none; stroke: var(--warm); stroke-width: 1.4; stroke-dasharray: 4 4; }
  .direct { stroke: var(--warm); stroke-width: 2; }
  .handle { fill: var(--panel); stroke: var(--ink); stroke-width: 2.5; cursor: grab; }
  .handle.cold { stroke: var(--cold); }
  .handle.warm { stroke: var(--warm); }
  .handle.changed { stroke: var(--pending); }
  .handle.readonly { cursor: default; }
  .threshold { stroke: var(--pending); stroke-width: 1.5; stroke-dasharray: 4 3; }
  .threshold.readonly { stroke: var(--ink-3); }
  .threshold-grip { fill: var(--pending); cursor: ew-resize; }
  .live { stroke: var(--ink-2); stroke-width: 1; stroke-dasharray: 2 3; }
  .live-target { fill: none; stroke: var(--warm); stroke-width: 2; }
  .live-water { fill: var(--warm); }
  .median { fill: none; stroke: var(--ink); stroke-width: 1.3; stroke-dasharray: 1 4; stroke-linecap: round; }
  .flat { fill: var(--panel-2); opacity: .6; }
</style>
