<script>
  import { activityLabel } from '../../lib/format.js';
  import { translate } from '../../lib/i18n/index.js';
  import { ACTIVITY_VAR, tempColor } from '../../lib/ui/thermal.js';
  import { plantGeometry, plantModel } from './plant.js';

  let { stateData = null, profile = null, lang = 'en' } = $props();

  const m = $derived(plantModel(stateData, profile));
  const g = $derived(plantGeometry(m));
  const t = (key, params) => translate(lang, `overview.${key}`, params);
  const deg = (v) => (v === null ? '—' : `${v.toFixed(1)}°`);
  const plain = (v, d = 0) => (v === null ? '—' : v.toFixed(d));

  const toZone = $derived(m.valve === 'room');
  const idle = 'var(--pipe-idle)';
  const flowCol = $derived(m.flowing ? tempColor(m.flow) : idle);
  const retCol = $derived(m.flowing ? tempColor(m.ret) : idle);
  const sub = $derived.by(() => {
    if (m.activity === 'dhw' && m.dhw) return t('subDhw', { t: plain(m.dhw.temp), target: plain(m.dhw.target) });
    if (m.activity === 'heating' || m.activity === 'cooling') {
      const zones = m.zones.map((z) => z.id.slice(1)).join('+');
      const ctl = m.controlMode === 'curve' ? t('subCurve') : m.controlMode === 'direct' ? t('subDirect') : null;
      return [t('subZones', { z: zones }), ctl].filter(Boolean).join(' · ');
    }
    return '';
  });
  let scroller = $state(null);
  $effect(() => {
    if (scroller) scroller.scrollLeft = (scroller.scrollWidth - scroller.clientWidth) * 0.65;
  });
  const blade = 'M125 175 C 120 150, 128 130, 140 128 C 142 150, 133 165, 125 175Z';
</script>

