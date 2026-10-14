import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { tick } from 'svelte';
import { get } from 'svelte/store';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import Curve from '../src/features/curve/CurveScreen.svelte';
import CurveChart from '../src/features/curve/CurveChart.svelte';
import { api } from '../src/lib/api.js';
import {
  answerConfirm,
  commands,
  confirmRequest,
  language,
  profile,
  resetClientState,
  state,
} from '../src/lib/stores.js';
import {
  curveLine,
  curvePoints,
  isCoupled,
  levelStep,
  modelDisagrees,
  modelTarget,
  moveHandle,
  setcurvesDiff,
  slopeStep,
  validateDraft,
  makeScale,
  X_RANGE,
  Y_RANGE,
} from '../src/lib/curvegeom.js';
import en from '../src/lib/i18n/curve.en.js';
import nl from '../src/lib/i18n/curve.nl.js';

const curve = (co, ct, wo, wt) => ({ cold: { outside: co, target: ct }, warm: { outside: wo, target: wt } });

// ---------------------------------------------------------------- geometry (same cases as backend test_curve.py)
describe('curvegeom mirrors the backend maths', () => {
  it('maps the crosswise naming', () => {
    const vals = {
      'main/Z2_Heat_Curve_Target_High_Temp': 45,
      'main/Z2_Heat_Curve_Target_Low_Temp': 30,
      'main/Z2_Heat_Curve_Outside_High_Temp': 15,
      'main/Z2_Heat_Curve_Outside_Low_Temp': -5,
      'main/Z2_Cool_Curve_Target_High_Temp': 1,
    };
    expect(curvePoints(vals, 'z2', 'heat')).toEqual(curve(-5, 45, 15, 30));
    expect(curvePoints(vals, 'z1', 'heat')).toBeNull();
    expect(curvePoints(vals, 'z2', 'cool')).toBeNull();
  });

  it('model target is flat beyond the ends and adds the shift', () => {
    const c = curve(-10, 50, 10, 30);
    expect(modelTarget(c, 0, -20)).toBe(50);
    expect(modelTarget(c, 0, 20)).toBe(30);
    expect(modelTarget(c, 0, 0)).toBe(40);
    expect(modelTarget(c, 2, 0)).toBe(42);
  });

  it('warns only above 1 °C', () => {
    const c = curve(-10, 50, 10, 30);
    expect(modelDisagrees(c, 0, 0, 41)).toBe(false);
    expect(modelDisagrees(c, 0, 0, 41.5)).toBe(true);
    expect(modelDisagrees(c, 0, 0, 38.5)).toBe(true);
  });

  it('ordering invariant and limits', () => {
    expect(validateDraft(curve(-5, 40, 15, 40), 'heat')).toEqual([]);
    expect(validateDraft(curve(5, 40, 5, 30), 'heat')).toEqual(['outside_order']);
    expect(validateDraft(curve(-5, 30, 15, 31), 'heat')).toEqual(['target_order']);
    expect(validateDraft(curve(-5, 76, 15, 30), 'heat')).toContain('limit:cold.target');
    expect(validateDraft(curve(-5, 40, 31, 30), 'heat')).toContain('limit:warm.outside');
    expect(validateDraft(curve(16, 20, 30, 5), 'cool')).toEqual([]);
    expect(validateDraft(curve(14, 20, 30, 5), 'cool')).toContain('limit:cold.outside');
    expect(validateDraft(curve(16, 21, 30, 5), 'cool')).toContain('limit:cold.target');
  });

  it('slope and level steps are refused as a whole', () => {
    const c = curve(-5, 75, 15, 30);
    expect(slopeStep(c, 'heat', 1)).toBeNull();
    expect(slopeStep(c, 'heat', -1)).toEqual(curve(-5, 74, 15, 31));
    const low = curve(-5, 40, 15, 15);
    expect(levelStep(low, 'heat', -1)).toBeNull();
    expect(levelStep(low, 'heat', 1)).toEqual(curve(-5, 41, 15, 16));
    const flat = curve(-5, 40, 15, 40);
    expect(slopeStep(flat, 'heat', -1)).toBeNull();
    expect(slopeStep(flat, 'heat', 1)).toEqual(curve(-5, 41, 15, 39));
  });

  it('diff contains only changed keys', () => {
    const cur = curve(-5, 45, 15, 30);
    const d = setcurvesDiff(cur, curve(-5, 47, 15, 28), 'z1', 'heat');
    expect(d.json).toEqual({ zone1: { heat: { target: { high: 47, low: 28 } } } });
    expect(d.keys).toEqual({ Z1_Heat_Curve_Target_High_Temp: 47, Z1_Heat_Curve_Target_Low_Temp: 28 });
    const e = setcurvesDiff(cur, curve(-6, 45, 15, 30), 'z2', 'cool');
    expect(e.json).toEqual({ zone2: { cool: { outside: { low: -6 } } } });
    expect(setcurvesDiff(cur, cur)).toEqual({ json: {}, keys: {} });
  });

  it('a drag stops at the last valid integer', () => {
    const c = curve(-5, 45, 15, 30);
    expect(moveHandle(c, 'heat', 'cold', 'outside', 40).cold.outside).toBe(14);
    expect(moveHandle(c, 'heat', 'warm', 'outside', -30).warm.outside).toBe(-4);
    expect(moveHandle(c, 'heat', 'warm', 'target', 60).warm.target).toBe(45);
    expect(moveHandle(c, 'heat', 'cold', 'target', 10).cold.target).toBe(30);
    expect(moveHandle(c, 'heat', 'cold', 'target', 99).cold.target).toBe(75);
    expect(moveHandle(c, 'heat', 'cold', 'outside', -40).cold.outside).toBe(-20);
    expect(moveHandle(c, 'heat', 'cold', 'target', 44.6).cold.target).toBe(45);
    expect(moveHandle(curve(16, 20, 30, 5), 'cool', 'warm', 'outside', 99).warm.outside).toBe(30);
  });

  it('coupled mode drops only the target-ordering rule', () => {
    // live state seen on a direct-mode installation with a room thermostat: cold target 20 < warm 30
    const live = curve(-5, 20, 15, 30);
    expect(validateDraft(live, 'heat')).toEqual(['target_order']);
    expect(validateDraft(live, 'heat', { coupled: true })).toEqual([]);
    expect(validateDraft(curve(5, 20, 5, 30), 'heat', { coupled: true })).toEqual(['outside_order']);
    expect(validateDraft(curve(-5, 14, 15, 30), 'heat', { coupled: true })).toContain('limit:cold.target');
    expect(validateDraft(curve(16, 5, 30, 20), 'cool', { coupled: true })).toEqual([]);
  });

  it('coupled mode lets the cold-end target move below the warm-end target', () => {
    const c = curve(-5, 28, 15, 30);
    expect(moveHandle(c, 'heat', 'cold', 'target', 20).cold.target).toBe(30);
    expect(moveHandle(c, 'heat', 'cold', 'target', 20, { coupled: true }).cold.target).toBe(20);
    expect(moveHandle(c, 'heat', 'cold', 'target', 10, { coupled: true }).cold.target).toBe(15);
    expect(moveHandle(c, 'heat', 'warm', 'target', 60, { coupled: true }).warm.target).toBe(60);
    expect(moveHandle(c, 'heat', 'cold', 'outside', 40, { coupled: true }).cold.outside).toBe(14);
    expect(levelStep(c, 'heat', -1)).toBeNull();
    expect(levelStep(c, 'heat', -1, { coupled: true })).toEqual(curve(-5, 27, 15, 29));
    expect(slopeStep(c, 'heat', -1, { coupled: true })).toEqual(curve(-5, 27, 15, 31));
  });

  it('isCoupled: direct control with a room sensor, per zone and mode', () => {
    const G = (value, unknown = false, stale = false) => ({ value, unknown, stale });
    const p = (heat, cool, s1, s2 = 'water') => ({
      heating_control: G(heat), cooling_control: G(cool),
      zone: { z1: { sensor: G(s1) }, z2: { sensor: G(s2) } },
    });
    for (const s of ['ext_thermostat', 'int_thermostat', 'thermistor']) expect(isCoupled(p('direct', 'curve', s), 'z1', 'heat')).toBe(true);
    expect(isCoupled(p('direct', 'curve', 'water'), 'z1', 'heat')).toBe(false);
    expect(isCoupled(p('curve', 'curve', 'ext_thermostat'), 'z1', 'heat')).toBe(false);
    expect(isCoupled(p('direct', 'curve', 'ext_thermostat'), 'z1', 'cool')).toBe(false);
    expect(isCoupled(p('curve', 'direct', 'thermistor'), 'z1', 'cool')).toBe(true);
    expect(isCoupled(p('direct', 'curve', 'water', 'ext_thermostat'), 'z2', 'heat')).toBe(true);
    expect(isCoupled(p('direct', 'curve', 'water', 'ext_thermostat'), 'z1', 'heat')).toBe(false);
    const unknown = p('direct', 'curve', 'ext_thermostat');
    unknown.zone.z1.sensor = G(null, true);
    expect(isCoupled(unknown, 'z1', 'heat')).toBe(false);
    expect(isCoupled(null, 'z1', 'heat')).toBe(false);
  });

  it('draws the line flat beyond both ends', () => {
    expect(curveLine(curve(-5, 45, 15, 30), 2, [-25, 35])).toEqual([[-25, 47], [-5, 47], [15, 32], [35, 32]]);
  });
});

