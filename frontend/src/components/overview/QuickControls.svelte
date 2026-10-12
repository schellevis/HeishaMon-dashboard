<script>
  import CommandControl from '../settings/CommandControl.svelte';
  import CurveSetpointControl from './CurveSetpointControl.svelte';
  import { isCoupled } from '../../lib/curvegeom.js';
  import { translate } from '../../lib/i18n/index.js';
  import { catalog as defaultCatalog } from '../../lib/catalog.js';

  let {
    profile = null,
    stateData = null,
    prefs = null,
    lang = 'en',
    commandMap = {},
    /** catalog override (tests); defaults to the build-time catalog */
    catalogData = null,
  } = $props();

  const source = $derived(catalogData ?? defaultCatalog);
  const commandIndex = $derived(new Map((source.commands ?? []).map((entry) => [entry.name, entry])));

  const DHW_MODES = new Set([3, 4, 5, 6, 8]);

  function known(field) {
    return field && !field.unknown ? field.value : undefined;
  }

  const hasDhw = $derived(known(profile?.dhw_installed) === true);
  const zones = $derived(known(profile?.zones) ?? 'z1');
  const z1Active = $derived(zones === 'z1' || zones === 'both');
  const z2Active = $derived(zones === 'z2' || zones === 'both');
  const showHeat = $derived(known(profile?.heating_in_use) !== false);
  const showCool = $derived(known(profile?.cooling_in_use) === true);
  const heatingControl = $derived(known(profile?.heating_control));
  const coolingControl = $derived(known(profile?.cooling_control));

  const mode = $derived.by(() => {
    const fromProfile = known(profile?.operating_mode);
    if (typeof fromProfile === 'number') return fromProfile;
    const topic = stateData?.topics?.['main/Operating_Mode_State'];
    return topic && !topic.sentinel ? topic.value : null;
  });
  const dhwCapable = $derived(mode != null && DHW_MODES.has(mode));

  function cmd(name) {
    return commandIndex.get(name) ?? null;
  }

  function signed(value) {
    if (value > 0) return `+${value}`;
    if (value < 0) return `−${Math.abs(value)}`;
    return '0';
  }

  /** Zone request label and read-out: a shift on the curve, or an absolute setpoint. */
  function requestLabel(zone, heat) {
    const control = heat ? heatingControl : coolingControl;
    const base = `${translate(lang, heat ? 'overview.heatRequest' : 'overview.coolRequest')} ${translate(lang, `overview.${zone}`)}`;
    if (control === 'curve') return `${base} (${translate(lang, 'overview.requestShift')})`;
    if (control === 'direct') return `${base} (${translate(lang, 'overview.requestSetpoint')})`;
    return base;
  }

  function requestFormatter(heat) {
    const control = heat ? heatingControl : coolingControl;
    if (control === 'curve') return (value) => `${signed(value)} °C`;
    return (value) => `${value} °C`;
  }

  const zoneControls = $derived([
    z1Active && showHeat && { zone: 'zone1', heat: true, name: 'SetZ1HeatRequestTemperature', testid: 'z1-heat' },
    z1Active && showCool && { zone: 'zone1', heat: false, name: 'SetZ1CoolRequestTemperature', testid: 'z1-cool' },
    z2Active && showHeat && { zone: 'zone2', heat: true, name: 'SetZ2HeatRequestTemperature', testid: 'z2-heat' },
    z2Active && showCool && { zone: 'zone2', heat: false, name: 'SetZ2CoolRequestTemperature', testid: 'z2-cool' },
  ].filter(Boolean).map((zc) => {
    // coupled (direct + room sensor): the setpoint lives in the curve's cold-end target
    const z = zc.zone === 'zone1' ? 'z1' : 'z2';
    const mode = zc.heat ? 'heat' : 'cool';
    return { ...zc, z, mode, coupled: isCoupled(profile, z, mode) };
  }));

  const common = $derived({ profile, live: stateData, prefs, lang, commandMap, variant: 'compact', catalogData: source });