<div class="panel plant" data-testid="plant" style:--flow-period={m.flowPeriod ? `${m.flowPeriod}s` : '0s'}>
  <div class="head">
    <div class="activity">
      <span class="dot" style:background={`var(${ACTIVITY_VAR[m.activity]})`}></span>
      <span>{activityLabel(m.activity, lang)}</span>
      {#if sub}<small>{sub}</small>{/if}
    </div>
    <div class="legend" aria-label={t('tempScale')}><span class="num">15°</span><span class="ramp"></span><span class="num">55°</span></div>
  </div>
  <div class="scroll" bind:this={scroller}>
    <svg viewBox="0 40 960 345" role="img" aria-label={t('plantLabel')}>
      <!-- outdoor unit -->
      <rect class="unit" x="30" y="70" width="190" height="220" rx="12" />
      <text class="unit-label" x="44" y="92">{t('plantOutdoor')}</text>
      <circle cx="125" cy="175" r="58" class="ring" />
      <g class="fan" class:spin={m.fanSpinning}>
        <path d={blade} /><path d={blade} transform="rotate(120 125 175)" /><path d={blade} transform="rotate(240 125 175)" />
        <circle cx="125" cy="175" r="6" class="hub" />
      </g>
      {@render bubble(64, 262, 'TT', 'OUT')}
      <text class="reading" x="86" y="262" data-testid="plant-outside">{deg(m.outside)}</text>
      <text class="reading-sub" x="86" y="275">{t('tagOutside')}</text>
      {@render bubble(160, 262, 'SC', 'CMP')}
      <text class="reading" x="182" y="262" data-testid="plant-compressor">{plain(m.compressor)}</text>
      <text class="reading-sub" x="182" y="275">HZ</text>

      <path class="refrig" d="M220 140 H330 M220 220 H330" />
      <text class="reading-sub" x="244" y="132">{t('plantRefrigerant')}</text>

      <!-- indoor unit -->
      <rect class="unit" x="330" y="60" width="170" height="310" rx="12" />
      <text class="unit-label" x="344" y="82">{t('plantIndoor')}</text>
      <path class="hex" d="M380 110 l30 14 -30 14 30 14 -30 14 30 14 -30 14 30 14" />
      <text class="reading-sub" x="376" y="250">{t('plantHex')}</text>

      <!-- main flow to the valve -->
      {@render pipe('M500 110 H600', flowCol, m.flowing)}

      <!-- zone branch -->
      <g class="branch" class:dim={!toZone}>
        {@render pipe(g.zoneFlow, toZone ? flowCol : idle, m.flowing && toZone)}
        {@render pipe(g.zoneReturn, toZone ? retCol : idle, m.flowing && toZone)}
        {#if g.buffer}
          <g data-testid="plant-buffer">
            <rect class="unit" x={g.buffer.x} y={g.buffer.y} width={g.buffer.w} height={g.buffer.h} rx="18" />
            <text class="reading-sub" x={g.buffer.x + 4} y={g.buffer.y - 6}>{t('plantBuffer')} {deg(m.buffer.temp)}</text>
          </g>
        {/if}
        {#each g.emitters as e, i (e.id)}
          <g data-testid={`plant-zone-${e.id}`}>
            <rect class="unit" x={e.x} y={e.y} width={e.w} height={e.h} rx="8" />
            <path class="hex" d={`M${e.x + 12} ${e.y + 15} H${e.x + 68} V${e.y + 30} H${e.x + 12} V${e.y + 45} H${e.x + 68} V${e.y + 60} H${e.x + 12} V${e.y + 70}`} />
            <text class="unit-label" x={e.x} y={e.y - 8}>{t('plantZone', { n: e.id.slice(1) })}</text>
            {#if m.zones[i].water !== null}<text class="reading-sub" x={e.x} y={e.y + e.h + 14}>{deg(m.zones[i].water)}</text>{/if}
          </g>
        {/each}
        {@render bubble(700, 82, 'TT', 'FLW')}
        <text class="reading" x="722" y="80" data-testid="plant-flow">{deg(m.flow)}</text>
        <text class="reading-sub" x="722" y="93">{m.target === null ? t('tagFlowNoTarget') : t('tagFlow', { t: plain(m.target) })}</text>
        {@render bubble(700, 262, 'TT', 'RET')}
        <text class="reading" x="722" y="260" data-testid="plant-return">{deg(m.ret)}</text>
        <text class="reading-sub" x="722" y="273">{t('tagReturn', { dt: plain(m.deltaT, 1) })}</text>
      </g>

      <!-- pump on the return -->
      <g transform="translate(540,230)" class="pump"><circle r="14" /><path d="M6 -6 L-8 0 L6 6" /></g>
      <text class="reading" x="520" y="206" data-testid="plant-pump">{plain(m.pumpFlow, 1)}</text>
      <text class="reading-sub" x="566" y="206">L/MIN</text>

      <!-- DHW branch -->
      {#if m.dhw}
        <g class="branch" class:dim={toZone} data-testid="plant-dhw-branch" data-active={String(!toZone)}>
          {@render pipe(g.dhwFlow, !toZone ? flowCol : idle, m.flowing && !toZone)}
          {@render pipe(g.dhwReturn, !toZone ? retCol : idle, m.flowing && !toZone)}
          <rect class="fill" x="782" y="262" width="52" height="110" rx="24" fill={tempColor(m.dhw.temp)} fill-opacity=".28" />
          <rect class="tank" x="782" y="262" width="52" height="110" rx="24" />
          <path class="hex" d="M780 290 C 815 296, 795 306, 815 314 S 795 328, 815 336 S 800 346, 780 350" />
          <text class="unit-label" x="848" y="290">{t('plantTank')}</text>
          <text class="reading" x="848" y="314" data-testid="plant-dhw">{deg(m.dhw.temp)}</text>
          <text class="reading-sub" x="848" y="327">{m.dhw.target === null ? '' : t('tagTarget', { t: plain(m.dhw.target) })}</text>
        </g>
      {/if}

      <!-- three-way valve -->
      <g transform="translate(600,110)" class="valve">
        <path d="M-11 -9 L0 0 L-11 9 Z M11 -9 L0 0 L11 9 Z" /><path d="M-8 11 L0 0 L8 11 Z" />
      </g>
      <text class="reading-sub" x="584" y="92">{t('plantValve')}</text>
    </svg>
  </div>
</div>

{#snippet bubble(x, y, top, bottom)}
  <g class="bubble" transform={`translate(${x},${y})`}>
    <circle r="15" /><line x1="-15" x2="15" y1="0" y2="0" />
    <text y="-3">{top}</text><text y="10">{bottom}</text>
  </g>
{/snippet}

{#snippet pipe(d, color, moving)}
  <path class="pipe" {d} stroke={color} />
  <path class="pipe-flow" class:moving {d} />
{/snippet}

<style>
  .plant { overflow: hidden; }
  .head { display: flex; align-items: center; gap: 14px; padding: 14px 18px 0; flex-wrap: wrap; }
  .activity { font: 600 26px/1 var(--font-ui); letter-spacing: -.015em; display: flex; align-items: center; gap: 10px; flex: 1; }
  .activity small { font: 400 14px var(--font-ui); color: var(--ink-2); letter-spacing: 0; }
  .dot { width: 10px; height: 10px; border-radius: 3px; }
  .legend { display: flex; align-items: center; gap: 8px; color: var(--ink-3); font-size: 11.5px; }
  .ramp { width: 110px; height: 6px; border-radius: 3px; background: linear-gradient(90deg, var(--cold), var(--cool) 35%, var(--warm) 65%, var(--hot)); }
  .scroll { overflow-x: auto; }
  svg { display: block; width: 100%; height: auto; }
  svg text { font-family: var(--font-data); font-stretch: 87.5%; }
  .unit { fill: var(--unit); stroke: var(--line-2); stroke-width: 1.2; }
  .tank { fill: none; stroke: var(--line-2); stroke-width: 1.4; }
  .unit-label { fill: var(--ink-3); font-size: 10px; letter-spacing: .1em; }
  .ring { fill: none; stroke: var(--line-2); stroke-width: 1.2; }
  .fan path { fill: var(--ink-3); }
  .hub { fill: var(--panel); stroke: var(--ink-3); }
  .fan { transform-origin: 125px 175px; transform-box: view-box; }
  .fan.spin { animation: spin 1.6s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .hex { fill: none; stroke: var(--ink-3); stroke-width: 1.4; }
  .refrig { fill: none; stroke: var(--line-2); stroke-width: 2; stroke-dasharray: 5 4; }
  .pipe { fill: none; stroke-width: 7; stroke-linecap: round; stroke-linejoin: round; transition: stroke .8s; }
  .pipe-flow { fill: none; stroke-width: 2.2; stroke-linecap: round; stroke-dasharray: 2 11; stroke: var(--flow-dash); opacity: 0; }
  .pipe-flow.moving { opacity: 1; animation: flow var(--flow-period) linear infinite; }
  @keyframes flow { to { stroke-dashoffset: -13; } }
  /* dim the inactive branch's pipes and equipment, never its readings (spec R1 readable text) */
  .branch.dim :is(.pipe, .pipe-flow, .unit, .tank, .hex, .fill) { opacity: .35; }
  .bubble circle { fill: var(--panel); stroke: var(--ink-2); stroke-width: 1.2; }
  .bubble line { stroke: var(--ink-2); stroke-width: 1; }
  .bubble text { fill: var(--ink-2); font-size: 9.5px; font-weight: 600; text-anchor: middle; letter-spacing: .04em; }
  .reading { fill: var(--ink); font-size: 15px; font-weight: 500; }
  .reading-sub { fill: var(--ink-3); font-size: 9.5px; letter-spacing: .06em; }
  .pump circle, .valve path { fill: var(--panel); stroke: var(--ink-2); stroke-width: 1.4; stroke-linejoin: round; }
  .pump path { fill: none; stroke: var(--ink-2); stroke-width: 1.4; }
  @media (max-width: 759px) {
    .activity { font-size: 21px; }
    svg { min-width: 720px; }
  }
</style>