// ---------------------------------------------------------------- wording
describe('strings', () => {
  it('use cold/warm end wording only, never high/low', () => {
    for (const table of [en, nl]) {
      for (const [key, value] of Object.entries(table)) {
        expect(`${key} ${value}`).not.toMatch(/\b(high|low|hoog|laag)\b/i);
      }
    }
    expect(en.coldEnd).toBe('Cold end');
    expect(en.warmEnd).toBe('Warm end');
    expect(nl.coldEnd).toBe('Koude kant');
    expect(nl.warmEnd).toBe('Warme kant');
    expect(Object.keys(en).sort()).toEqual(Object.keys(nl).sort());
  });
});

// ---------------------------------------------------------------- chart component
function mockRect() {
  const spy = vi
    .spyOn(Element.prototype, 'getBoundingClientRect')
    .mockReturnValue({ left: 0, top: 0, width: 640, height: 360, right: 640, bottom: 360, x: 0, y: 0 });
  return spy;
}

function pointer(el, type, x, y) {
  el.dispatchEvent(new MouseEvent(type, { clientX: x, clientY: y, bubbles: true }));
}

describe('CurveChart', () => {
  afterEach(() => vi.restoreAllMocks());

  it('marks a moved handle with the draft class', () => {
    render(CurveChart, { props: { mode: 'heat', current: curve(-5, 45, 15, 30), draft: curve(-5, 50, 15, 30) } });
    expect(screen.getByTestId('handle-cold').classList.contains('changed')).toBe(true);
    expect(screen.getByTestId('handle-warm').classList.contains('changed')).toBe(false);
  });

  it('dragging a handle past the other end stops at the invariant', async () => {
    mockRect();
    const onchange = vi.fn();
    const c = curve(-5, 45, 15, 30);
    render(CurveChart, { props: { mode: 'heat', current: c, draft: null, onchange } });
    const sx = makeScale(X_RANGE.heat, [44, 640 - 14]);
    const sy = makeScale(Y_RANGE.heat, [360 - 34, 12]);
    pointer(screen.getByTestId('handle-cold'), 'pointerdown', sx(-5), sy(45));
    pointer(screen.getByTestId('curve-chart'), 'pointermove', sx(33), sy(20));
    expect(onchange).toHaveBeenCalledTimes(1);
    expect(onchange.mock.calls[0][0]).toEqual(curve(14, 30, 15, 30));
    pointer(screen.getByTestId('curve-chart'), 'pointerup', 0, 0);
    pointer(screen.getByTestId('curve-chart'), 'pointermove', sx(0), sy(50));
    expect(onchange).toHaveBeenCalledTimes(1);
  });

  it('keyboard arrows move a handle by 1 °C and respect the invariant', async () => {
    const onchange = vi.fn();
    render(CurveChart, { props: { mode: 'heat', current: curve(-5, 45, 15, 45), draft: null, onchange } });
    await fireEvent.keyDown(screen.getByTestId('handle-cold'), { key: 'ArrowDown' });
    expect(onchange).not.toHaveBeenCalledWith(expect.objectContaining({ cold: { outside: -5, target: 44 } }));
    await fireEvent.keyDown(screen.getByTestId('handle-cold'), { key: 'ArrowUp' });
    expect(onchange.mock.calls.at(-1)[0].cold.target).toBe(46);
  });

  it('renders ghost, shift line, direct line, markers and live points', () => {
    const c = curve(-5, 45, 15, 30);
    const { unmount } = render(CurveChart, {
      props: {
        mode: 'heat',
        current: c,
        draft: curve(-5, 47, 15, 30),
        shift: 2,
        showShift: true,
        outside: 3,
        reportedTarget: 40,
        actualWater: 38,
        thresholds: { heaterOn: { value: -2 }, heatingOff: { value: 17 } },
      },
    });
    expect(screen.getByTestId('ghost-line')).toBeTruthy();
    expect(screen.getByTestId('shift-line')).toBeTruthy();
    expect(screen.getByTestId('marker-heaterOn')).toBeTruthy();
    expect(screen.getByTestId('marker-heatingOff')).toBeTruthy();
    expect(screen.getByTestId('live-target')).toBeTruthy();
    expect(screen.getByTestId('live-water')).toBeTruthy();
    unmount();
    render(CurveChart, {
      props: { mode: 'heat', current: c, directSetpoint: 35, switchMarkers: { heatToCool: 22, coolToHeat: 18 } },
    });
    expect(screen.getByTestId('direct-line')).toBeTruthy();
    expect(screen.queryByTestId('shift-line')).toBeNull();
    expect(screen.getByTestId('switch-heatToCool').textContent).toContain('22');
    expect(screen.getByTestId('switch-coolToHeat').textContent).toContain('18');
    expect(screen.queryByTestId('marker-heaterOn')).toBeNull();
  });
});

