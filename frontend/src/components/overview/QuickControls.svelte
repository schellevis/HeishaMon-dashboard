<script>
  import { translate } from '../../lib/i18n/index.js';
  import ApplyButton from '../ApplyButton.svelte';
  import { askConfirm } from '../../lib/stores.js';
  import { api } from '../../lib/api.js';
  import { encode, validate, resolveRange } from '../../lib/encoding.js';
  import { commandByName } from '../../lib/catalog.js';

  let {
    profile = null,
    stateData = null,
    prefs = null,
    lang = 'en',
  } = $props();

  let eepromCount = $state(0);
  let eepromLast = $state(0);
  let pendingCommands = $state(new Set());

  const HEATING_MODES = new Set([0, 2, 4, 6]);
  const COOLING_MODES = new Set([1, 5, 7, 8]);
  const DHW_MODES = new Set([3, 4, 5, 6, 8]);

  // Derive which controls are visible
  const hasDhw = $derived(profile?.dhw_installed?.value === true);
  const dhwInUse = $derived(profile?.dhw_in_use?.value === true);
  const heatingControl = $derived(profile?.heating_control?.value ?? 'curve');
  const coolingControl = $derived(profile?.cooling_control?.value ?? 'curve');
  const zones = $derived(profile?.zones?.value ?? 'z1');
  const z1Active = $derived(zones === 'z1' || zones === 'both');
  const z2Active = $derived(zones === 'z2' || zones === 'both');

  // Check if current mode is DHW-capable
  const isDhwCapableMode = $derived(() => {
    const mode = profile?.operating_mode?.value ?? -1;
    return DHW_MODES.has(mode);
  });

  // Zone sensor types
  const z1Sensor = $derived(profile?.zone?.z1?.sensor?.value ?? 'water');
  const z2Sensor = $derived(profile?.zone?.z2?.sensor?.value ?? 'water');

  // Get current values from state
  function getTopicValue(key) {
    return stateData?.topics?.[key]?.value ?? null;
  }

  // Get range from catalog for a command, respecting conditional_ranges
  function getCommandRange(commandName, profile) {
    const cmd = commandByName(commandName);
    if (!cmd) {
      console.warn(`Command ${commandName} not found in catalog`);
      return { min: 0, max: 100, step: 1 };
    }
    
    return resolveRange(cmd, profile) ?? cmd.range ?? { min: 0, max: 100, step: 1 };
  }

  // Get the effective range for a zone request based on mode and sensor
  function getZoneRequestRange(zone, isHeat) {
    const sensor = zone === 'z1' ? z1Sensor : z2Sensor;
    const mode = isHeat ? heatingControl : coolingControl;
    
    // Get the command name - capitalize the zone identifier (z1 -> Z1)
    const zoneCapitalized = zone.toUpperCase();
    const cmdName = isHeat ? `Set${zoneCapitalized}HeatRequestTemperature` : `Set${zoneCapitalized}CoolRequestTemperature`;
    
    // Get the base range from catalog
    const cmd = commandByName(cmdName);
    const range = cmd ? resolveRange(cmd, profile) : null;
    
    // Apply conditional logic based on mode and sensor per spec Appendix A.2
    if (mode === 'curve') {
      // In curve mode, it's always -5..5 shift
      return { ...(range ?? {}), min: -5, max: 5, step: 1, isShift: true };
    } else {
      // In direct mode, the range depends on the sensor
      if (sensor === 'water') {
        // Direct mode with water sensor: heat is 20..65, cool is 5..20
        return { 
          min: isHeat ? 20 : 5, 
          max: isHeat ? 65 : 20, 
          step: 1, 
          isShift: false 
        };
      } else {
        // Direct mode with room sensor: heat is 10..30, cool is 18..30
        return { 
          min: isHeat ? 10 : 18, 
          max: 30, 
          step: 1, 
          isShift: false 
        };
      }
    }
  }

  // Command submission with EEPROM rate limiting
  async function submitCommand(name, value, risky = false) {
    const now = Date.now();
    const oneHour = 60 * 60 * 1000;

    // EEPROM rate limiting: max 3 per 60 minutes
    if (now - eepromLast < oneHour && eepromCount >= 3) {
      const confirmed = await askConfirm({
        title: translate(lang, 'overview.eepromWarningTitle'),
        body: translate(lang, 'overview.eepromWarning'),
      });
      if (!confirmed) return;
      if (now - eepromLast >= oneHour) {
        eepromCount = 0;
        eepromLast = now;
      }
    }

    if (now - eepromLast >= oneHour) {
      eepromCount = 0;
      eepromLast = now;
    }

    const command = commandByName(name);
    if (!command) return;

    if (risky) {
      const confirmed = await askConfirm({
        title: translate(lang, 'common.confirmTitle'),
        body: `${translate(lang, 'common.confirmBody')}\n\n${name}`,
      });
      if (!confirmed) return;
    }

    const entry = { type: command.type, ...command };
    const validation = validate(entry, value, profile);
    if (!validation.ok) {
      console.warn(`Validation failed for ${name}: ${validation.error}`);
      return;
    }

    pendingCommands.add(name);
    pendingCommands = new Set(pendingCommands);
    try {
      const encoded = encode(command.type, value);
      if (!encoded.ok) {
        console.warn(`Encoding failed for ${name}: ${encoded.error}`);
        return;
      }

      await api.command({ name, value, confirm: true });
      eepromCount += 1;
    } finally {
      pendingCommands.delete(name);
      pendingCommands = new Set(pendingCommands);
    }
  }

  // Heat pump on/off
  const hpOn = $derived(getTopicValue('main/Operating_Mode_State') !== 0);

  // Operating mode options - use labels from common.*
  const modeOptions = $derived([
    { value: 0, label: translate(lang, 'common.mode0') },
    { value: 1, label: translate(lang, 'common.mode1') },
    { value: 2, label: translate(lang, 'common.mode2') },
    { value: 3, label: translate(lang, 'common.mode3') },
    { value: 4, label: translate(lang, 'common.mode4') },
    { value: 5, label: translate(lang, 'common.mode5') },
    { value: 6, label: translate(lang, 'common.mode6') },
  ]);

  let draftValues = $state({});

  function handleSliderInput(zone, isHeat, value) {
    draftValues[`${zone}_${isHeat ? 'heat' : 'cool'}`] = Number(value);
  }

  function handleSliderApply(zone, isHeat) {
    const key = `${zone}_${isHeat ? 'heat' : 'cool'}`;
    const value = draftValues[key];
    if (value === undefined) return;
    
    // Capitalize the zone identifier (z1 -> Z1)
    const zoneCapitalized = zone.toUpperCase();
    const cmdName = isHeat ? `Set${zoneCapitalized}HeatRequestTemperature` : `Set${zoneCapitalized}CoolRequestTemperature`;
    submitCommand(cmdName, value);
    const newDraft = { ...draftValues };
    delete newDraft[key];
    draftValues = newDraft;
  }

  // DHW setpoint range from catalog
  const dhwRange = $derived(getCommandRange('SetDHWTemp', profile));
  let dhwDraft = $state(null);

  function handleDhwApply() {
    if (dhwDraft === null) return;
    submitCommand('SetDHWTemp', dhwDraft);
    dhwDraft = null;
  }

  // Get current quiet/powerful mode values
  // Note: Quiet_Mode_Level and Powerful_Mode_Time are used as state indicators
  // Quiet mode is active when level > 0, Powerful mode when time > 0
  const quietOn = $derived(getTopicValue('main/Quiet_Mode_Level') !== 0);
  const powerfulOn = $derived(getTopicValue('main/Powerful_Mode_Time') !== 0);