</script>

<section class="quick-controls" data-testid="quick-controls">
  <h2>{translate(lang, 'overview.quickControls')}</h2>
  <div class="grid">
    {#if cmd('SetHeatpump')}
      <div data-testid="control-hp-power">
        <CommandControl entry={cmd('SetHeatpump')} {...common} labelText={translate(lang, 'overview.heatPump')} inputTestid="input-hp-power" applyTestid="apply-hp-power" />
      </div>
    {/if}
    {#if cmd('SetOperationMode')}
      <div data-testid="control-mode">
        <CommandControl entry={cmd('SetOperationMode')} {...common} labelText={translate(lang, 'overview.operatingMode')} inputTestid="input-mode" applyTestid="apply-mode" />
      </div>
    {/if}
    {#if cmd('SetQuietMode')}
      <div data-testid="control-quiet">
        <CommandControl entry={cmd('SetQuietMode')} {...common} labelText={translate(lang, 'overview.quietMode')} inputTestid="input-quiet" applyTestid="apply-quiet" />
      </div>
    {/if}
    {#if cmd('SetPowerfulMode')}
      <div data-testid="control-powerful">
        <CommandControl entry={cmd('SetPowerfulMode')} {...common} labelText={translate(lang, 'overview.powerfulMode')} inputTestid="input-powerful" applyTestid="apply-powerful" />
      </div>
    {/if}
    {#each zoneControls as zc (zc.name)}
      {#if zc.coupled && cmd('SetCurves')}
        <div data-testid={`control-${zc.testid}`} data-coupled="true">
          <CurveSetpointControl
            zone={zc.z}
            mode={zc.mode}
            entry={cmd('SetCurves')}
            {profile}
            live={stateData}
            {prefs}
            {lang}
            {commandMap}
            labelText={requestLabel(zc.zone, zc.heat)}
            inputTestid={`slider-${zc.testid}`}
            applyTestid={`apply-${zc.testid}`}
            noteTestid={`coupled-note-${zc.testid}`}
          />
        </div>
      {:else if cmd(zc.name)}
        <div data-testid={`control-${zc.testid}`}>
          <CommandControl
            entry={cmd(zc.name)}
            {...common}
            widget="slider"
            labelText={requestLabel(zc.zone, zc.heat)}
            formatValue={requestFormatter(zc.heat)}
            inputTestid={`slider-${zc.testid}`}
            applyTestid={`apply-${zc.testid}`}
          />
        </div>
      {/if}
    {/each}
    {#if hasDhw && cmd('SetDHWTemp')}
      <div data-testid="control-dhw-setpoint">
        <CommandControl entry={cmd('SetDHWTemp')} {...common} labelText={translate(lang, 'overview.dhwSetpoint')} inputTestid="input-dhw" applyTestid="apply-dhw" />
      </div>
    {/if}
    {#if hasDhw && cmd('SetForceDHW')}
      <div data-testid="control-force-dhw" data-enabled={dhwCapable ? 'true' : 'false'}>
        <CommandControl
          entry={cmd('SetForceDHW')}
          {...common}
          labelText={translate(lang, 'overview.forceDhw')}
          blockedNote={dhwCapable ? null : translate(lang, 'overview.forceDhwNeedsMode')}
          inputTestid="input-force-dhw"
          applyTestid="apply-force-dhw"
        />
      </div>
    {/if}
  </div>
</section>

<style>
  .quick-controls {
    border: 1px solid var(--border);
    border-radius: var(--card-radius);
    background: var(--bg);
    padding: 0.5rem 1rem 0.75rem;
  }
  h2 {
    margin: 0.25rem 0 0.25rem;
    font-size: 1rem;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(17rem, 1fr));
    column-gap: 2rem;
  }
  .grid > div {
    border-bottom: 1px solid var(--border);
    min-width: 0;
  }
  @media (max-width: 480px) {
    .grid {
      grid-template-columns: 1fr;
    }
  }
</style>