// ---------------------------------------------------------------- screen
const F = (value) => ({ value, unknown: value === null, stale: false });
function makeProfile(over = {}) {
  return {
    computed_at: 1,
    operating_mode: F(0),
    heating_in_use: F(true),
    cooling_in_use: F(false),
    dhw_in_use: F(false),
    zones: F('z1'),
    heating_control: F('curve'),
    cooling_control: F('curve'),
    zone: {
      z1: { active: F(true), sensor: F('water') },
      z2: { active: F(false), sensor: F('water') },
    },
    ...over,
  };
}
function tv(value) {
  return { value, raw: String(value), kind: 'number', unit: null, decimals: null, enum_label: null, catalogued: true, sentinel: false, last_change: 1, last_seen: 1, retained_only: false };
}
function makeState(extra = {}) {
  const values = {
    'main/Z1_Heat_Curve_Target_High_Temp': 45,
    'main/Z1_Heat_Curve_Target_Low_Temp': 30,
    'main/Z1_Heat_Curve_Outside_High_Temp': 15,
    'main/Z1_Heat_Curve_Outside_Low_Temp': -5,
    'main/Z1_Cool_Curve_Target_High_Temp': 18,
    'main/Z1_Cool_Curve_Target_Low_Temp': 10,
    'main/Z1_Cool_Curve_Outside_High_Temp': 30,
    'main/Z1_Cool_Curve_Outside_Low_Temp': 20,
    'main/Outside_Temp': 5,
    'main/Z1_Water_Target_Temp': 38,
    'main/Main_Outlet_Temp': 37,
    'main/Z1_Heat_Request_Temp': 0,
    'main/Heater_On_Outdoor_Temp': -2,
    'main/Heating_Off_Outdoor_Temp': 17,
    ...extra,
  };
  return {
    seq: 1,
    topics: Object.fromEntries(Object.entries(values).map(([k, v]) => [k, tv(v)])),
    device_online: 'online',
    last_device_message: 1,
    broker_connected: true,
    listen_only_suspected: false,
  };
}