</script>

<div class="quick-controls" data-testid="quick-controls">
  <h2>{translate(lang, 'overview.quickControls')}</h2>

  <section data-testid="control-hp-power">
    <label>
      <input
        type="checkbox"
        checked={hpOn}
        disabled={pendingCommands.has('SetOperationMode')}
        onchange={(e) => submitCommand('SetOperationMode', e.target.checked ? 4 : 0)}
      />
      {translate(lang, hpOn ? 'overview.heatPumpOff' : 'overview.heatPumpOn')}
    </label>
  </section>

  <section data-testid="control-mode">
    <label>
      {translate(lang, 'overview.operatingMode')}
      <select
        disabled={pendingCommands.has('SetOperationMode')}
        onchange={(e) => submitCommand('SetOperationMode', Number(e.target.value))}
      >
        {#each modeOptions as opt}
          <option value={opt.value} selected={getTopicValue('main/Operating_Mode_State') === opt.value}>
            {opt.label}
          </option>
        {/each}
      </select>
    </label>
  </section>

  <section data-testid="control-quiet-powerful">
    <label>
      <input
        type="checkbox"
        checked={quietOn}
        disabled={pendingCommands.has('SetQuietMode')}
        onchange={(e) => submitCommand('SetQuietMode', e.target.checked ? 1 : 0)}
      />
      {translate(lang, 'overview.quietMode')}
    </label>
    <label>
      <input
        type="checkbox"
        checked={powerfulOn}
        disabled={pendingCommands.has('SetPowerfulMode')}
        onchange={(e) => submitCommand('SetPowerfulMode', e.target.checked ? 1 : 0)}
      />
      {translate(lang, 'overview.powerfulMode')}
    </label>
  </section>

  {#if hasDhw}
    <section data-testid="control-force-dhw">
      <label>
        <input
          type="checkbox"
          disabled={!isDhwCapableMode() || pendingCommands.has('SetForceDHW')}
          onchange={(e) => submitCommand('SetForceDHW', e.target.checked ? 1 : 0)}
        />
        {translate(lang, 'overview.forceDhw')}
      </label>
    </section>
  {/if}

  {#if z1Active}
    <section data-testid="control-z1-heat">
      <label>
        {translate(lang, 'overview.heatRequest')} {translate(lang, 'zone1')}
        <input
          type="range"
          min={getZoneRequestRange('z1', true).min}
          max={getZoneRequestRange('z1', true).max}
          step={getZoneRequestRange('z1', true).step}
          value={draftValues.z1_heat ?? getTopicValue(`main/Z1_Heat_Request_Temperature`) ?? 0}
          oninput={(e) => handleSliderInput('z1', true, e.target.value)}
          data-testid="slider-z1-heat"
        />
        <span class="slider-value">
          {draftValues.z1_heat ?? getTopicValue(`main/Z1_Heat_Request_Temperature`) ?? 0}
          {getZoneRequestRange('z1', true).isShift ? translate(lang, 'unitCelsius') : ''}
        </span>
      </label>
      <ApplyButton testid="apply-z1-heat" disabled={pendingCommands.has('SetZ1HeatRequestTemperature')} onclick={() => handleSliderApply('z1', true)} />
    </section>
  {/if}

  {#if z1Active && coolingControl === 'curve'}
    <section data-testid="control-z1-cool">
      <label>
        {translate(lang, 'overview.coolRequest')} {translate(lang, 'zone1')}
        <input
          type="range"
          min={getZoneRequestRange('z1', false).min}
          max={getZoneRequestRange('z1', false).max}
          step={getZoneRequestRange('z1', false).step}
          value={draftValues.z1_cool ?? getTopicValue(`main/Z1_Cool_Request_Temperature`) ?? 0}
          oninput={(e) => handleSliderInput('z1', false, e.target.value)}
          data-testid="slider-z1-cool"
        />
        <span class="slider-value">
          {draftValues.z1_cool ?? getTopicValue(`main/Z1_Cool_Request_Temperature`) ?? 0}
        </span>
      </label>
      <ApplyButton testid="apply-z1-cool" disabled={pendingCommands.has('SetZ1CoolRequestTemperature')} onclick={() => handleSliderApply('z1', false)} />
    </section>
  {/if}

  {#if z2Active}
    <section data-testid="control-z2-heat">
      <label>
        {translate(lang, 'overview.heatRequest')} {translate(lang, 'zone2')}
        <input
          type="range"
          min={getZoneRequestRange('z2', true).min}
          max={getZoneRequestRange('z2', true).max}
          step={getZoneRequestRange('z2', true).step}
          value={draftValues.z2_heat ?? getTopicValue(`main/Z2_Heat_Request_Temperature`) ?? 0}
          oninput={(e) => handleSliderInput('z2', true, e.target.value)}
          data-testid="slider-z2-heat"
        />
        <span class="slider-value">
          {draftValues.z2_heat ?? getTopicValue(`main/Z2_Heat_Request_Temperature`) ?? 0}
          {getZoneRequestRange('z2', true).isShift ? translate(lang, 'unitCelsius') : ''}
        </span>
      </label>
      <ApplyButton testid="apply-z2-heat" disabled={pendingCommands.has('SetZ2HeatRequestTemperature')} onclick={() => handleSliderApply('z2', true)} />
    </section>
  {/if}

  {#if hasDhw}
    <section data-testid="control-dhw-setpoint">
      <label>
        {translate(lang, 'overview.dhwSetpoint')}
        <input
          type="number"
          min={dhwRange.min}
          max={dhwRange.max}
          step={dhwRange.step}
          value={dhwDraft ?? getTopicValue('main/DHW_Temp_Setpoint') ?? 50}
          oninput={(e) => { dhwDraft = Number(e.target.value); }}
          data-testid="input-dhw"
        />
      </label>
      <ApplyButton testid="apply-dhw" disabled={pendingCommands.has('SetDHWTemp')} onclick={handleDhwApply} />
    </section>
  {/if}
</div>

<style>
  .quick-controls {
    background: #1a1a1a;
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1rem;
    color: #e5e5e5;
  }
  h2 {
    margin: 0 0 1rem;
    font-size: 1rem;
    color: #ccc;
  }
  section {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    margin-bottom: 0.75rem;
    align-items: center;
  }
  label {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: 0.875rem;
    min-width: 120px;
  }
  input[type="range"] {
    width: 100%;
  }
  .slider-value {
    font-size: 0.75rem;
    color: #888;
    text-align: center;
    display: block;
  }
  input[type="number"] {
    width: 60px;
    padding: 0.25rem;
    border-radius: 4px;
    border: 1px solid #444;
    background: #2a2a2a;
    color: #e5e5e5;
  }
  input[type="checkbox"] {
    margin-right: 0.5rem;
  }
  select {
    padding: 0.25rem;
    border-radius: 4px;
    border: 1px solid #444;
    background: #2a2a2a;
    color: #e5e5e5;
  }
</style>
