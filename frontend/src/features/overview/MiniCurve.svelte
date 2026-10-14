<script module>
  import { curvePoints, isCoupled } from '../../lib/curvegeom.js';

  const usable = (f) => (f && !f.unknown && !f.stale ? f.value : undefined);

  /** Zone and mode of the Overview preview (spec R3.5). */
  export function activeCurve(profile, activity) {
    const zone = usable(profile?.zones) === 'z2' ? 'z2' : 'z1';
    const heat = usable(profile?.heating_in_use);
    const cool = usable(profile?.cooling_in_use);
    if (heat === false && cool === false) return null;
    if (activity === 'cooling' || (heat === false && cool === true)) return { zone, mode: 'cool' };
    return { zone, mode: 'heat' };
  }

  /** What CurveChart gets for one zone/mode; `note` is the i18n key of the label, or null. */
  export function miniView({ profile, values, zone, mode }) {
    const n = zone.slice(1);
    const M = mode === 'cool' ? 'Cool' : 'Heat';
    const curve = curvePoints(values, zone, mode);
    const control = usable(mode === 'cool' ? profile?.cooling_control : profile?.heating_control);
    const request = values[`main/Z${n}_${M}_Request_Temp`];
    const req = typeof request === 'number' && Number.isFinite(request) ? request : null;
    const coupled = control === 'direct' && isCoupled(profile, zone, mode);
    const view = { curve, shift: 0, showShift: false, directSetpoint: null, coupled, inactive: false, note: null };
    if (control === 'curve') return { ...view, shift: req ?? 0, showShift: true };
    if (control === 'direct') {
      const setpoint = coupled ? (curve?.cold.target ?? null) : req;
      if (setpoint === null) return { ...view, inactive: true, note: 'miniSetpointUnavailable' };
      return { ...view, directSetpoint: setpoint, note: coupled ? 'setpoint' : 'notActive' };
    }
    return { ...view, inactive: true, note: 'miniControlUnknown' };
  }
</script>

<script>
  import CurveChart from '../curve/CurveChart.svelte';
  import { activityOf } from '../../lib/format.js';
  import { translate } from '../../lib/i18n/index.js';

  let { stateData = null, profile = null, lang = 'en' } = $props();

  const pick = $derived(activeCurve(profile, activityOf(stateData, profile)));
  const values = $derived(Object.fromEntries(
    Object.entries(stateData?.topics ?? {})
      .filter(([, tv]) => tv && !tv.sentinel && typeof tv.value === 'number')
      .map(([k, tv]) => [k, tv.value]),
  ));
  const view = $derived(pick ? miniView({ profile, values, zone: pick.zone, mode: pick.mode }) : null);
  const n = $derived(pick ? pick.zone.slice(1) : '1');
  const outside = $derived(values['main/Outside_Temp'] ?? null);
  const reported = $derived(values[`main/Z${n}_Water_Target_Temp`] ?? null);
  const water = $derived(values[`main/Z${n}_Water_Temp`] ?? values['main/Main_Outlet_Temp'] ?? null);
  const title = $derived(translate(lang, pick?.mode === 'cool' ? 'overview.miniCurveCool' : 'overview.miniCurveHeat', { n }));
  // notActive and setpoint live in the curve module; the other notes in overview
  const noteText = $derived.by(() => {
    if (!view?.note) return null;
    if (view.note === 'notActive') return translate(lang, 'curve.notActive');
    if (view.note === 'setpoint') return `${translate(lang, 'curve.setpoint')}: ${view.directSetpoint} °C`;
    return translate(lang, `overview.${view.note}`);
  });
</script>

{#if pick && view?.curve}
  <div class="panel" data-testid="mini-curve">
    <div class="panel-head">
      <h2>{title}{#if noteText}<span class="tag note" data-testid="mini-curve-note"> · {noteText}</span>{/if}</h2>
      <a class="tag" href="#/curve">{translate(lang, 'overview.openCurve')} →</a>
    </div>
    <div class="body">
      <CurveChart {lang} mode={pick.mode} current={view.curve} shift={view.shift} showShift={view.showShift}
        directSetpoint={view.directSetpoint} coupled={view.coupled} inactive={view.inactive} editable={false}
        {outside} reportedTarget={reported} actualWater={water} />
    </div>
  </div>
{/if}

<style>
  .body { padding: 8px 12px; }
  a.tag { text-decoration: none; }
  .note { margin-left: 6px; }
</style>
