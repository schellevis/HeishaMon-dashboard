<script>
  import { onMount, untrack } from 'svelte';
  import ApplyResult from '../components/curve/ApplyResult.svelte';
  import ChangeLog from '../components/curve/ChangeLog.svelte';
  import CurveChart from '../components/curve/CurveChart.svelte';
  import CurveEditor from '../components/curve/CurveEditor.svelte';
  import DraftPanel from '../components/curve/DraftPanel.svelte';
  import OverlayPanel from '../components/curve/OverlayPanel.svelte';
  import { api } from '../lib/api.js';
  import {
    MODE_SETS,
    SHIFT_RANGE,
    THRESHOLDS,
    applyLeaves,
    curvePoints,
    diffRows,
    isCoupled,
    leafKey,
    leavesOfJson,
    modelDisagrees,
    modelTarget,
    setcurvesDiff,
    zoneNum,
  } from '../lib/curvegeom.js';
  import { translate } from '../lib/i18n/index.js';
  import { askConfirm, commands, language, profile, state as appState } from '../lib/stores.js';

  const TABS = [
    { id: 'z1heat', zone: 'z1', mode: 'heat', label: 'tabZ1Heat' },
    { id: 'z1cool', zone: 'z1', mode: 'cool', label: 'tabZ1Cool' },
    { id: 'z2heat', zone: 'z2', mode: 'heat', label: 'tabZ2Heat' },
    { id: 'z2cool', zone: 'z2', mode: 'cool', label: 'tabZ2Cool' },
  ];
  const AUTO_MODES = [2, 6, 7, 8];
  const DAY = 86_400_000;

  const lang = $derived($language);
  const t = (key, params) => translate(lang, `curve.${key}`, params);

  // ---- tab selection: the tab matching the operating mode opens by default
  let userTab = $state(null);
  const defaultTab = $derived.by(() => {
    const zones = $profile?.zones?.value;
    const mode = $profile?.operating_mode?.value;
    const zone = zones === 'z2' ? 'z2' : 'z1';
    const cool = mode !== undefined && mode !== null && MODE_SETS.cool.includes(mode) && !MODE_SETS.heat.includes(mode);
    return `${zone}${cool ? 'cool' : 'heat'}`;
  });
  const tab = $derived(TABS.find((x) => x.id === (userTab ?? defaultTab)) ?? TABS[0]);

  function tabInactive(x) {
    const p = $profile;
    if (!p) return false;
    const zones = p.zones?.value;
    const zoneOff = (zones === 'z1' && x.zone === 'z2') || (zones === 'z2' && x.zone === 'z1');
    const inUse = x.mode === 'heat' ? p.heating_in_use?.value : p.cooling_in_use?.value;
    return zoneOff || inUse === false;
  }

  // ---- values from state
  const topics = $derived($appState?.topics ?? {});
  const num = (key) => {
    const v = topics[key]?.value;
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
  };
  const zn = $derived(zoneNum(tab.zone));
  const Mode = $derived(tab.mode === 'heat' ? 'Heat' : 'Cool');
  const current = $derived.by(() => {
    const values = {};
    for (const [k, v] of Object.entries(topics)) if (k.includes('_Curve_')) values[k] = v?.value;
    return curvePoints(values, tab.zone, tab.mode);
  });

  // ---- control mode, sensor
  const control = $derived(tab.mode === 'heat' ? $profile?.heating_control?.value : $profile?.cooling_control?.value);
  const direct = $derived(control === 'direct');
  const sensor = $derived($profile?.zone?.[tab.zone]?.sensor?.value ?? null);
  const coupled = $derived(isCoupled($profile, tab.zone, tab.mode));
  const requestKey = $derived(`main/Z${zn}_${Mode}_Request_Temp`);
  const requestValue = $derived(num(requestKey));
  const requestCommand = $derived(`SetZ${zn}${Mode}RequestTemperature`);

  // ---- drafts
  let drafts = $state({});
  let shiftDrafts = $state({});
  let thresholdDrafts = $state({ heaterOn: null, heatingOff: null });
  const draft = $derived(drafts[tab.id] ?? null);
  const shown = $derived(draft ?? current);
  const curveRows = $derived(current && draft ? diffRows(current, draft, tab.zone, tab.mode) : []);
  const shiftDraft = $derived(shiftDrafts[tab.id] ?? null);
  const shift = $derived(shiftDraft ?? requestValue ?? 0);

  const thresholdValue = (name) => thresholdDrafts[name] ?? num(THRESHOLDS[name].key);
  const thresholdView = $derived(
    tab.mode === 'heat'
      ? { heaterOn: { value: thresholdValue('heaterOn') }, heatingOff: { value: thresholdValue('heatingOff') } }
      : null,
  );
  const thresholdRows = (name) => {
    const d = thresholdDrafts[name];
    const cur = num(THRESHOLDS[name].key);
    return d !== null && d !== cur ? [{ key: THRESHOLDS[name].key.replace('main/', ''), from: cur ?? '–', to: d }] : [];
  };
  const shiftRows = $derived(
    shiftDraft !== null && shiftDraft !== requestValue
      ? [{ key: requestKey.replace('main/', ''), from: requestValue ?? '–', to: shiftDraft }]
      : [],
  );

  const autoMode = $derived(AUTO_MODES.includes($profile?.operating_mode?.value));
  const switchMarkers = $derived(
    autoMode ? { heatToCool: num('main/Heat_To_Cool_Temp'), coolToHeat: num('main/Cool_To_Heat_Temp') } : null,
  );

  // ---- live markers and model warning
  const outsideNow = $derived(num('main/Outside_Temp'));
  const reportedTarget = $derived(num(`main/Z${zn}_Water_Target_Temp`));
  const ownWater = $derived(sensor === 'water' && num(`main/Z${zn}_Water_Temp`) !== null);
  const actualWater = $derived(ownWater ? num(`main/Z${zn}_Water_Temp`) : num('main/Main_Outlet_Temp'));
  const warn = $derived(
    !direct && current && outsideNow !== null && reportedTarget !== null
      ? modelDisagrees(current, requestValue ?? 0, outsideNow, reportedTarget)
      : false,
  );
  const modelValue = $derived(current && outsideNow !== null ? modelTarget(current, requestValue ?? 0, outsideNow) : null);
  const directSetpoint = $derived(direct ? (coupled ? (shown?.cold.target ?? null) : requestValue) : null);

  // ---- commands
  let results = $state({});

  function recentChanges(name) {
    const since = Date.now() - 3_600_000;
    return Object.values($commands).filter(
      (c) => c.name === name && ['confirmed', 'retried', 'failed'].includes(c.status) && c.submitted_ts >= since,
    ).length;
  }

  async function submit(group, name, value, changes) {
    const ok = await askConfirm({ title: t('confirmTitle'), body: t('confirmBody', { command: name, changes }) });
    if (!ok) return;
    try {
      const cmd = await api.command({ name, value, confirm: false });
      commands.update((m) => ({ ...m, [cmd.id]: cmd }));
      results[group] = { id: cmd.id, command: cmd, error: null };
      return cmd;
    } catch (e) {
      results[group] = { id: null, command: null, error: e?.code ?? 'error' };
    }
  }

  async function applyCurve() {
    if (!current || !draft) return;
    const diff = setcurvesDiff(current, draft, tab.zone, tab.mode);
    if (!Object.keys(diff.keys).length) return;
    const cmd = await submit('curve', 'SetCurves', diff.json, JSON.stringify(diff.keys));
    if (cmd) sessionPrev[cmd.id] = previousLeaves(diff.keys, current);
  }

  // session-only memory of the values an applied change replaced (used by revert)
  let sessionPrev = $state({});
  function previousLeaves(keys, curve) {
    const out = {};
    for (const end of ['cold', 'warm']) {
      for (const field of ['outside', 'target']) {
        const k = leafKey(tab.zone, tab.mode, end, field);
        if (k in keys) out[k] = curve[end][field];
      }
    }
    return out;
  }

  function applyThreshold(name) {
    const value = thresholdDrafts[name];
    if (value === null) return;
    return submit(name, THRESHOLDS[name].command, value, `${THRESHOLDS[name].command}=${value}`);
  }

  function applyShift() {
    if (shiftDraft === null) return;
    return submit('shift', requestCommand, shiftDraft, `${requestCommand}=${shiftDraft}`);
  }

  function stepShift(delta) {
    const next = Math.min(SHIFT_RANGE.max, Math.max(SHIFT_RANGE.min, (shiftDraft ?? requestValue ?? 0) + delta));
    shiftDrafts = { ...shiftDrafts, [tab.id]: next };
  }

  function discard() {
    drafts = { ...drafts, [tab.id]: null };
    shiftDrafts = { ...shiftDrafts, [tab.id]: null };
    thresholdDrafts = { heaterOn: null, heatingOff: null };
  }

  const groups = $derived([
    {
      id: 'curve',
      label: t('groupSetCurves'),
      rows: curveRows.map((r) => ({ key: r.key, from: r.from, to: r.to })),
      applyLabel: t('applyCurve'),
      onapply: applyCurve,
    },
    ...(tab.mode === 'heat'
      ? [
          {
            id: 'heaterOn',
            label: t('groupHeaterOn'),
            rows: thresholdRows('heaterOn'),
            applyLabel: t('applyHeaterOn'),
            onapply: () => applyThreshold('heaterOn'),
          },
          {
            id: 'heatingOff',
            label: t('groupHeatingOff'),
            rows: thresholdRows('heatingOff'),
            applyLabel: t('applyHeatingOff'),
            onapply: () => applyThreshold('heatingOff'),
          },
        ]
      : []),
    {
      id: 'shift',
      label: t('groupShift'),
      rows: shiftRows,
      applyLabel: t('applyShift'),
      onapply: applyShift,
    },
  ]);
  const eepromWarning = $derived(recentChanges('SetCurves') >= 3);

  const resultFor = (group) => {
    const r = results[group];
    if (!r) return null;
    return { error: r.error, command: (r.id && $commands[r.id]) || r.command };
  };

  // ---- change log with revert
  let revertNotice = $state(null);
  const logEntries = $derived.by(() => {
    const parsed = [];
    for (const c of Object.values($commands)) {
      if (c.name !== 'SetCurves') continue;
      let leaves = {};
      try {
        leaves = leavesOfJson(JSON.parse(c.payload));
      } catch {
        continue;
      }
      const own = Object.fromEntries(Object.entries(leaves).filter(([k]) => k.startsWith(`Z${zn}_${Mode}_Curve_`)));
      if (Object.keys(own).length) parsed.push({ c, own });
    }
    parsed.sort((a, b) => b.c.submitted_ts - a.c.submitted_ts);
    return parsed.map(({ c, own }, i) => {
      const previous = {};
      for (const k of Object.keys(own)) {
        const older = parsed.slice(i + 1).find((p) => k in p.own && ['confirmed', 'retried'].includes(p.c.status));
        previous[k] = older ? older.own[k] : sessionPrev[c.id]?.[k];
      }
      const canRevert = Object.values(previous).every((v) => typeof v === 'number');
      return {
        id: c.id,
        ts: c.submitted_ts,
        status: c.status,
        summary: Object.entries(own).map(([k, v]) => `${k.replace(/^Z\d_(Heat|Cool)_Curve_/, '').replace(/_Temp$/, '')}=${v}`).join(', '),
        canRevert: canRevert && !!current,
        onrevert: () => {
          drafts = { ...drafts, [tab.id]: applyLeaves(current, previous, tab.zone, tab.mode) };
          revertNotice = t('revertLoaded');
        },
      };
    });
  });

  // ---- overlay
  let range = $state('14');
  let customFrom = $state('');
  let customTo = $state('');
  let colorBy = $state('water_minus_target');
  let overlayData = $state(null);
  let overlayLoading = $state(false);
  let overlayError = $state(null);
  let overlayToken = 0;

  function overlayWindow() {
    if (range === 'custom') {
      const from = Date.parse(customFrom);
      const to = Date.parse(customTo);
      if (!Number.isFinite(from) || !Number.isFinite(to) || to <= from) return null;
      return { from, to: to + DAY };
    }
    const to = Date.now();
    return { from: to - Number(range) * DAY, to };
  }

  async function loadOverlay(zone, mode) {
    const win = overlayWindow();
    const token = ++overlayToken;
    if (!win) {
      overlayData = null;
      return;
    }
    overlayLoading = true;
    overlayError = null;
    try {
      const data = await api.overlay({ zone, mode, from: win.from, to: win.to });
      if (token !== overlayToken) return;
      overlayData = data;
    } catch (e) {
      if (token !== overlayToken) return;
      overlayData = null;
      overlayError = e?.code ?? 'error';
    } finally {
      if (token === overlayToken) overlayLoading = false;
    }
  }

  $effect(() => {
    const zone = tab.zone;
    const mode = tab.mode;
    void range;
    void customFrom;
    void customTo;
    untrack(() => loadOverlay(zone, mode));
  });

  $effect(() => {
    // fall back to the default colouring when the chosen one is not offered for this data
    const windows = overlayData?.windows ?? [];
    if (colorBy === 'side' && !windows.some((w) => w.side)) colorBy = 'water_minus_target';
    if (colorBy === 'room_minus_setpoint' && !windows.some((w) => w.room_minus_setpoint != null)) colorBy = 'water_minus_target';
  });

  onMount(async () => {
    if (import.meta.env.MODE === 'test') return;
    try {
      const { commands: list } = await api.commands({ limit: 200 });
      commands.update((m) => ({ ...Object.fromEntries(list.map((c) => [c.id, c])), ...m }));
    } catch {
      // the log stays empty until the next successful load
    }
  });

  function setDraft(next) {
    drafts = { ...drafts, [tab.id]: next };
  }
  function setThreshold(name, value) {
    thresholdDrafts = { ...thresholdDrafts, [name]: value };
  }
  const editable = $derived(!!current);