const overlayFixture = {
  zone: 'z1',
  mode: 'heat',
  boundary_ts: null,
  windows: [
    { start_ts: 1, outside: 2, water: 35, target: 34, water_minus_target: 1, cop: 4, freq: 40, room_minus_setpoint: null, side: null, eligible_minutes: 15 },
    { start_ts: 2, outside: 6, water: 30, target: 30, water_minus_target: 0, cop: null, freq: 30, room_minus_setpoint: null, side: null, eligible_minutes: 13 },
  ],
  median: [{ band_lo: 2, value: 35, n: 3 }],
  histogram: [{ band_lo: 2, hours: 0.5 }, { band_lo: 6, hours: 0.25 }],
};

async function confirmNext(accepted = true) {
  await waitFor(() => expect(get(confirmRequest)).not.toBeNull());
  answerConfirm(accepted);
  await tick();
}

function mount(opts = {}) {
  state.set(opts.state ?? makeState());
  profile.set(opts.profile ?? makeProfile());
  return render(Curve);
}

describe('Curve screen', () => {
  beforeEach(() => {
    resetClientState();
    language.set('en');
    vi.spyOn(api, 'overlay').mockResolvedValue(overlayFixture);
  });
  afterEach(() => vi.restoreAllMocks());

  it('opens the tab matching the operating mode and keeps all four reachable', async () => {
    mount();
    expect(screen.getByTestId('tab-z1heat').getAttribute('aria-selected')).toBe('true');
    expect(screen.getByTestId('tab-z1cool').className).toContain('inactive');
    expect(screen.getByTestId('tab-z2heat').className).toContain('inactive');
    await fireEvent.click(screen.getByTestId('tab-z2cool'));
    expect(screen.getByTestId('tab-z2cool').getAttribute('aria-selected')).toBe('true');
  });

  it('opens a cool tab in a cooling mode', () => {
    mount({ profile: makeProfile({ operating_mode: F(1), heating_in_use: F(false), cooling_in_use: F(true) }) });
    expect(screen.getByTestId('tab-z1cool').getAttribute('aria-selected')).toBe('true');
  });

  it('shows curve mode with a shift control and the model assumption note', () => {
    mount();
    expect(screen.getByTestId('mode-badge').dataset.control).toBe('curve');
    expect(screen.getByTestId('shift-control')).toBeTruthy();
    expect(screen.getByTestId('assumption-note').textContent).toMatch(/Model assumption/);
    expect(screen.queryByTestId('not-active')).toBeNull();
  });

  it('direct mode with a water sensor marks the curve not active and draws the setpoint', () => {
    mount({
      profile: makeProfile({ heating_control: F('direct') }),
      state: makeState({ 'main/Z1_Heat_Request_Temp': 33 }),
    });
    expect(screen.getByTestId('not-active')).toBeTruthy();
    expect(screen.getByTestId('direct-line')).toBeTruthy();
    expect(screen.queryByTestId('shift-control')).toBeNull();
    expect(screen.queryByTestId('coupled-hint')).toBeNull();
  });

  it('direct mode with a thermostat couples the setpoint to the cold-end target', () => {
    mount({
      profile: makeProfile({
        heating_control: F('direct'),
        zone: { z1: { active: F(true), sensor: F('ext_thermostat') }, z2: { active: F(false), sensor: F('water') } },
      }),
    });
    expect(screen.queryByTestId('not-active')).toBeNull();
    expect(screen.getByTestId('coupled-hint').textContent).toContain('45');
  });

  it('coupled mode: the cold-end target can be set below the warm-end target and is applied', async () => {
    const command = vi.spyOn(api, 'command').mockResolvedValue({
      id: 'c1', name: 'SetCurves', payload: '{}', status: 'pending', submitted_ts: Date.now(),
      keys: { 'main/Z1_Heat_Curve_Target_High_Temp': { expected: 20, status: 'pending' } },
    });
    mount({
      profile: makeProfile({
        heating_control: F('direct'),
        zone: { z1: { active: F(true), sensor: F('ext_thermostat') }, z2: { active: F(false), sensor: F('water') } },
      }),
      state: makeState({ 'main/Z1_Heat_Curve_Target_High_Temp': 28 }),
    });
    expect(screen.getByTestId('editor-hint').textContent).toBe(`${en.invariantHintCoupled} ${en.limitsHeat}`);
    const input = screen.getByTestId('input-cold-target');
    await fireEvent.change(input, { target: { value: '20' } });
    expect(input.value).toBe('20');
    await fireEvent.click(screen.getByTestId('apply-curve'));
    await confirmNext(true);
    await waitFor(() => expect(command).toHaveBeenCalledWith({
      name: 'SetCurves', value: { zone1: { heat: { target: { high: 20 } } } }, confirm: true,
    }));
  });

  it('not coupled: the cold-end target still stops at the warm-end target', async () => {
    mount({ state: makeState({ 'main/Z1_Heat_Curve_Target_High_Temp': 40 }) });
    expect(screen.getByTestId('editor-hint').textContent).toBe(`${en.invariantHint} ${en.limitsHeat}`);
    const input = screen.getByTestId('input-cold-target');
    await fireEvent.change(input, { target: { value: '20' } });
    expect(input.value).toBe('30');
  });

  it('warns when the reported target differs from the model by more than 1 °C', () => {
    // model at 5 °C: 45 - 15 * 10/20 = 37.5; reported 38 -> fine
    const { unmount } = mount();
    expect(screen.queryByTestId('model-warning')).toBeNull();
    unmount();
    mount({ state: makeState({ 'main/Z1_Water_Target_Temp': 40 }) });
    expect(screen.getByTestId('model-warning').textContent).toMatch(/37\.5/);
  });

  it('the input stops at the last valid integer', async () => {
    mount();
    const input = screen.getByTestId('input-cold-outside');
    await fireEvent.change(input, { target: { value: '40' } });
    expect(input.value).toBe('14');
    expect(screen.getByTestId('draft-group-curve')).toBeTruthy();
  });

  it('slope/level buttons are disabled when the whole step would break a rule', async () => {
    mount({ state: makeState({ 'main/Z1_Heat_Curve_Target_High_Temp': 75 }) });
    await fireEvent.click(screen.getByTestId('editor-slope-level'));
    expect(screen.getByTestId('slope-plus').disabled).toBe(true);
    expect(screen.getByTestId('slope-minus').disabled).toBe(false);
    expect(screen.getByTestId('level-plus').disabled).toBe(true);
  });

  it('Apply sends one SetCurves with only the changed keys after confirmation', async () => {
    const command = vi.spyOn(api, 'command').mockResolvedValue({
      id: 'u1', name: 'SetCurves', payload: '{}', status: 'pending', submitted_ts: Date.now(),
      keys: { Z1_Heat_Curve_Target_High_Temp: { expected: 47, status: 'pending' } },
    });
    mount();
    await fireEvent.change(screen.getByTestId('input-cold-target'), { target: { value: '47' } });
    await fireEvent.click(screen.getByTestId('apply-curve'));
    expect(command).not.toHaveBeenCalled();
    await confirmNext(true);
    await waitFor(() => expect(command).toHaveBeenCalledTimes(1));
    expect(command).toHaveBeenCalledWith({
      name: 'SetCurves',
      value: { zone1: { heat: { target: { high: 47 } } } },
      confirm: true,
    });
    await waitFor(() => expect(screen.getByTestId('key-status').textContent).toContain('Z1_Heat_Curve_Target_High_Temp'));
  });

  it('a cancelled confirmation sends nothing', async () => {
    const command = vi.spyOn(api, 'command').mockResolvedValue({});
    mount();
    await fireEvent.change(screen.getByTestId('input-warm-target'), { target: { value: '28' } });
    await fireEvent.click(screen.getByTestId('apply-curve'));
    await confirmNext(false);
    expect(command).not.toHaveBeenCalled();
  });

  it('names failed keys of a partial SetCurves failure', async () => {
    const id = 'u2';
    vi.spyOn(api, 'command').mockResolvedValue({
      id, name: 'SetCurves', payload: '{}', status: 'pending', submitted_ts: Date.now(),
      keys: {
        Z1_Heat_Curve_Target_High_Temp: { expected: 47, status: 'pending' },
        Z1_Heat_Curve_Target_Low_Temp: { expected: 28, status: 'pending' },
      },
    });
    mount();
    await fireEvent.change(screen.getByTestId('input-cold-target'), { target: { value: '47' } });
    await fireEvent.change(screen.getByTestId('input-warm-target'), { target: { value: '28' } });
    await fireEvent.click(screen.getByTestId('apply-curve'));
    await confirmNext(true);
    await waitFor(() => expect(get(commands)[id]).toBeTruthy());
    commands.update((m) => ({
      ...m,
      [id]: {
        ...m[id],
        status: 'failed',
        keys: {
          Z1_Heat_Curve_Target_High_Temp: { expected: 47, status: 'confirmed' },
          Z1_Heat_Curve_Target_Low_Temp: { expected: 28, status: 'failed' },
        },
      },
    }));
    await waitFor(() => expect(screen.getByTestId('keys-failed').textContent).toContain('Z1_Heat_Curve_Target_Low_Temp'));
    expect(screen.getByTestId('keys-failed').textContent).not.toContain('Target_High');
  });

  it('threshold markers have their own Apply and are never folded into SetCurves', async () => {
    const command = vi.spyOn(api, 'command').mockResolvedValue({ id: 'u3', name: 'SetHeaterOnOutdoorTemp', status: 'pending', payload: '1', submitted_ts: 1, keys: null });
    mount();
    await fireEvent.change(screen.getByTestId('input-cold-target'), { target: { value: '46' } });
    await fireEvent.keyDown(screen.getByTestId('marker-heaterOn'), { key: 'ArrowRight' });
    const heater = screen.getByTestId('draft-group-heaterOn');
    expect(heater.textContent).toContain('-2');
    expect(heater.textContent).toContain('-1');
    expect(screen.getByTestId('draft-group-curve')).toBeTruthy();
    expect(screen.queryByTestId('draft-group-heatingOff')).toBeNull();
    await fireEvent.click(screen.getByTestId('apply-heaterOn'));
    await confirmNext(true);
    await waitFor(() => expect(command).toHaveBeenCalledTimes(1));
    expect(command).toHaveBeenCalledWith({ name: 'SetHeaterOnOutdoorTemp', value: -1, confirm: true });
  });

  it('threshold markers stop at their catalog ranges', async () => {
    mount({ state: makeState({ 'main/Heater_On_Outdoor_Temp': 20 }) });
    await fireEvent.keyDown(screen.getByTestId('marker-heaterOn'), { key: 'ArrowRight' });
    // 21 is out of range (-15..20): the draft stays at the current value, so no diff appears
    expect(screen.queryByTestId('draft-group-heaterOn')).toBeNull();
  });

  it('the shift stepper has its own Apply with the real command name', async () => {
    const command = vi.spyOn(api, 'command').mockResolvedValue({ id: 'u4', name: 'SetZ1HeatRequestTemperature', status: 'pending', payload: '1', submitted_ts: 1, keys: null });
    mount();
    await fireEvent.click(screen.getByTestId('shift-plus'));
    expect(screen.getByTestId('shift-value').textContent).toBe('1');
    await fireEvent.click(screen.getByTestId('apply-shift'));
    await confirmNext(true);
    await waitFor(() => expect(command).toHaveBeenCalledWith({ name: 'SetZ1HeatRequestTemperature', value: 1, confirm: true }));
  });

  it('shows a rejection code from the backend', async () => {
    vi.spyOn(api, 'command').mockRejectedValue(Object.assign(new Error('x'), { code: 'write_lock' }));
    mount();
    await fireEvent.change(screen.getByTestId('input-warm-target'), { target: { value: '28' } });
    await fireEvent.click(screen.getByTestId('apply-curve'));
    await confirmNext(true);
    await waitFor(() => expect(screen.getByTestId('result-curve').textContent).toContain('write_lock'));
  });

  it('logs applied changes, reverts to previous values as a draft and shows the 24–48 h hint', async () => {
    commands.set({
      a: { id: 'a', name: 'SetCurves', payload: '{"zone1":{"heat":{"target":{"high":45}}}}', status: 'confirmed', submitted_ts: 1000, keys: null },
      b: { id: 'b', name: 'SetCurves', payload: '{"zone1":{"heat":{"target":{"high":47}}}}', status: 'confirmed', submitted_ts: 2000, keys: null },
      c: { id: 'c', name: 'SetCurves', payload: '{"zone2":{"cool":{"target":{"high":12}}}}', status: 'confirmed', submitted_ts: 3000, keys: null },
    });
    mount({ state: makeState({ 'main/Z1_Heat_Curve_Target_High_Temp': 47 }) });
    const entries = screen.getAllByTestId('log-entry');
    expect(entries).toHaveLength(2);
    const revert = screen.getAllByTestId('revert');
    expect(revert[0].disabled).toBe(false);
    expect(revert[1].disabled).toBe(true); // oldest: previous values unknown
    expect(screen.getByTestId('wait-hint').textContent).toMatch(/24–48/);
    await fireEvent.click(revert[0]);
    expect(screen.getByTestId('input-cold-target').value).toBe('45');
    expect(screen.getByTestId('draft-group-curve')).toBeTruthy();
  });

  it('shows the wear warning when the server flags eeprom_warning', () => {
    const now = Date.now();
    commands.set(
      Object.fromEntries(
        [1, 2, 3].map((i) => [`x${i}`, { id: `x${i}`, name: 'SetCurves', payload: '{}', status: 'confirmed', submitted_ts: now - i * 1000, keys: null, eeprom_warning: i === 1 }]),
      ),
    );
    mount();
    return fireEvent.change(screen.getByTestId('input-warm-target'), { target: { value: '28' } }).then(() => {
      expect(screen.getByTestId('eeprom-warning')).toBeTruthy();
    });
  });

  it('renders overlay points from /api/overlay, median, histogram and the COP grey label', async () => {
    mount();
    await waitFor(() => expect(screen.getAllByTestId('overlay-point')).toHaveLength(2));
    expect(api.overlay).toHaveBeenCalledWith(expect.objectContaining({ zone: 'z1', mode: 'heat' }));
    const { from, to } = api.overlay.mock.calls[0][0];
    expect(Math.round((to - from) / 86_400_000)).toBe(14);
    expect(screen.getByTestId('overlay-median')).toBeTruthy();
    expect(screen.getByTestId('overlay-histogram').textContent).toContain('0.5');
    await fireEvent.change(screen.getByTestId('color-by'), { target: { value: 'cop' } });
    await waitFor(() => expect(screen.getByTestId('no-cop-note').textContent).toBe('no COP'));
    const grey = screen.getAllByTestId('overlay-point').filter((p) => p.dataset.noCop === 'true');
    expect(grey).toHaveLength(1);
  });

  it('offers room − setpoint and before/after only when the data supports them', async () => {
    mount();
    await waitFor(() => expect(screen.getAllByTestId('overlay-point')).toHaveLength(2));
    const values = [...screen.getByTestId('color-by').querySelectorAll('option')].map((o) => o.value);
    expect(values).toEqual(['water_minus_target', 'cop', 'freq']);
  });

  it('refetches the overlay for another tab and a new range', async () => {
    mount();
    await waitFor(() => expect(api.overlay).toHaveBeenCalledTimes(1));
    await fireEvent.click(screen.getByTestId('range-30'));
    await waitFor(() => expect(api.overlay).toHaveBeenCalledTimes(2));
    await fireEvent.click(screen.getByTestId('tab-z2cool'));
    await waitFor(() => expect(api.overlay).toHaveBeenLastCalledWith(expect.objectContaining({ zone: 'z2', mode: 'cool' })));
  });

  it('shows the overlay error code when the request fails', async () => {
    api.overlay.mockRejectedValue(Object.assign(new Error('x'), { code: 'storage_unavailable' }));
    mount();
    await waitFor(() => expect(screen.getByTestId('overlay-error').textContent).toContain('storage_unavailable'));
  });

  it('is available in Dutch', async () => {
    language.set('nl');
    mount();
    expect(screen.getByTestId('tab-z1heat').textContent).toContain('Zone 1 verwarmen');
    expect(screen.getAllByText(/Koude kant/).length).toBeGreaterThan(0);
  });
});