</script>

<section data-testid="screen-curve" class="curve-screen">
  <h2>{t('title')}</h2>

  <div role="tablist" aria-label={t('tabsLabel')}>
    {#each TABS as x (x.id)}
      <button
        type="button"
        role="tab"
        data-testid="tab-{x.id}"
        aria-selected={x.id === tab.id}
        class:inactive={tabInactive(x)}
        onclick={() => (userTab = x.id)}
      >
        {t(x.label)}{#if tabInactive(x)} <small>({t('inactive')})</small>{/if}
      </button>
    {/each}
  </div>

  <p class="badge" data-testid="mode-badge" data-control={control ?? 'unknown'}>
    {direct ? t('badgeDirect') : t('badgeCurve')}
    {#if direct && !coupled}<strong data-testid="not-active"> · {t('notActive')}</strong>{/if}
  </p>
  {#if direct && !coupled}<p class="hint" data-testid="not-active-hint">{t('notActiveHint')}</p>{/if}
  {#if coupled}
    <p class="hint" data-testid="coupled-hint">{t('coupledHint')} {t('setpoint')}: {shown?.cold.target ?? '–'} °C</p>
  {/if}

  {#if !current}
    <p data-testid="no-curve-data">{t('noData')}</p>
  {/if}

  {#if warn}
    <p role="alert" data-testid="model-warning">
      {t('modelWarning', { model: modelValue?.toFixed(1), reported: reportedTarget })}
    </p>
  {/if}

  <CurveChart
    {lang}
    mode={tab.mode}
    {current}
    draft={draft ?? null}
    {shift}
    showShift={!direct}
    {directSetpoint}
    {editable}
    outside={outsideNow}
    {reportedTarget}
    {actualWater}
    thresholds={thresholdView}
    {switchMarkers}
    overlay={overlayData}
    {colorBy}
    {coupled}
    onchange={setDraft}
    onthreshold={setThreshold}
  />
  <p class="hint" data-testid="assumption-note">{t('assumptionNote')}</p>

  {#if !direct}
    <div class="shift" data-testid="shift-control">
      <span>{t('shift')}: <output data-testid="shift-value">{shift}</output></span>
      <button type="button" data-testid="shift-minus" aria-label={t('shiftMinus')} disabled={shift <= SHIFT_RANGE.min} onclick={() => stepShift(-1)}>−</button>
      <button type="button" data-testid="shift-plus" aria-label={t('shiftPlus')} disabled={shift >= SHIFT_RANGE.max} onclick={() => stepShift(1)}>+</button>
    </div>
  {/if}

  <CurveEditor {lang} mode={tab.mode} {shown} {coupled} onchange={setDraft} />

  <DraftPanel {lang} {groups} ondiscard={discard} {eepromWarning} />
  {#each groups as g (g.id)}
    <ApplyResult {lang} id={g.id} result={resultFor(g.id)} />
  {/each}

  <ChangeLog {lang} entries={logEntries} notice={revertNotice} />

  <OverlayPanel
    {lang}
    data={overlayData}
    loading={overlayLoading}
    error={overlayError}
    {range}
    {colorBy}
    from={customFrom}
    to={customTo}
    onrange={(r) => (range = r)}
    oncolor={(c) => (colorBy = c)}
    oncustom={(f, to) => {
      customFrom = f;
      customTo = to;
    }}
  />
</section>
