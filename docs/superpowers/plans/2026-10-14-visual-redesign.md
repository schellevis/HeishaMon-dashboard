# Visual Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the Svelte frontend onto the approved "plant schematic" visual design: new tokens and
themes, a rail shell, a live installation schematic, a 24 h timeline and a restyled set of screens.

**Architecture:** Frontend-only. Pure logic lives in small tested modules (`lib/ui/thermal.js`,
`lib/theme.js`, `lib/domain/activity.js`, `lib/eventtext.js`, `features/overview/plant.js`,
`features/overview/timeline.js`). Svelte components only render them. Existing behaviour (commands,
gates, confirm, tiles/prefs, curve editing) is unchanged; existing `data-testid`s are kept.

**Tech Stack:** Svelte 5 (runes), Vite, uPlot 1.6, Vitest + Testing Library (jsdom), Playwright.
New dependencies: `@fontsource/instrument-sans@5.3.0`, `@fontsource-variable/martian-mono@5.3.0`.

**Spec:** `docs/superpowers/specs/2026-10-14-visual-design.md` (run copy `.paseo-autopilot/20261014T072835Z-visual-redesign/01-spec.md`) (amends
`docs/superpowers/specs/2026-10-11-heishamon-dashboard-design.md` §4.2/§7). Visual reference:
`docs/mockups/2026-10-14-redesign/index.html` — open it next to your work
(`python3 -m http.server 8333 --bind 0.0.0.0 -d docs/mockups/2026-10-14-redesign`).

## Global Constraints

- Installation-agnostic: everything shown is derived from the profile and live state; never hard-code the owner's setup (AGENTS.md).
- Unknown profile input → show the feature (spec §4.3 "Unknown inputs").
- Text contrast: functional text uses `--ink`, `--ink-2`, `--ink-3` or the `-ink` state variants (`--ok-ink`, `--pending-ink`, `--fail-ink`, `--warm-ink`), never the raw accent colours (spec R1 "Readable text").
- Bilingual: every new UI string gets a key in both `*.en.js` and `*.nl.js` of the same module (`tests/i18n.test.js` enforces parity).
- Keep every existing `data-testid`; tests and Playwright depend on them.
- Fonts are bundled (Fontsource), never loaded from a CDN.
- `prefers-reduced-motion: reduce` stops all animation.
- Breakpoint: desktop ≥ 760 px, phone < 760 px.
- Colours: components use CSS variables only; hex literals are allowed only in `src/app.css`, `src/lib/ui/thermal.js` and `src/lib/uplot.js` (enforced in Task 10).
- No backend changes. History reads: `GET /api/history` ≤ 20 topics; refresh at most every 5 min, never per live message.
- Run test suites one after another, never in parallel (AGENTS.md). Vitest: `VITE_CACHE_DIR=/tmp/vite-<attempt-id> npm --prefix frontend run test`. Playwright: `cd frontend && npx playwright test`.
- Work on branch `feat/visual-redesign`. Builders never commit; the orchestrator commits each accepted wave. Merging to `main` only when the owner asks. Documentation files (`AGENTS.md`, `README.md`) are not edited during the build waves; the deferred task D1 handles them after verification.

## Configuration and wave overview
- Run copy: `/workspace/heishamon-dashboard/.paseo-autopilot/20261014T072835Z-visual-redesign/03-plan.md` is byte-identical to `docs/superpowers/plans/2026-10-14-visual-redesign.md`.
- Initial spec / plan reviews: 1 / 1
- Builder cap / user cap / effective concurrency: 4 / 1 / 1 (builders on the Pro-tier claude-2 account; waves therefore execute one task at a time, in the listed order)
- Final verifiers: 1
- Waves: W1 = T1; W2 = T2, T3, T4; W3 = T5, T6, T7, T8; W4 = T9; W5 = T10; W6 = T11; deferred (post-VERIFY) = D1
- Integrated baseline: branch `feat/visual-redesign` at the orchestrator's wave commit; each builder starts from the previous wave's commit plus nothing else uncommitted except the run directory (gitignored).
- Builder validation: `VITE_CACHE_DIR=/tmp/vite-<attempt-id> npm --prefix frontend run test`; builds with `npm --prefix frontend run build` (writes `frontend/dist`, serial by construction); Playwright only where a task says so (port 8765, serial by construction).
- Verification commands (verifier, serial, in this order, workspace `/workspace/heishamon-dashboard`, no other agent running): `VITE_CACHE_DIR=/tmp/vite-verify npm --prefix frontend run test`; `npm --prefix frontend run build`; `cd frontend && npx playwright test` (port 8765, embedded broker and simulator started by the suite); `.venv/bin/python -m pytest backend/tests -q`. Exclusive resources: port 8765, `frontend/dist`, `/tmp/vite-verify`, `/tmp/pw-T19-results`.
- Builders never commit; the orchestrator commits each accepted wave on `feat/visual-redesign`. Nobody pushes or merges.

---

## File map

| File | Status | Responsibility |
|---|---|---|
| `frontend/src/app.css` | rewrite | tokens, themes, fonts, base controls, shared panel/tag classes |
| `frontend/src/lib/ui/thermal.js` | new | thermal ramp `tempColor`, activity colour vars, `mix` helper |
| `frontend/src/lib/theme.js` | new | theme choice (localStorage), resolved theme store, `cssVar` |
| `frontend/src/lib/domain/activity.js` | new | `activityFrom(...)` shared by status bar and timeline |
| `frontend/src/lib/format.js` | modify | `activityOf` delegates to `activityFrom` |
| `frontend/src/lib/eventtext.js` | new | event/command labels and the merged "recent" list |
| `frontend/src/app/icons.js` | new | nav icon paths per screen id |
| `frontend/src/app/App.svelte`, `Nav.svelte`, `Statusbar.svelte` | rewrite | rail shell, status strip, theme toggle |
| `frontend/src/features/overview/plant.js` | new | `plantModel(state, profile)`, `plantGeometry(model)` |
| `frontend/src/features/overview/PlantSchematic.svelte` | new | live schematic |
| `frontend/src/features/overview/NowPanel.svelte` | new | COP, power, today's energy |
| `frontend/src/features/overview/timeline.js` | new | history → grid, activity bands |
| `frontend/src/features/overview/Timeline24h.svelte` | new | uPlot timeline with band plugin and readout |
| `frontend/src/features/overview/MiniCurve.svelte` | new | read-only `CurveChart` for the active zone/mode |
| `frontend/src/features/overview/RecentEvents.svelte` | new | six newest events/commands |
| `frontend/src/features/overview/OverviewScreen.svelte`, `QuickControls.svelte`, `Tile.svelte`, `Sparkline.svelte` | modify | new layout and style |
| `frontend/src/lib/uplot.js` | modify | palette, themed axes, `stepped` series flag |
| `frontend/src/lib/curvegeom.js` | modify | deviation/sequential colours on the ramp |
| all other `*.svelte` under `features/` and `lib/ui/` | restyle | tokens only |
| `frontend/tests/*.test.js` | new/modify | per task |
| `frontend/e2e/visual.spec.js` | new | theme/phone smoke |

---

### Task 0: Branch (orchestrator, done)

The orchestrator created `feat/visual-redesign` from `main` at e9d75b2 before the run. No builder task.

---

### Task 1: Tokens, fonts, theme and thermal ramp

- Wave: 1
- Dependencies: none
- Owned files: frontend/package.json, frontend/package-lock.json, frontend/index.html, frontend/src/main.js, frontend/src/app.css, frontend/src/lib/ui/thermal.js, frontend/src/lib/theme.js, frontend/tests/thermal.test.js, frontend/tests/theme.test.js, frontend/tests/contrast.test.js
- Shared mutable paths: frontend/node_modules (installs), frontend/dist, /tmp/vite-<attempt-id>
- Exclusive resources: frontend/node_modules and package-lock.json (only task that installs)
- Consumed interfaces: none
- Produced interfaces: thermal.js (RAMP, ACTIVITY_VAR, mixRgb, tempColor); theme.js (THEME_KEY, themeChoice, resolvedTheme, initTheme, setTheme, cssVar); app.css tokens incl. legacy aliases
- Acceptance criteria: every step below done; its tests and the full Vitest suite PASS; no file outside the owned files changed
- Validation: `VITE_CACHE_DIR=/tmp/vite-<attempt-id> npm --prefix frontend run test` (full suite) plus the step-specific commands below
- Report pattern: reports/build/T1--<attempt-id>.md

**Files:**
- Modify: `frontend/package.json`, `frontend/package-lock.json` (via npm)
- Rewrite: `frontend/src/app.css`
- Modify: `frontend/src/main.js`, `frontend/index.html`
- Create: `frontend/src/lib/ui/thermal.js`, `frontend/src/lib/theme.js`
- Test: `frontend/tests/thermal.test.js`, `frontend/tests/theme.test.js`, `frontend/tests/contrast.test.js`

**Interfaces:**
- Produces: `tempColor(t: number|null): string` (`'rgb(r,g,b)'`, or `'var(--pipe-idle)'` for null/non-finite); `RAMP`; `MARK_RGB`; `ACTIVITY_VAR: {heating,cooling,dhw,defrost,idle}` → CSS var name; `mixRgb(a: number[], b: number[], f: number): string`.
- Produces: `THEME_KEY = 'heishamon.theme'`; `themeChoice` (writable `'day'|'night'|null`); `resolvedTheme` (readable `'day'|'night'`); `initTheme({storage, media, root}) → unsubscribe`; `setTheme(choice)`; `cssVar(name, root?) → string`.

- [ ] **Step 1: Install fonts**

```bash
npm --prefix frontend install --save-exact @fontsource/instrument-sans@5.3.0 @fontsource-variable/martian-mono@5.3.0
ls frontend/node_modules/@fontsource-variable/martian-mono/   # expect index.css and wdth.css (or full.css) among the files
```

Use the CSS file that contains the `wdth` axis (`wdth.css`, else `full.css`). If neither exists,
use `index.css`; `font-stretch` then has no effect, which is acceptable. Write the chosen file into
Step 6.

- [ ] **Step 2: Write failing tests**

`frontend/tests/thermal.test.js`:

```js
import { describe, expect, it } from 'vitest';
import { ACTIVITY_VAR, RAMP, mixRgb, tempColor } from '../src/lib/ui/thermal.js';

describe('thermal ramp', () => {
  it('hits the stops exactly', () => {
    expect(tempColor(15)).toBe('rgb(79,163,224)');
    expect(tempColor(28)).toBe('rgb(143,184,201)');
    expect(tempColor(38)).toBe('rgb(240,160,75)');
    expect(tempColor(55)).toBe('rgb(229,83,61)');
  });
  it('clamps outside the ramp', () => {
    expect(tempColor(-20)).toBe(tempColor(15));
    expect(tempColor(80)).toBe(tempColor(55));
  });
  it('interpolates between stops', () => {
    expect(tempColor(46.5)).toBe(mixRgb([240, 160, 75], [229, 83, 61], 0.5));
  });
  it('returns the idle pipe colour for missing values', () => {
    expect(tempColor(null)).toBe('var(--pipe-idle)');
    expect(tempColor(Number.NaN)).toBe('var(--pipe-idle)');
  });
  it('has four ascending stops and a colour per activity', () => {
    expect(RAMP.map(([t]) => t)).toEqual([15, 28, 38, 55]);
    expect(Object.keys(ACTIVITY_VAR).sort()).toEqual(['cooling', 'defrost', 'dhw', 'heating', 'idle']);
  });
});
```

`frontend/tests/theme.test.js`:

```js
import { describe, expect, it } from 'vitest';
import { get } from 'svelte/store';
import { THEME_KEY, initTheme, resolvedTheme, setTheme, themeChoice } from '../src/lib/theme.js';

function memoryStorage(initial = {}) {
  const data = { ...initial };
  return { getItem: (k) => data[k] ?? null, setItem: (k, v) => { data[k] = String(v); }, removeItem: (k) => { delete data[k]; }, data };
}
function media(light) {
  const listeners = new Set();
  return {
    matches: light,
    addEventListener: (_, fn) => listeners.add(fn),
    removeEventListener: (_, fn) => listeners.delete(fn),
    fire(next) { this.matches = next; for (const fn of listeners) fn({ matches: next }); },
  };
}

describe('theme', () => {
  it('follows the system until a choice is stored', () => {
    const root = document.createElement('html');
    const m = media(true);
    const stop = initTheme({ storage: memoryStorage(), media: m, root });
    expect(get(resolvedTheme)).toBe('day');
    expect(root.dataset.theme).toBe('day');
    m.fire(false);
    expect(get(resolvedTheme)).toBe('night');
    expect(root.dataset.theme).toBe('night');
    stop();
  });
  it('restores and persists an explicit choice', () => {
    const root = document.createElement('html');
    const storage = memoryStorage({ [THEME_KEY]: 'night' });
    const stop = initTheme({ storage, media: media(true), root });
    expect(get(themeChoice)).toBe('night');
    expect(root.dataset.theme).toBe('night');
    setTheme('day');
    expect(storage.data[THEME_KEY]).toBe('day');
    expect(root.dataset.theme).toBe('day');
    setTheme(null);
    expect(storage.data[THEME_KEY]).toBeUndefined();
    stop();
  });
  it('ignores a garbage stored value', () => {
    const root = document.createElement('html');
    const stop = initTheme({ storage: memoryStorage({ [THEME_KEY]: 'pink' }), media: media(false), root });
    expect(get(themeChoice)).toBe(null);
    expect(root.dataset.theme).toBe('night');
    stop();
  });
});
```

`frontend/tests/contrast.test.js` (spec R1 "Readable text": WCAG ≥ 4.5:1 for functional text):

```js
import { describe, expect, it } from 'vitest';
import css from '../src/app.css?raw';

function block(selector) {
  const start = css.indexOf(selector);
  return css.slice(start, css.indexOf('}', start));
}
function vars(text) {
  return Object.fromEntries([...text.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1], m[2]]));
}
function luminance(hex) {
  const [r, g, b] = [1, 3, 5]
    .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function ratio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe('text contrast', () => {
  for (const [name, selector] of [['night', ":root[data-theme='night']"], ['day', ":root[data-theme='day']"]]) {
    it(`meets 4.5:1 for functional text in ${name}`, () => {
      const v = vars(block(selector));
      for (const fg of ['ink', 'ink-2', 'ink-3', 'ok-ink', 'pending-ink', 'fail-ink', 'warm-ink']) {
        for (const bg of ['panel', 'panel-2', 'ground']) {
          expect(ratio(v[fg], v[bg]), `${fg} on ${bg}`).toBeGreaterThanOrEqual(4.5);
        }
      }
    });
  }
});
```

- [ ] **Step 3: Run, expect FAIL** — `VITE_CACHE_DIR=/tmp/vite-<attempt-id> npm --prefix frontend run test -- thermal theme contrast` → "Failed to resolve import" (contrast fails until Step 6 writes `app.css`).

- [ ] **Step 4: Implement `frontend/src/lib/ui/thermal.js`**

```js
/** Temperature colours (spec 2026-10-14 §2): one cold→warm ramp for everything that is a temperature. */

export const RAMP = [
  [15, [79, 163, 224]],
  [28, [143, 184, 201]],
  [38, [240, 160, 75]],
  [55, [229, 83, 61]],
];

/** Non-temperature marks shared by charts: neutral grey and the "after" / ok green. */
export const MARK_RGB = { neutral: [147, 163, 176], ok: [108, 197, 154] };

/** CSS variable per activity; the same colour marks an activity everywhere. */
export const ACTIVITY_VAR = {
  heating: '--warm',
  dhw: '--hot',
  cooling: '--cold',
  defrost: '--cool',
  idle: '--line-2',
};

export function mixRgb(a, b, f) {
  return `rgb(${a.map((x, i) => Math.round(x + (b[i] - x) * f)).join(',')})`;
}

export function tempColor(t) {
  if (t === null || t === undefined || !Number.isFinite(t)) return 'var(--pipe-idle)';
  if (t <= RAMP[0][0]) return mixRgb(RAMP[0][1], RAMP[0][1], 0);
  for (let i = 1; i < RAMP.length; i++) {
    const [t1, c1] = RAMP[i];
    if (t <= t1) {
      const [t0, c0] = RAMP[i - 1];
      return mixRgb(c0, c1, (t - t0) / (t1 - t0));
    }
  }
  const last = RAMP[RAMP.length - 1][1];
  return mixRgb(last, last, 0);
}
```

- [ ] **Step 5: Implement `frontend/src/lib/theme.js`**

```js
/** Day/night theme: browser-local like the language (spec 2026-10-14 §3), never a server pref. */
import { derived, writable } from 'svelte/store';

export const THEME_KEY = 'heishamon.theme';
const VALID = new Set(['day', 'night']);

export const themeChoice = writable(null);
const systemLight = writable(false);
export const resolvedTheme = derived([themeChoice, systemLight], ([choice, light]) => choice ?? (light ? 'day' : 'night'));

let store = null;

export function setTheme(choice) {
  const next = VALID.has(choice) ? choice : null;
  themeChoice.set(next);
  if (next) store?.setItem?.(THEME_KEY, next);
  else store?.removeItem?.(THEME_KEY);
}

export function initTheme({
  storage = globalThis.localStorage,
  media = globalThis.matchMedia?.('(prefers-color-scheme: light)'),
  root = globalThis.document?.documentElement,
} = {}) {
  store = storage;
  const saved = storage?.getItem?.(THEME_KEY);
  themeChoice.set(VALID.has(saved) ? saved : null);
  systemLight.set(Boolean(media?.matches));
  const onMedia = (event) => systemLight.set(Boolean(event.matches));
  media?.addEventListener?.('change', onMedia);
  const unsub = resolvedTheme.subscribe((theme) => {
    if (root) root.dataset.theme = theme;
  });
  return () => {
    unsub();
    media?.removeEventListener?.('change', onMedia);
  };
}

/** Current value of a CSS custom property (charts need concrete colours). */
export function cssVar(name, root = globalThis.document?.documentElement) {
  if (!root || !globalThis.getComputedStyle) return '';
  return getComputedStyle(root).getPropertyValue(name).trim();
}
```

- [ ] **Step 6: Rewrite `frontend/src/app.css`**

```css
/* Design tokens (spec 2026-10-14 §2). Components use these variables only. */
:root {
  --cold: #4fa3e0;
  --cool: #8fb8c9;
  --warm: #f0a04b;
  --hot: #e5533d;
  --ok: #6cc59a;
  --pending: #e8c25a;
  --fail: #e5533d;
  --font-ui: 'Instrument Sans', system-ui, sans-serif;
  --font-data: 'Martian Mono Variable', 'Martian Mono', ui-monospace, monospace;
  --r: 10px;
  --r-control: 8px;

  /* Legacy names, kept until every screen is migrated (removed in Task 10). */
  --bg: var(--panel);
  --bg-secondary: var(--panel-2);
  --bg-hover: var(--line);
  --border: var(--line-2);
  --text: var(--ink);
  --text-secondary: var(--ink-2);
  --primary: var(--warm);
  --primary-dark: var(--hot);
  --danger: var(--fail);
  --warn-bg: color-mix(in srgb, var(--pending) 14%, transparent);
  --warn-border: var(--pending);
  --card-radius: var(--r);
}
:root,
:root[data-theme='night'] {
  --ground: #12181c;
  --panel: #182026;
  --panel-2: #1e2830;
  --line: #2a3640;
  --line-2: #364552;
  --ink: #dce3e8;
  --ink-2: #93a3b0;
  --ink-3: #8494a1;
  --pipe-idle: #33414c;
  --unit: #222c34;
  --flow-dash: rgb(255 255 255 / .7);
  --ok-ink: #6cc59a;
  --pending-ink: #e8c25a;
  --fail-ink: #ef6a55;
  --warm-ink: #f0a04b;
  color-scheme: dark;
}
:root[data-theme='day'] {
  --ground: #e9edf0;
  --panel: #ffffff;
  --panel-2: #f3f6f8;
  --line: #d5dde3;
  --line-2: #bcc8d1;
  --ink: #18212a;
  --ink-2: #4f5f6c;
  --ink-3: #5a6874;
  --pipe-idle: #c9d3da;
  --unit: #f6f8f9;
  --flow-dash: rgb(255 255 255 / .95);
  --ok-ink: #2a7050;
  --pending-ink: #7a5d0a;
  --fail-ink: #b8321f;
  --warm-ink: #8f520f;
  color-scheme: light;
}

html, body { margin: 0; }
body {
  background: var(--ground);
  color: var(--ink);
  font: 400 14px/1.45 var(--font-ui);
  -webkit-font-smoothing: antialiased;
}

/* Shared building blocks */
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: var(--r); min-width: 0; }
.panel-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 16px; border-bottom: 1px solid var(--line); }
.panel-head h2 { margin: 0; font: 600 13.5px var(--font-ui); }
.panel-body { padding: 16px; }
.tag { font: 500 10.5px/1 var(--font-data); font-stretch: 87.5%; letter-spacing: .08em; text-transform: uppercase; color: var(--ink-3); }
.num { font-family: var(--font-data); font-variant-numeric: tabular-nums; font-stretch: 87.5%; }
.value-stale { color: var(--ink-3); }

/* Controls */
button, select, input, textarea { font: inherit; font-size: 13px; color: var(--ink); }
button {
  padding: 6px 12px;
  border: 1px solid var(--line-2);
  border-radius: var(--r-control);
  background: var(--panel-2);
  cursor: pointer;
}
button:hover:not(:disabled) { background: var(--line); }
button:disabled { cursor: not-allowed; opacity: .45; }
button.primary { background: var(--ink); color: var(--ground); border-color: var(--ink); font-weight: 600; }
button.primary:hover:not(:disabled) { background: var(--ink); opacity: .9; }
button[aria-pressed='true'] { background: var(--panel); box-shadow: 0 0 0 1px var(--line-2); }
select,
input:not([type='checkbox']):not([type='radio']):not([type='range']),
textarea {
  padding: 6px 8px;
  border: 1px solid var(--line-2);
  border-radius: var(--r-control);
  background: var(--panel-2);
  box-sizing: border-box;
  max-width: 100%;
}
input[type='range'] { accent-color: var(--warm); }
input[type='checkbox'], input[type='radio'] { accent-color: var(--warm); }
a { color: var(--ink); }

:focus-visible { outline: 2px solid var(--warm); outline-offset: 2px; border-radius: 4px; }

table { border-collapse: collapse; }
th { font-weight: 500; color: var(--ink-2); text-align: left; }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
```

- [ ] **Step 7: Wire fonts and theme in `frontend/src/main.js`**

```js
import { mount } from 'svelte';
import '@fontsource/instrument-sans/400.css';
import '@fontsource/instrument-sans/500.css';
import '@fontsource/instrument-sans/600.css';
import '@fontsource-variable/martian-mono/wdth.css'; // the file chosen in Step 1
import 'uplot/dist/uPlot.min.css';
import './app.css';
import { initTheme } from './lib/theme.js';
import App from './app/App.svelte';

initTheme();
const app = mount(App, { target: document.getElementById('app') });

export default app;
```

In `frontend/index.html` add `data-theme="night"` to `<html>` (avoids a light flash before JS runs).

- [ ] **Step 8: Run tests** — `VITE_CACHE_DIR=/tmp/vite-<attempt-id> npm --prefix frontend run test` → all PASS (new and existing).
- [ ] **Step 9: Build check** — `npm --prefix frontend run build` → succeeds; `ls frontend/dist/assets | grep -E 'woff2'` lists font files.
- [ ] **Step 10: Commit** — done by the orchestrator after the wave is accepted; builders never commit. Write the build report instead.

---

### Task 2: Shared activity rule

- Wave: 2
- Dependencies: Task 1
- Owned files: frontend/src/lib/domain/activity.js, frontend/src/lib/format.js, frontend/tests/activity.test.js
- Shared mutable paths: /tmp/vite-<attempt-id>
- Exclusive resources: none
- Consumed interfaces: rules.js modeSets
- Produced interfaces: activityFrom({defrost, valve, heatpump, mode})
- Acceptance criteria: every step below done; its tests and the full Vitest suite PASS; no file outside the owned files changed
- Validation: `VITE_CACHE_DIR=/tmp/vite-<attempt-id> npm --prefix frontend run test` (full suite) plus the step-specific commands below
- Report pattern: reports/build/T2--<attempt-id>.md

**Files:**
- Create: `frontend/src/lib/domain/activity.js`
- Modify: `frontend/src/lib/format.js:36-46`
- Test: `frontend/tests/activity.test.js`

**Interfaces:**
- Produces: `activityFrom({defrost, valve, heatpump, mode}, {strict = false} = {}) → 'defrost'|'dhw'|'idle'|'heating'|'cooling'|'unknown'`. Lenient (default, live state): values ≥ 0.5 count as on, missing inputs are skipped, `mode` is rounded, never `'unknown'`. Strict (timeline, spec R3.4): a missing input needed to exclude a higher-priority activity, or a mode in no mode set, yields `'unknown'`.

- [ ] **Step 1: Failing test** `frontend/tests/activity.test.js`

```js
import { describe, expect, it } from 'vitest';
import { activityFrom } from '../src/lib/domain/activity.js';
import { activityOf } from '../src/lib/format.js';
import { modeSets } from '../src/lib/domain/rules.js';

const heatMode = modeSets.heating[0];
const coolMode = modeSets.cooling.find((m) => !modeSets.heating.includes(m));

describe('activityFrom', () => {
  it('defrost wins over everything', () => {
    expect(activityFrom({ defrost: 1, valve: 1, heatpump: 1, mode: heatMode })).toBe('defrost');
  });
  it('valve on DHW means dhw', () => {
    expect(activityFrom({ defrost: 0, valve: 1, heatpump: 1, mode: heatMode })).toBe('dhw');
  });
  it('heat pump off means idle', () => {
    expect(activityFrom({ defrost: 0, valve: 0, heatpump: 0, mode: heatMode })).toBe('idle');
  });
  it('falls back to the mode', () => {
    expect(activityFrom({ defrost: 0, valve: 0, heatpump: 1, mode: heatMode })).toBe('heating');
    expect(activityFrom({ defrost: 0, valve: 0, heatpump: 1, mode: coolMode })).toBe('cooling');
    expect(activityFrom({ defrost: null, valve: null, heatpump: null, mode: null })).toBe('idle');
  });
  it('treats rollup averages with a 0.5 threshold', () => {
    expect(activityFrom({ defrost: 0.6, valve: 0, heatpump: 1, mode: heatMode })).toBe('defrost');
    expect(activityFrom({ defrost: 0.4, valve: 0.2, heatpump: 0.9, mode: heatMode + 0.2 })).toBe('heating');
  });
  it('strict mode returns unknown when a needed input is missing', () => {
    const strict = { strict: true };
    expect(activityFrom({ defrost: null, valve: 0, heatpump: 1, mode: heatMode }, strict)).toBe('unknown');
    expect(activityFrom({ defrost: 0, valve: null, heatpump: 1, mode: heatMode }, strict)).toBe('unknown');
    expect(activityFrom({ defrost: 0, valve: 0, heatpump: null, mode: heatMode }, strict)).toBe('unknown');
    expect(activityFrom({ defrost: 0, valve: 0, heatpump: 1, mode: null }, strict)).toBe('unknown');
    expect(activityFrom({ defrost: 0, valve: 0, heatpump: 1, mode: 99 }, strict)).toBe('unknown');
    expect(activityFrom({ defrost: 1, valve: null, heatpump: null, mode: null }, strict)).toBe('defrost');
    expect(activityFrom({ defrost: 0, valve: 0, heatpump: 0, mode: null }, strict)).toBe('idle');
    expect(activityFrom({ defrost: 0, valve: 0, heatpump: 1, mode: heatMode }, strict)).toBe('heating');
  });
  it('activityOf still agrees for a live state', () => {
    const t = (value) => ({ value, sentinel: false });
    const state = { topics: { 'main/Defrosting_State': t(0), 'main/ThreeWay_Valve_State': t(1), 'main/Heatpump_State': t(1) } };
    expect(activityOf(state, null)).toBe('dhw');
  });
});
```

- [ ] **Step 2: Run** `VITE_CACHE_DIR=/tmp/vite-<attempt-id> npm --prefix frontend run test -- activity` → FAIL (module missing).

- [ ] **Step 3: Implement `frontend/src/lib/domain/activity.js`**

```js
/** What the heat pump is doing, from the defrost flag, valve, on/off state and operating mode. */
import { modeSets } from './rules.js';

const HEATING = new Set(modeSets.heating);
const COOLING = new Set(modeSets.cooling);
const DHW = new Set(modeSets.dhw);
const on = (v) => typeof v === 'number' && v >= 0.5;
const known = (v) => typeof v === 'number' && Number.isFinite(v);

function fromMode(mode) {
  const m = known(mode) ? Math.round(mode) : null;
  if (HEATING.has(m)) return 'heating';
  if (COOLING.has(m)) return 'cooling';
  if (DHW.has(m)) return 'dhw';
  return null;
}

/** Strict: only claim a lower-priority activity when every higher-priority input is known (spec R3.4). */
function strictActivity({ defrost, valve, heatpump, mode }) {
  if (!known(defrost)) return 'unknown';
  if (on(defrost)) return 'defrost';
  if (!known(valve)) return 'unknown';
  if (on(valve)) return 'dhw';
  if (!known(heatpump)) return 'unknown';
  if (heatpump < 0.5) return 'idle';
  return fromMode(mode) ?? 'unknown';
}

export function activityFrom({ defrost = null, valve = null, heatpump = null, mode = null } = {}, { strict = false } = {}) {
  if (strict) return strictActivity({ defrost, valve, heatpump, mode });
  if (on(defrost)) return 'defrost';
  if (on(valve)) return 'dhw';
  if (typeof heatpump === 'number' && heatpump < 0.5) return 'idle';
  return fromMode(mode) ?? 'idle';
}
```

- [ ] **Step 4: Replace `activityOf` in `frontend/src/lib/format.js`** (keep the doc comment; remove the now-unused `HEATING_MODES`/`COOLING_MODES`/`DHW_MODES` constants only if nothing else in the file uses them — `grep -n "_MODES" frontend/src/lib/format.js`):

```js
import { activityFrom } from './domain/activity.js';

export function activityOf(state, profile) {
  const field = profile?.operating_mode;
  return activityFrom({
    defrost: topicNumber(state, 'main/Defrosting_State'),
    valve: topicNumber(state, 'main/ThreeWay_Valve_State'),
    heatpump: topicNumber(state, 'main/Heatpump_State'),
    mode: field && !field.unknown ? field.value : topicNumber(state, 'main/Operating_Mode_State'),
  });
}
```

- [ ] **Step 5: Run full Vitest** → PASS (status-bar tests exercise `activityOf`).
- [ ] **Step 6: Commit** — done by the orchestrator after the wave is accepted; builders never commit. Write the build report instead.

---

### Task 3: Shell — icon rail, status strip, theme toggle

- Wave: 2
- Dependencies: Task 1
- Owned files: frontend/src/app/icons.js, frontend/src/app/App.svelte, frontend/src/app/Nav.svelte, frontend/src/app/Statusbar.svelte, frontend/src/lib/i18n/common.en.js, frontend/src/lib/i18n/common.nl.js, frontend/tests/shell.test.js; selector-only fixes in frontend/tests/{registry,foundation,smoke,state}.test.js and frontend/e2e/*.spec.js if the markup change breaks them
- Shared mutable paths: frontend/dist, /tmp/vite-<attempt-id>
- Exclusive resources: port 8765 (Playwright smoke, optional)
- Consumed interfaces: themeChoice, resolvedTheme, setTheme (Task 1)
- Produced interfaces: ICONS, iconFor(id); data-testid="theme-toggle"
- Acceptance criteria: every step below done; its tests and the full Vitest suite PASS; no file outside the owned files changed
- Validation: `VITE_CACHE_DIR=/tmp/vite-<attempt-id> npm --prefix frontend run test` (full suite) plus the step-specific commands below
- Report pattern: reports/build/T3--<attempt-id>.md

**Files:**
- Create: `frontend/src/app/icons.js`
- Rewrite: `frontend/src/app/App.svelte`, `frontend/src/app/Nav.svelte`, `frontend/src/app/Statusbar.svelte`
- Modify: `frontend/src/lib/i18n/common.en.js`, `common.nl.js`
- Test: `frontend/tests/shell.test.js`; existing `registry.test.js`, `foundation.test.js`, `smoke.test.js` must stay green

**Interfaces:**
- Consumes: `themeChoice`, `resolvedTheme`, `setTheme` (Task 1).
- Produces: `ICONS: Record<screenId, string>` (SVG path `d`), `iconFor(id)`.

- [ ] **Step 1: i18n keys** — add to `common.en.js` / `common.nl.js`:

```js
// en
themeToggle: 'Switch theme',
themeDay: 'Day',
themeNight: 'Night',
brand: 'HeishaMon dashboard',
// nl
themeToggle: 'Thema wisselen',
themeDay: 'Dag',
themeNight: 'Nacht',
brand: 'HeishaMon-dashboard',
```

- [ ] **Step 2: Failing test** `frontend/tests/shell.test.js`

```js
import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { get } from 'svelte/store';
import Nav from '../src/app/Nav.svelte';
import Statusbar from '../src/app/Statusbar.svelte';
import registry from '../src/app/registry.js';
import { iconFor } from '../src/app/icons.js';
import { resolvedTheme, setTheme } from '../src/lib/theme.js';

describe('nav rail', () => {
  it('has an icon for every registered screen', () => {
    for (const { id } of registry) expect(iconFor(id)).toMatch(/^M/);
  });
  it('renders an svg icon inside each link and keeps the label as text', () => {
    const { container } = render(Nav, { variant: 'side' });
    const links = [...container.querySelectorAll('a')];
    expect(links).toHaveLength(registry.length);
    for (const a of links) expect(a.querySelector('svg')).not.toBeNull();
  });
});

describe('status strip', () => {
  it('toggles the theme between day and night', async () => {
    setTheme('night');
    render(Statusbar, { now: 0 });
    await fireEvent.click(screen.getByTestId('theme-toggle'));
    expect(get(resolvedTheme)).toBe('day');
    await fireEvent.click(screen.getByTestId('theme-toggle'));
    expect(get(resolvedTheme)).toBe('night');
  });
  it('keeps the existing test ids', () => {
    render(Statusbar, { now: 0 });
    for (const id of ['device-status', 'broker-status', 'last-message', 'error-code', 'operating-mode', 'activity', 'write-lock', 'language-switch', 'lang-en', 'lang-nl']) {
      expect(screen.getByTestId(id)).toBeTruthy();
    }
  });
});
```

- [ ] **Step 3: Run** → FAIL (`icons.js` missing, no `theme-toggle`).

- [ ] **Step 4: `frontend/src/app/icons.js`**

```js
/** 24×24 stroke icons for the nav, keyed by screen id. */
export const ICONS = {
  overview: 'M3 12h4l3-7 4 14 3-7h4',
  charts: 'M4 19V5M4 19h16M8 15l4-5 3 3 5-6',
  energy: 'M13 3 5 13h6l-1 8 8-10h-6z',
  curve: 'M4 7h4l8 10h4M8 5.2a1.8 1.8 0 1 0 0 3.6 1.8 1.8 0 1 0 0-3.6M16 15.2a1.8 1.8 0 1 0 0 3.6 1.8 1.8 0 1 0 0-3.6',
  settings: 'M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M14 6a2 2 0 1 0 4 0 2 2 0 1 0-4 0M8 12a2 2 0 1 0 4 0 2 2 0 1 0-4 0M16 18a2 2 0 1 0 4 0 2 2 0 1 0-4 0',
  topics: 'M5 6h14M5 12h14M5 18h9',
  log: 'M6 4h9l3 3v13H6zM9 11h6M9 15h6',
  system: 'M4 5h16v10H4zM9 19h6M12 15v4',
};
const FALLBACK = 'M12 9a3 3 0 1 0 0 6 3 3 0 1 0 0-6';

export function iconFor(id) {
  return ICONS[id] ?? FALLBACK;
}
```

- [ ] **Step 5: `frontend/src/app/Nav.svelte`** — same markup contract (one `<a>` per feature, `href="#/<id>"`, `data-testid="nav-<id>"`, `aria-current`), new look. Log and System sit at the bottom of the rail (`order >= 7`).

```svelte
<script>
  import { language, route } from '../lib/stores.js';
  import registry from './registry.js';
  import { iconFor } from './icons.js';
  import { translate } from '../lib/i18n/index.js';

  let { variant = 'side' } = $props();
  // Log and System are reference screens: bottom of the rail on desktop.
  const isTail = (f) => f.order >= 7;
</script>

<nav data-variant={variant} aria-label={translate($language, 'common.navLabel')}>
  {#if variant === 'side'}
    <svg class="mark" viewBox="0 0 36 36" aria-hidden="true">
      <rect x="1" y="1" width="34" height="34" rx="9" fill="none" stroke="var(--line-2)" />
      <path d="M8 22 C 12 12, 16 12, 18 18 S 24 24, 28 14" fill="none" stroke="var(--warm)" stroke-width="2.4" stroke-linecap="round" />
      <circle cx="28" cy="14" r="2.6" fill="var(--warm)" />
    </svg>
  {/if}
  {#each registry as feature (feature.id)}
    {#if variant === 'side' && isTail(feature) && registry.find(isTail) === feature}<span class="spacer"></span>{/if}
    <a
      href={`#/${feature.id}`}
      data-testid={`nav-${feature.id}`}
      aria-current={$route === feature.id ? 'page' : undefined}
      onclick={() => route.set(feature.id)}
    ><svg viewBox="0 0 24 24" aria-hidden="true"><path d={iconFor(feature.id)} /></svg>{translate($language, feature.navKey)}</a>
  {/each}
</nav>

<style>
  nav { display: flex; background: var(--panel); min-width: 0; }
  a {
    display: flex; flex-direction: column; align-items: center; gap: 4px;
    color: var(--ink-3); text-decoration: none; font-size: 11px; border-radius: 8px; padding: 8px 0;
  }
  a svg { width: 20px; height: 20px; stroke: currentColor; fill: none; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
  a:hover { color: var(--ink); background: var(--panel-2); }
  a[aria-current='page'] { color: var(--ink); background: var(--panel-2); }
  .mark { width: 36px; height: 36px; margin-bottom: 14px; }
  .spacer { flex: 1; }
  nav[data-variant='side'] {
    flex-direction: column; align-items: center; gap: 4px; width: 76px; flex: none;
    padding: 14px 0; border-right: 1px solid var(--line);
    position: sticky; top: 0; height: 100vh; box-sizing: border-box;
  }
  nav[data-variant='side'] a { width: 64px; text-align: center; }
  nav[data-variant='side'] a[aria-current='page'] { box-shadow: inset 2px 0 0 var(--warm); }
  nav[data-variant='bottom'] {
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 10;
    border-top: 1px solid var(--line); overflow-x: auto; scrollbar-width: none;
    padding: 4px 4px calc(4px + env(safe-area-inset-bottom));
  }
  nav[data-variant='bottom'] a { flex: 1 0 64px; font-size: 10.5px; white-space: nowrap; }
  nav[data-variant='bottom'] a[aria-current='page'] { box-shadow: inset 0 2px 0 var(--warm); }
</style>
```

Check: `registry.test.js` compares `a.textContent` with the translated label. The `<svg>` has no
text nodes, so it still matches; keep no whitespace between `</svg>` and the label expression.

- [ ] **Step 6: `frontend/src/app/Statusbar.svelte`** — keep the whole `<script>` block as is, add the theme imports and the pulse, and replace markup and style:

Add to the script:

```js
  import { resolvedTheme, setTheme } from '../lib/theme.js';
  const nextTheme = $derived($resolvedTheme === 'night' ? 'day' : 'night');
  // Restart the pulse animation on every new device message.
  let pulseKey = $derived($deviceState?.last_device_message ?? 0);
  let firmware = $derived($profile?.firmware?.value ?? null);
```

Markup:

```svelte
<div class="status" data-testid="status-bar">
  <span class="item" data-testid="device-status" class:value-stale={offline}>
    {#key pulseKey}<span class="pulse" class:off={$deviceState?.device_online !== 'online'} aria-hidden="true"></span>{/key}
    <span class="val">{deviceLabel}</span>
    {#if offline}<span class="tag age">{ageText}</span>{/if}
  </span>
  <span class="item tag" data-testid="last-message">{translate($language, 'common.lastMessage')}: {ageText}</span>
  <span class="item" data-testid="operating-mode" class:value-stale={offline}><span class="tag">{translate($language, 'common.operatingMode')}</span> <span class="val">{mode}</span></span>
  <span class="item hide-m" data-testid="activity" class:value-stale={offline}><span class="tag">{translate($language, 'common.activity')}</span> <span class="val">{activity}</span></span>
  <span class="item hide-m" data-testid="error-code" class:value-stale={offline}><span class="tag">{translate($language, 'common.errorCode')}</span> <span class="val">{errorLabel}</span></span>
  <span class="item hide-m" data-testid="broker-status"><span class="tag">MQTT</span> <span class="val">{brokerLabel}</span></span>
  {#if firmware}<span class="item hide-m"><span class="tag">HeishaMon</span> <span class="val">{firmware}</span></span>{/if}
  <span class="grow"></span>
  {#if $system && $system.last_flush_ok === false}
    <span class="item flush" data-testid="flush-error">
      {translate($language, 'common.flushFailed')}{ $system.last_flush_error ? `: ${$system.last_flush_error}` : ''}
    </span>
  {/if}
  <button
    type="button"
    class="chip"
    class:locked={$prefs?.write_lock === true}
    class:unlocked={$prefs?.write_lock === false}
    data-testid="write-lock"
    aria-pressed={$prefs?.write_lock === true}
    disabled={$prefs == null}
    onclick={toggleWriteLock}
  >
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 11h14v9H5zM8 11V8a4 4 0 0 1 8 0v3" /></svg>
    {translate($language, 'common.writeLock')}:
    {$prefs?.write_lock ? translate($language, 'common.writeLockOn') : translate($language, 'common.writeLockOff')}
  </button>
  <button type="button" class="chip" data-testid="theme-toggle" title={translate($language, 'common.themeToggle')} onclick={() => setTheme(nextTheme)}>
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 8a4 4 0 1 0 0 8 4 4 0 1 0 0-8M12 3v2M12 19v2M3 12h2M19 12h2" /></svg>
    {translate($language, nextTheme === 'day' ? 'common.themeDay' : 'common.themeNight')}
  </button>
  <div class="langs" data-testid="language-switch" role="group" aria-label={translate($language, 'common.language')}>
    <button type="button" class="chip" data-testid="lang-en" aria-pressed={$language === 'en'} onclick={() => language.set('en')}>
      {translate($language, 'common.langEn')}
    </button>
    <button type="button" class="chip" data-testid="lang-nl" aria-pressed={$language === 'nl'} onclick={() => language.set('nl')}>
      {translate($language, 'common.langNl')}
    </button>
  </div>
</div>

<style>
  .status {
    display: flex; flex-wrap: wrap; align-items: center; gap: 8px 18px;
    padding: 10px 24px; border-bottom: 1px solid var(--line); background: var(--ground);
    position: sticky; top: 0; z-index: 5; min-width: 0;
  }
  .item { display: inline-flex; align-items: baseline; gap: 7px; white-space: nowrap; }
  .val { font: 500 12.5px var(--font-data); font-stretch: 87.5%; }
  .grow { flex: 1; }
  .pulse { width: 8px; height: 8px; border-radius: 50%; background: var(--ok); align-self: center; animation: beat .9s ease-out; }
  .pulse.off { background: var(--ink-3); animation: none; }
  @keyframes beat { from { box-shadow: 0 0 0 0 color-mix(in srgb, var(--ok) 70%, transparent); } to { box-shadow: 0 0 0 8px transparent; } }
  .chip { display: inline-flex; align-items: center; gap: 7px; padding: 5px 10px; border-radius: 999px; font-size: 12.5px; }
  .chip svg { width: 14px; height: 14px; stroke: currentColor; fill: none; stroke-width: 1.8; }
  .chip.locked { border-color: color-mix(in srgb, var(--ok) 55%, var(--line-2)); }
  .chip.unlocked { border-color: var(--pending); color: var(--pending-ink); }
  .langs { display: inline-flex; gap: 4px; }
  .flush { color: var(--fail-ink); }
  @media (max-width: 759px) {
    .status { padding: 8px 14px; gap: 8px 12px; }
    .hide-m { display: none; }
  }
</style>
```

Note: `common.lastMessage` stays as label text; the existing tests read the text content of these
test ids — run them and adapt only selectors that broke because of the label/value split, never the
asserted values.

- [ ] **Step 7: `frontend/src/app/App.svelte`** — script unchanged except the breakpoint (`>= 760` in both places). Markup and style:

```svelte
<div class="app" data-testid="shell" data-layout={navVariant}>
  <Nav variant={navVariant} />
  <div class="column">
    <h1 class="sr-only">{translate($language, 'common.brand')}</h1>
    <Statusbar />
    <main>
      <Screen />
    </main>
  </div>
  <ConfirmDialog
    open={$confirmRequest !== null}
    title={$confirmRequest?.title ?? translate($language, 'common.confirmTitle')}
    body={$confirmRequest?.body ?? translate($language, 'common.confirmBody')}
    confirmLabel={translate($language, 'common.confirm')}
    cancelLabel={translate($language, 'common.cancel')}
    onconfirm={() => answerConfirm(true)}
    oncancel={() => answerConfirm(false)}
  />
</div>

<style>
  .app { min-height: 100vh; display: flex; }
  .app[data-layout='bottom'] { display: block; }
  .column { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  main { flex: 1; min-width: 0; padding: 22px 24px 48px; }
  .app[data-layout='bottom'] main { padding: 16px 12px 96px; }
  .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
</style>
```

Remove the old `:global(body)` and `:global(.value-stale)` rules (now in `app.css`).

- [ ] **Step 8: Run full Vitest** → PASS. Fix only selectors broken by the markup change.
- [ ] **Step 9: Visual check** — `npm --prefix frontend run build`, start the simulator stack as in the README (or `cd frontend && npx playwright test e2e/screens.spec.js -g "overview loads" ` for a smoke), open at 1280 px and 390 px, compare the rail/status strip with the mockup.
- [ ] **Step 10: Commit** — done by the orchestrator after the wave is accepted; builders never commit. Write the build report instead.

---

### Task 4: Plant model and geometry

- Wave: 2
- Dependencies: Task 1
- Owned files: frontend/src/features/overview/plant.js, frontend/tests/plant.test.js, frontend/src/lib/i18n/overview.en.js, frontend/src/lib/i18n/overview.nl.js
- Shared mutable paths: /tmp/vite-<attempt-id>
- Exclusive resources: none
- Consumed interfaces: activityOf (format.js)
- Produced interfaces: plantModel(state, profile), plantGeometry(model); all new overview.* i18n keys
- Acceptance criteria: every step below done; its tests and the full Vitest suite PASS; no file outside the owned files changed
- Validation: `VITE_CACHE_DIR=/tmp/vite-<attempt-id> npm --prefix frontend run test` (full suite) plus the step-specific commands below
- Report pattern: reports/build/T4--<attempt-id>.md

**Files:**
- Modify: `frontend/src/lib/i18n/overview.en.js`, `overview.nl.js` (all new Overview keys, Step 0)
- Create: `frontend/src/features/overview/plant.js`
- Test: `frontend/tests/plant.test.js`

**Interfaces:**
- Consumes: `activityOf` (format.js).
- Produces:
  - `plantModel(state, profile) → { activity, outside, compressor, flow, ret, target, deltaT, pumpFlow, flowing, flowPeriod, fanSpinning, valve: 'room'|'dhw', zones: [{id:'z1'|'z2', water}], dhw: {temp, target}|null, buffer: {temp}|null, controlMode: 'curve'|'direct'|null }`
  - `plantGeometry(model) → { emitters: [{id, x, y, w, h, inX, outX}], zoneFlow: string, zoneReturn: string, dhwFlow: string|null, dhwReturn: string|null, buffer: {x, y, w, h}|null }` (SVG path strings in the schematic's viewBox `0 40 960 345`).

- [ ] **Step 0: All new Overview strings (for Tasks 4–9)** — append these keys to the default export of `frontend/src/lib/i18n/overview.en.js` and `overview.nl.js` (Tasks 5–8 run in one wave and must not edit these files). Run `VITE_CACHE_DIR=/tmp/vite-<attempt-id> npm --prefix frontend run test -- i18n` → PASS (key parity).

```js
// en
plantLabel: 'Live diagram of the installation',
plantOutdoor: 'OUTDOOR UNIT',
plantIndoor: 'INDOOR UNIT',
plantRefrigerant: 'REFRIGERANT',
plantHex: 'HEAT EXCHANGER',
plantValve: '3-WAY',
plantZone: 'ZONE {n}',
plantTank: 'DHW TANK',
plantBuffer: 'BUFFER',
tagOutside: 'OUTSIDE',
tagFlow: 'FLOW · TARGET {t}',
tagFlowNoTarget: 'FLOW',
tagReturn: 'RETURN · ΔT {dt} K',
tagTarget: 'TARGET {t}',
subZones: 'zone {z}',
subCurve: 'curve',
subDirect: 'direct',
subDhw: 'tank {t} → {target} °C',
tempScale: 'Colour scale',
nowTitle: 'Efficiency now',
powerOutIn: '{out} kW out / {in} kW in',
fromGrid: 'electricity',
fromAir: 'from outside air',
pump: 'Pump',
nowHeating: 'Heating',
nowDhw: 'DHW',
nowCooling: 'Cooling',
today: 'Today',
todayCop: 'COP today',
kwhIn: 'kWh in',
timelineTitle: 'Last 24 hours',
now: 'now',
lineFlow: 'flow',
lineReturn: 'return',
lineOutside: 'outside',
lineTarget: 'target',
linePower: 'power in',
timelineEmpty: 'No history for the last 24 hours yet.',
timelineApprox: 'Activity is approximate (from 1-minute averages)',
timelineIncomplete: 'History incomplete',
activityUnknown: 'unknown',
miniCurveHeat: 'Heating curve, zone {n}',
miniCurveCool: 'Cooling curve, zone {n}',
openCurve: 'Open',
miniControlUnknown: 'Control mode unknown',
miniSetpointUnavailable: 'Setpoint unavailable',
recentEvents: 'Events',
openLog: 'Log',
noEvents: 'No events yet.',
pinnedTiles: 'Pinned',
// nl
plantLabel: 'Live schema van de installatie',
plantOutdoor: 'BUITENUNIT',
plantIndoor: 'BINNENUNIT',
plantRefrigerant: 'KOUDEMIDDEL',
plantHex: 'WARMTEWISSELAAR',
plantValve: '3-WEG',
plantZone: 'ZONE {n}',
plantTank: 'SWW-BOILER',
plantBuffer: 'BUFFER',
tagOutside: 'BUITEN',
tagFlow: 'AANVOER · DOEL {t}',
tagFlowNoTarget: 'AANVOER',
tagReturn: 'RETOUR · ΔT {dt} K',
tagTarget: 'DOEL {t}',
subZones: 'zone {z}',
subCurve: 'stooklijn',
subDirect: 'direct',
subDhw: 'boiler {t} → {target} °C',
tempScale: 'Kleurschaal',
nowTitle: 'Rendement nu',
powerOutIn: '{out} kW uit / {in} kW in',
fromGrid: 'stroom',
fromAir: 'uit buitenlucht',
pump: 'Pomp',
nowHeating: 'Verwarmen',
nowDhw: 'Warm water',
nowCooling: 'Koelen',
today: 'Vandaag',
todayCop: 'COP vandaag',
kwhIn: 'kWh in',
timelineTitle: 'Afgelopen 24 uur',
now: 'nu',
lineFlow: 'aanvoer',
lineReturn: 'retour',
lineOutside: 'buiten',
lineTarget: 'doel',
linePower: 'vermogen in',
timelineEmpty: 'Nog geen geschiedenis van de afgelopen 24 uur.',
timelineApprox: 'Activiteit is een benadering (uit minuutgemiddelden)',
timelineIncomplete: 'Geschiedenis onvolledig',
activityUnknown: 'onbekend',
miniCurveHeat: 'Stooklijn zone {n}',
miniCurveCool: 'Koellijn zone {n}',
openCurve: 'Openen',
miniControlUnknown: 'Regelmodus onbekend',
miniSetpointUnavailable: 'Setpoint niet beschikbaar',
recentEvents: 'Gebeurtenissen',
openLog: 'Logboek',
noEvents: 'Nog geen gebeurtenissen.',
pinnedTiles: 'Vastgezet',
```

- [ ] **Step 1: Failing test** `frontend/tests/plant.test.js`

```js
import { describe, expect, it } from 'vitest';
import { plantGeometry, plantModel } from '../src/features/overview/plant.js';

const F = (value, unknown = false) => ({ value, unknown, stale: false });
const T = (value, sentinel = false) => ({ value, sentinel });
const baseProfile = { zones: F('z1'), dhw_installed: F(true), buffer_installed: F(false), operating_mode: F(4), heating_control: F('curve') };
const state = (topics) => ({ topics });

describe('plantModel', () => {
  it('reads the live values and derives ΔT and flow', () => {
    const m = plantModel(state({
      'main/Outside_Temp': T(6.3), 'main/Compressor_Freq': T(34), 'main/Main_Outlet_Temp': T(35.2),
      'main/Main_Inlet_Temp': T(30.4), 'main/Main_Target_Temp': T(35), 'main/Pump_Flow': T(14.8),
      'main/ThreeWay_Valve_State': T(0), 'main/Heatpump_State': T(1), 'main/Defrosting_State': T(0),
      'main/DHW_Temp': T(48.6), 'main/DHW_Target_Temp': T(52),
    }), baseProfile);
    expect(m.deltaT).toBeCloseTo(4.8);
    expect(m.flowing).toBe(true);
    expect(m.flowPeriod).toBeCloseTo(18 / 14.8);
    expect(m.fanSpinning).toBe(true);
    expect(m.valve).toBe('room');
    expect(m.dhw).toEqual({ temp: 48.6, target: 52 });
    expect(m.zones).toEqual([{ id: 'z1', water: null }]);
    expect(m.controlMode).toBe('curve');
  });
  it('treats sentinels as missing', () => {
    const m = plantModel(state({ 'main/Outside_Temp': T(-128, true), 'main/Pump_Flow': T(0) }), baseProfile);
    expect(m.outside).toBe(null);
    expect(m.flowing).toBe(false);
    expect(m.flowPeriod).toBe(null);
  });
  it('follows the profile: no tank, two zones, buffer', () => {
    const m = plantModel(state({}), { ...baseProfile, zones: F('both'), dhw_installed: F(false), buffer_installed: F(true) });
    expect(m.dhw).toBe(null);
    expect(m.zones.map((z) => z.id)).toEqual(['z1', 'z2']);
    expect(m.buffer).toEqual({ temp: null });
  });
  it('shows the tank and zone 1 when the profile is unknown', () => {
    const m = plantModel(state({}), { zones: F(null, true), dhw_installed: F(null, true) });
    expect(m.dhw).not.toBe(null);
    expect(m.zones.map((z) => z.id)).toEqual(['z1']);
  });
  it('ignores the DHW valve position when there is no tank', () => {
    const m = plantModel(state({ 'main/ThreeWay_Valve_State': T(1) }), { ...baseProfile, dhw_installed: F(false) });
    expect(m.valve).toBe('room');
  });
  it('names the cooling control while cooling', () => {
    const m = plantModel(state({ 'main/Heatpump_State': T(1), 'main/Defrosting_State': T(0), 'main/ThreeWay_Valve_State': T(0) }),
      { ...baseProfile, operating_mode: F(1), heating_control: F('curve'), cooling_control: F('direct') });
    expect(m.activity).toBe('cooling');
    expect(m.controlMode).toBe('direct');
  });
  it('stops the fan during defrost', () => {
    const m = plantModel(state({ 'main/Compressor_Freq': T(70), 'main/Defrosting_State': T(1) }), baseProfile);
    expect(m.activity).toBe('defrost');
    expect(m.fanSpinning).toBe(false);
  });
});

describe('plantGeometry', () => {
  it('draws one emitter per zone without overlap', () => {
    const one = plantGeometry(plantModel(state({}), baseProfile));
    expect(one.emitters).toHaveLength(1);
    const two = plantGeometry(plantModel(state({}), { ...baseProfile, zones: F('both') }));
    expect(two.emitters).toHaveLength(2);
    const [a, b] = two.emitters;
    expect(a.x + a.w).toBeLessThan(b.x);
  });
  it('omits the DHW pipes without a tank', () => {
    const g = plantGeometry(plantModel(state({}), { ...baseProfile, dhw_installed: F(false) }));
    expect(g.dhwFlow).toBe(null);
    expect(g.dhwReturn).toBe(null);
  });
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement `frontend/src/features/overview/plant.js`**

```js
/** What the plant schematic shows, derived from live state and the installation profile only. */
import { activityOf } from '../../lib/format.js';

const known = (field) => (field && !field.unknown ? field.value : undefined);

function num(state, key) {
  const topic = state?.topics?.[key];
  return topic && !topic.sentinel && typeof topic.value === 'number' ? topic.value : null;
}

export function plantModel(state, profile) {
  const zonesValue = known(profile?.zones);
  const zoneIds = zonesValue === 'both' ? ['z1', 'z2'] : zonesValue === 'z2' ? ['z2'] : ['z1'];
  const hasDhw = known(profile?.dhw_installed) !== false;
  const hasBuffer = known(profile?.buffer_installed) === true;
  const activity = activityOf(state, profile);
  const flow = num(state, 'main/Main_Outlet_Temp');
  const ret = num(state, 'main/Main_Inlet_Temp');
  const pumpFlow = num(state, 'main/Pump_Flow');
  const flowing = pumpFlow !== null && pumpFlow > 0;
  const compressor = num(state, 'main/Compressor_Freq');
  const heatingUse = known(profile?.heating_in_use);
  const coolingOnly = heatingUse === false && known(profile?.cooling_in_use) === true;
  // the qualifier names the control of what runs now: cooling while cooling, else heating
  const coolingNow = activity === 'cooling' || coolingOnly;
  return {
    activity,
    outside: num(state, 'main/Outside_Temp'),
    compressor,
    flow,
    ret,
    target: num(state, 'main/Main_Target_Temp'),
    deltaT: flow !== null && ret !== null ? flow - ret : null,
    pumpFlow,
    flowing,
    // seconds per dash cycle: faster with more flow, within a calm range
    flowPeriod: flowing ? Math.min(4, Math.max(0.4, 18 / pumpFlow)) : null,
    fanSpinning: compressor !== null && compressor > 0 && activity !== 'defrost',
    valve: hasDhw && num(state, 'main/ThreeWay_Valve_State') === 1 ? 'dhw' : 'room',
    zones: zoneIds.map((id) => ({ id, water: num(state, `main/${id.toUpperCase()}_Water_Temp`) })),
    dhw: hasDhw ? { temp: num(state, 'main/DHW_Temp'), target: num(state, 'main/DHW_Target_Temp') } : null,
    buffer: hasBuffer ? { temp: num(state, 'main/Buffer_Temp') } : null,
    controlMode: known(coolingNow ? profile?.cooling_control : profile?.heating_control) ?? null,
  };
}

/** Pipe paths and equipment boxes in the viewBox `0 40 960 345` (valve at 600,110; indoor unit right edge x=500). */
export function plantGeometry(model) {
  const two = model.zones.length === 2;
  const emitters = two
    ? [
        { id: model.zones[0].id, x: 730, y: 130, w: 80, h: 80 },
        { id: model.zones[1].id, x: 850, y: 130, w: 80, h: 80 },
      ]
    : [{ id: model.zones[0].id, x: 840, y: 130, w: 80, h: 80 }];
  for (const e of emitters) {
    e.inX = e.x + 20;
    e.outX = e.x + e.w - 20;
  }
  const last = emitters[emitters.length - 1];
  const zoneFlow = [`M600 110 H${last.inX} V130`, ...emitters.slice(0, -1).map((e) => `M${e.inX} 110 V130`)].join(' ');
  const zoneReturn = [`M${last.outX} 210 V230 H500`, ...emitters.slice(0, -1).map((e) => `M${e.outX} 210 V230`)].join(' ');
  return {
    emitters,
    zoneFlow,
    zoneReturn,
    dhwFlow: model.dhw ? 'M600 110 V290 H780' : null,
    dhwReturn: model.dhw ? 'M780 350 H500' : null,
    buffer: model.buffer ? { x: 640, y: 92, w: 60, h: 36 } : null,
  };
}
```

- [ ] **Step 4: Run** `VITE_CACHE_DIR=/tmp/vite-<attempt-id> npm --prefix frontend run test -- plant` → PASS.
- [ ] **Step 5: Commit** — done by the orchestrator after the wave is accepted; builders never commit. Write the build report instead.

---

### Task 5: Plant schematic component

- Wave: 3
- Dependencies: Task 1, Task 4
- Owned files: frontend/src/features/overview/PlantSchematic.svelte, frontend/tests/plant-schematic.test.js
- Shared mutable paths: /tmp/vite-<attempt-id>
- Exclusive resources: none
- Consumed interfaces: plantModel, plantGeometry, tempColor, ACTIVITY_VAR, activityLabel, overview.* keys
- Produced interfaces: <PlantSchematic stateData profile lang /> with data-testid plant, plant-<reading>, plant-zone-<id>, plant-dhw-branch
- Acceptance criteria: every step below done; its tests and the full Vitest suite PASS; no file outside the owned files changed
- Validation: `VITE_CACHE_DIR=/tmp/vite-<attempt-id> npm --prefix frontend run test` (full suite) plus the step-specific commands below
- Report pattern: reports/build/T5--<attempt-id>.md

**Files:**
- Create: `frontend/src/features/overview/PlantSchematic.svelte`
- Test: `frontend/tests/plant-schematic.test.js`

**Interfaces:**
- Consumes: `plantModel`, `plantGeometry` (Task 4), `tempColor`, `ACTIVITY_VAR` (Task 1), `activityLabel` (format.js).
- Produces: `<PlantSchematic stateData profile lang />` with `data-testid="plant"`, readings `data-testid="plant-<name>"` for `outside, compressor, flow, return, pump, dhw`, and `data-testid="plant-zone-<id>"`, `data-testid="plant-dhw-branch"`, `data-testid="plant-buffer"`.

- [ ] **Step 1: i18n keys** — already added by Task 4 to `overview.en.js` / `overview.nl.js`. Check with `grep -n 'plantLabel' frontend/src/lib/i18n/overview.en.js`. Do not edit the i18n files in this task.

- [ ] **Step 2: Failing test** `frontend/tests/plant-schematic.test.js`

```js
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import PlantSchematic from '../src/features/overview/PlantSchematic.svelte';

const F = (value) => ({ value, unknown: false, stale: false });
const T = (value) => ({ value, sentinel: false });
const profile = { zones: F('z1'), dhw_installed: F(true), buffer_installed: F(false), operating_mode: F(4), heating_control: F('curve') };
const live = { topics: {
  'main/Outside_Temp': T(6.3), 'main/Compressor_Freq': T(34), 'main/Main_Outlet_Temp': T(35.2),
  'main/Main_Inlet_Temp': T(30.4), 'main/Main_Target_Temp': T(35), 'main/Pump_Flow': T(14.8),
  'main/ThreeWay_Valve_State': T(0), 'main/Heatpump_State': T(1), 'main/Defrosting_State': T(0),
  'main/DHW_Temp': T(48.6), 'main/DHW_Target_Temp': T(52),
} };

describe('PlantSchematic', () => {
  it('shows the readings', () => {
    render(PlantSchematic, { stateData: live, profile, lang: 'en' });
    expect(screen.getByTestId('plant-outside').textContent).toBe('6.3°');
    expect(screen.getByTestId('plant-flow').textContent).toBe('35.2°');
    expect(screen.getByTestId('plant-return').textContent).toBe('30.4°');
    expect(screen.getByTestId('plant-compressor').textContent).toBe('34');
    expect(screen.getByTestId('plant-pump').textContent).toBe('14.8');
    expect(screen.getByTestId('plant-dhw').textContent).toBe('48.6°');
    expect(screen.getByTestId('plant').textContent).toContain('Heating');
  });
  it('dims the DHW branch while the valve points at the room', () => {
    render(PlantSchematic, { stateData: live, profile, lang: 'en' });
    expect(screen.getByTestId('plant-dhw-branch').getAttribute('data-active')).toBe('false');
  });
  it('hides the tank when the profile has none', () => {
    render(PlantSchematic, { stateData: live, profile: { ...profile, dhw_installed: F(false) }, lang: 'en' });
    expect(screen.queryByTestId('plant-dhw-branch')).toBe(null);
  });
  it('draws two zones', () => {
    render(PlantSchematic, { stateData: live, profile: { ...profile, zones: F('both') }, lang: 'nl' });
    expect(screen.getByTestId('plant-zone-z1')).toBeTruthy();
    expect(screen.getByTestId('plant-zone-z2')).toBeTruthy();
  });
  it('draws the buffer tank with its temperature when the profile has one', () => {
    const withBuffer = { topics: { ...live.topics, 'main/Buffer_Temp': T(41.5) } };
    render(PlantSchematic, { stateData: withBuffer, profile: { ...profile, buffer_installed: F(true) }, lang: 'en' });
    expect(screen.getByTestId('plant-buffer').textContent).toContain('41.5°');
  });
  it('has no buffer without one in the profile', () => {
    render(PlantSchematic, { stateData: live, profile, lang: 'en' });
    expect(screen.queryByTestId('plant-buffer')).toBe(null);
  });
  it('shows a dash for a missing reading', () => {
    render(PlantSchematic, { stateData: { topics: {} }, profile, lang: 'en' });
    expect(screen.getByTestId('plant-outside').textContent).toBe('—');
  });
});
```

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Implement `frontend/src/features/overview/PlantSchematic.svelte`** (geometry copied from the mockup; zone/tank/buffer parts come from `plantGeometry`)

```svelte
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
  <div class="scroll">
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
```

When the scroll container first mounts on a phone, scroll it to the water side
(`scrollLeft = (scrollWidth - clientWidth) * 0.65`) in an `$effect` that runs once on mount.

- [ ] **Step 5: Run** `VITE_CACHE_DIR=/tmp/vite-<attempt-id> npm --prefix frontend run test -- plant-schematic` → PASS.
- [ ] **Step 6: Commit** — done by the orchestrator after the wave is accepted; builders never commit. Write the build report instead.

---

### Task 6: Now panel

- Wave: 3
- Dependencies: Task 1, Task 4
- Owned files: frontend/src/features/overview/NowPanel.svelte, frontend/src/lib/domain/power.js, frontend/tests/now-panel.test.js
- Shared mutable paths: /tmp/vite-<attempt-id>
- Exclusive resources: none
- Consumed interfaces: liveCop, powerPairs, api.energy, overview.* keys
- Produced interfaces: <NowPanel stateData profile lang />, todayTotals(result)
- Acceptance criteria: every step below done; its tests and the full Vitest suite PASS; no file outside the owned files changed
- Validation: `VITE_CACHE_DIR=/tmp/vite-<attempt-id> npm --prefix frontend run test` (full suite) plus the step-specific commands below
- Report pattern: reports/build/T6--<attempt-id>.md

**Files:**
- Create: `frontend/src/features/overview/NowPanel.svelte`
- Test: `frontend/tests/now-panel.test.js`

**Interfaces:**
- Consumes: `liveCop`, `powerPairs` (domain/power.js; this task adds the `mode` argument to `liveCop`); `activityOf` (format.js); `api.energy`.
- Produces: `<NowPanel stateData profile lang />` with test ids `now-cop`, `now-power`, `now-compressor`, `now-pump`, `now-today` (absent when no data).
- Produces (pure, exported from `<script module>`): `todayLabel(energyResponse) → 'YYYY-MM-DD'|null`, `todayTotals(energyResponse) → {consumed, produced, cop}|null`, `nowMode(activity) → 'heat'|'dhw'|'cool'`.
- Produces: `liveCop(values, profile, mode = 'heat')` in `frontend/src/lib/domain/power.js`.

- [ ] **Step 1: i18n keys** — already added by Task 4 to `overview.en.js` / `overview.nl.js`. Check with `grep -n 'nowTitle' frontend/src/lib/i18n/overview.en.js`. Do not edit the i18n files in this task.

- [ ] **Step 2: Failing test** `frontend/tests/now-panel.test.js`

```js
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/svelte';
import NowPanel, { nowMode, todayLabel, todayTotals } from '../src/features/overview/NowPanel.svelte';
import { api } from '../src/lib/api.js';

const F = (value) => ({ value, unknown: false, stale: false });
const T = (value) => ({ value, sentinel: false, last_change: 1, last_seen: 1, retained_only: false });
const profile = { has_extra: F(false) };
const live = { topics: {
  'main/Heat_Power_Production': T(2710), 'main/Heat_Power_Consumption': T(620),
  'main/Compressor_Freq': T(34), 'main/Pump_Flow': T(14.8),
} };

afterEach(() => vi.restoreAllMocks());

// 2026-10-14 10:00 Europe/Amsterdam
const TO = Date.UTC(2026, 9, 14, 8, 0);

describe('todayTotals', () => {
  it('sums today (server-local date of `to`) over all modes', () => {
    const r = todayTotals({ tz: 'Europe/Amsterdam', to: TO, periods: {
      '2026-10-13': { heat: { production_kwh: 1, consumption_kwh: 1 } },
      '2026-10-14': { heat: { production_kwh: 24, consumption_kwh: 6 }, dhw: { production_kwh: 6, consumption_kwh: 2 } },
    } });
    expect(r).toEqual({ consumed: 8, produced: 30, cop: 3.75 });
  });
  it('uses the server time zone for the date', () => {
    // 23:30 UTC on the 13th is already the 14th in Amsterdam
    expect(todayLabel({ tz: 'Europe/Amsterdam', to: Date.UTC(2026, 9, 13, 23, 30) })).toBe('2026-10-14');
  });
  it('returns null when today has no period, or without data', () => {
    expect(todayTotals({ tz: 'Europe/Amsterdam', to: TO, periods: { '2026-10-13': { heat: { production_kwh: 1, consumption_kwh: 1 } } } })).toBe(null);
    expect(todayTotals(null)).toBe(null);
    expect(todayTotals({ periods: {} })).toBe(null);
  });
});

describe('nowMode', () => {
  it('follows the activity', () => {
    expect(nowMode('dhw')).toBe('dhw');
    expect(nowMode('cooling')).toBe('cool');
    for (const a of ['heating', 'defrost', 'idle']) expect(nowMode(a)).toBe('heat');
  });
});

describe('NowPanel', () => {
  it('shows COP, power and today', async () => {
    vi.spyOn(api, 'energy').mockResolvedValue({ tz: 'Europe/Amsterdam', to: TO, periods: { '2026-10-14': { heat: { production_kwh: 24, consumption_kwh: 6 } } } });
    render(NowPanel, { stateData: live, profile, lang: 'en' });
    expect(screen.getByTestId('now-mode').textContent).toBe('Heating');
    expect(screen.getByTestId('now-cop').textContent).toBe('4.4');
    expect(screen.getByTestId('now-power').textContent).toBe('2.71 kW out / 0.62 kW in');
    expect(screen.getByTestId('now-compressor').textContent).toContain('34');
    await waitFor(() => expect(screen.getByTestId('now-today').textContent).toContain('6.0'));
  });
  it('shows a dash when COP cannot be computed and hides today on failure', async () => {
    vi.spyOn(api, 'energy').mockRejectedValue(new Error('x'));
    render(NowPanel, { stateData: { topics: {} }, profile, lang: 'en' });
    expect(screen.getByTestId('now-cop').textContent).toBe('—');
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByTestId('now-today')).toBe(null);
  });
  it('shows the DHW pair during a DHW run', () => {
    vi.spyOn(api, 'energy').mockResolvedValue({ periods: {} });
    const dhw = { topics: { ...live.topics, 'main/ThreeWay_Valve_State': T(1),
      'main/DHW_Power_Production': T(3000), 'main/DHW_Power_Consumption': T(1000) } };
    render(NowPanel, { stateData: dhw, profile, lang: 'en' });
    expect(screen.getByTestId('now-mode').textContent).toBe('DHW');
    expect(screen.getByTestId('now-cop').textContent).toBe('3.0');
    expect(screen.getByTestId('now-power').textContent).toBe('3.00 kW out / 1.00 kW in');
  });
  it('shows the cooling pair as EER without the ambient bar', () => {
    vi.spyOn(api, 'energy').mockResolvedValue({ periods: {} });
    const cool = { topics: { 'main/Heatpump_State': T(1), 'main/Operating_Mode_State': T(1),
      'main/Cool_Power_Production': T(2000), 'main/Cool_Power_Consumption': T(500) } };
    render(NowPanel, { stateData: cool, profile: { ...profile, operating_mode: F(1) }, lang: 'en' });
    expect(screen.getByTestId('now-mode').textContent).toBe('Cooling');
    expect(screen.getByTestId('now-cop-label').textContent).toBe('EER');
    expect(screen.getByTestId('now-cop').textContent).toBe('4.0');
    expect(screen.queryByTestId('now-bar')).toBe(null);
  });
});

describe('liveCop mode argument', () => {
  it('keeps the heat default and selects other pairs', async () => {
    const { liveCop } = await import('../src/lib/domain/power.js');
    const v = { 'main/Heat_Power_Production': T(2000), 'main/Heat_Power_Consumption': T(500),
      'main/DHW_Power_Production': T(900), 'main/DHW_Power_Consumption': T(300) };
    expect(liveCop(v, profile).value).toBe(4);
    expect(liveCop(v, profile, 'dhw').value).toBe(3);
    expect(liveCop(v, profile, 'cool')).toBe(null);
  });
});
```

The keys match `backend/heishamon_dashboard/rules.json` `power_pairs.main` (heat, cool, dhw). Operating mode 1 is a cooling mode in `rules.json` `operating_modes.cooling`; verify with `jq .operating_modes backend/heishamon_dashboard/rules.json` and use a cooling mode from that list if it differs.

- [ ] **Step 2b: `liveCop` mode argument** — in `frontend/src/lib/domain/power.js` change the signature to `liveCop(values, profile, mode = 'heat')` and read `powerPairs(profile).pairs[mode]`; return `null` when that pair does not exist. Update the doc comment ("production / consumption of the chosen mode's pair"). Existing callers pass no mode and keep the heat behaviour.

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Implement `frontend/src/features/overview/NowPanel.svelte`**

```svelte
<script module>
  /** Server-local date (YYYY-MM-DD) of the response's `to`, in the response's time zone. */
  export function todayLabel(result) {
    if (!result?.tz || !Number.isFinite(result?.to)) return null;
    try {
      return new Intl.DateTimeFormat('en-CA', { timeZone: result.tz, year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(result.to));
    } catch {
      return null;
    }
  }

  /** kWh consumed/produced and COP for today's period of `GET /api/energy?period=day`, all modes summed. */
  export function todayTotals(result) {
    const label = todayLabel(result);
    const modes = label ? result?.periods?.[label] : null;
    if (!modes) return null;
    let consumed = 0;
    let produced = 0;
    for (const m of Object.values(modes ?? {})) {
      consumed += m?.consumption_kwh ?? 0;
      produced += m?.production_kwh ?? 0;
    }
    return { consumed, produced, cop: consumed > 0 ? produced / consumed : null };
  }

  /** Which power pair the panel shows for an activity. */
  export function nowMode(activity) {
    if (activity === 'dhw') return 'dhw';
    if (activity === 'cooling') return 'cool';
    return 'heat';
  }
</script>

<script>
  import { api } from '../../lib/api.js';
  import { translate } from '../../lib/i18n/index.js';
  import { activityOf } from '../../lib/format.js';
  import { liveCop, powerPairs } from '../../lib/domain/power.js';

  let { stateData = null, profile = null, lang = 'en' } = $props();
  const t = (key, params) => translate(lang, `overview.${key}`, params);

  function watts(key) {
    const tv = stateData?.topics?.[key];
    return tv && !tv.sentinel && typeof tv.value === 'number' ? tv.value : null;
  }
  const mode = $derived(nowMode(activityOf(stateData, profile)));
  const pair = $derived(powerPairs(profile).pairs[mode]);
  const out = $derived(watts(pair[0]));
  const inn = $derived(watts(pair[1]));
  const cop = $derived(liveCop(stateData?.topics, profile, mode));
  const showBar = $derived(mode !== 'cool' && out !== null && inn !== null && out > inn);
  const MODE_KEY = { heat: 'nowHeating', dhw: 'nowDhw', cool: 'nowCooling' };
  const freq = $derived(watts('main/Compressor_Freq'));
  const pump = $derived(watts('main/Pump_Flow'));
  const kw = (w) => (w === null ? '—' : (w / 1000).toFixed(2));
  const total = $derived(Math.max(out ?? 0, inn ?? 0) || 1);

  let today = $state(null);
  const ENERGY_REFRESH_MS = 15 * 60 * 1000;
  $effect(() => {
    let alive = true;
    const load = () => api.energy({ period: 'day' }).then((r) => { if (alive) today = todayTotals(r); }, () => { if (alive) today = null; });
    load();
    const timer = setInterval(load, ENERGY_REFRESH_MS);
    return () => { alive = false; clearInterval(timer); };
  });
</script>

<div class="panel now">
  <div class="top">
    <div class="tag">{t('nowTitle')} · <span data-testid="now-mode">{t(MODE_KEY[mode])}</span></div>
    <div class="cop">
      <span class="big" data-testid="now-cop">{cop ? cop.value.toFixed(1) : '—'}</span>
      <span class="lbl"><span data-testid="now-cop-label">{mode === 'cool' ? 'EER' : t('cop')}</span><span class="num sub" data-testid="now-power">{t('powerOutIn', { out: kw(out), in: kw(inn) })}</span></span>
    </div>
    {#if showBar}
      <div class="bar" data-testid="now-bar" aria-hidden="true">
        <i style:width={`${((inn ?? 0) / total) * 100}%`} style:background="var(--ink-2)"></i>
        <i style:width={`${(Math.max(0, (out ?? 0) - (inn ?? 0)) / total) * 100}%`} style:background="var(--cold)"></i>
      </div>
      <div class="bar-note"><span>{t('fromGrid')}</span><span>{t('fromAir')}</span></div>
    {/if}
  </div>
  <div class="kv">
    <div><div class="tag">{t('compressorFreq')}</div><div class="v" data-testid="now-compressor">{freq === null ? '—' : freq}<small>Hz</small></div></div>
    <div><div class="tag">{t('pump')}</div><div class="v" data-testid="now-pump">{pump === null ? '—' : pump.toFixed(1)}<small>l/min</small></div></div>
    {#if today}
      <div><div class="tag">{t('today')}</div><div class="v" data-testid="now-today">{today.consumed.toFixed(1)}<small>{t('kwhIn')}</small></div></div>
      <div><div class="tag">{t('todayCop')}</div><div class="v">{today.cop === null ? '—' : today.cop.toFixed(1)}</div></div>
    {/if}
  </div>
</div>

<style>
  .top { padding: 18px; }
  .cop { display: flex; align-items: baseline; gap: 10px; }
  .big { font: 400 64px/0.9 var(--font-data); font-stretch: 75%; letter-spacing: -.03em; font-variant-numeric: tabular-nums; }
  .lbl { display: flex; flex-direction: column; gap: 3px; color: var(--ink-2); font-size: 12.5px; }
  .sub { font-size: 11px; white-space: nowrap; color: var(--ink-3); }
  .bar { height: 6px; border-radius: 3px; background: var(--panel-2); display: flex; overflow: hidden; margin: 14px 0 6px; }
  .bar i { display: block; height: 100%; }
  .bar-note { display: flex; justify-content: space-between; color: var(--ink-3); font-size: 11.5px; }
  .kv { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1px; background: var(--line); border-top: 1px solid var(--line); }
  .kv > div { background: var(--panel); padding: 11px 16px; }
  .v { font: 500 18px/1.2 var(--font-data); font-stretch: 87.5%; margin-top: 3px; }
  .v small { font-size: 11px; color: var(--ink-3); margin-left: 3px; font-weight: 400; }
</style>
```

- [ ] **Step 5: Run** → PASS.
- [ ] **Step 6: Commit** — done by the orchestrator after the wave is accepted; builders never commit. Write the build report instead.

---

### Task 7: Timeline data and chart

- Wave: 3
- Dependencies: Task 1, Task 2, Task 4
- Owned files: frontend/src/features/overview/timeline.js, frontend/src/features/overview/Timeline24h.svelte, frontend/src/lib/uplot.js, frontend/vitest.config.js, frontend/tests/setup.js, frontend/tests/timeline.test.js, frontend/tests/timeline-chart.test.js, frontend/tests/charts.test.js (new cases only)
- Shared mutable paths: /tmp/vite-<attempt-id>
- Exclusive resources: none
- Consumed interfaces: activityFrom (Task 2), ACTIVITY_VAR, cssVar, resolvedTheme (Task 1), overview.* keys
- Produced interfaces: timelineTopics, pointValue, toGrid, activityRuns, STEP_MS; uplot buildSeries(series, Uplot), themedAxes(axes); <Timeline24h profile lang />
- Acceptance criteria: every step below done; its tests and the full Vitest suite PASS; no file outside the owned files changed
- Validation: `VITE_CACHE_DIR=/tmp/vite-<attempt-id> npm --prefix frontend run test` (full suite) plus the step-specific commands below
- Report pattern: reports/build/T7--<attempt-id>.md

**Files:**
- Create: `frontend/src/features/overview/timeline.js`, `frontend/src/features/overview/Timeline24h.svelte`, `frontend/tests/setup.js`, `frontend/tests/timeline-chart.test.js`
- Modify: `frontend/vitest.config.js` (`setupFiles`)
- Modify: `frontend/src/lib/uplot.js` (a `stepped` series flag; themed axes)
- Test: `frontend/tests/timeline.test.js`

**Interfaces:**
- Consumes: `activityFrom` (Task 2), `ACTIVITY_VAR` (Task 1), `cssVar`, `resolvedTheme` (Task 1), `createChart`, `timeAxes` (uplot.js), `powerPairs`.
- Produces: `STEP_MS`, `HISTORY_POINTS = 1500`; `timelineTopics(profile) → {outside, flow, ret, target, powerHeat, powerCool, powerDhw, defrost, valve, heatpump, mode}` (role → topic key); `powerSum(cols, topics) → (kW|null)[]`; `tempRange(columns) → [lo, hi]`; `pointValue(point, resolution) → {ts, v, w}|null`; `toGrid(history, topics, from, to, stepMs) → {xs: number[] /* slot starts, seconds */, cols: Record<topicKey, (number|null)[]>, truncated: topicKey[]}` with the spec R3.4 grid policy; `activityRuns(xs, cols, topics, stepSec = STEP_MS / 1000) → [{from, to, activity}]` using strict `activityFrom` (activity may be `'unknown'`).

- [ ] **Step 1: i18n keys** — already added by Task 4 to `overview.en.js` / `overview.nl.js`. Check with `grep -n 'timelineTitle' frontend/src/lib/i18n/overview.en.js`. Do not edit the i18n files in this task.

- [ ] **Step 2: Failing test** `frontend/tests/timeline.test.js`

```js
import { describe, expect, it } from 'vitest';
import { HISTORY_POINTS, STEP_MS, activityRuns, pointValue, powerSum, tempRange, timelineTopics, toGrid } from '../src/features/overview/timeline.js';
import { modeSets } from '../src/lib/domain/rules.js';

const MIN = 60_000;
const heat = modeSets.heating[0];
const t = timelineTopics(null);
const H = (series, resolution = '1m') => ({ resolution, series });
const S = (points, extra = {}) => ({ kind: 'number', points, breaks: [], ...extra });

describe('pointValue', () => {
  it('reads raw and rollup points with their weight', () => {
    expect(pointValue([1, 5], 'raw')).toEqual({ ts: 1, v: 5, w: 1 });
    expect(pointValue([1, 5.5, 60], '1m')).toEqual({ ts: 1, v: 5.5, w: 60 });
    expect(pointValue([1, 5.5, 0], '1m')).toBe(null);
    expect(pointValue([1, null, 60], '1m')).toBe(null);
  });
});

describe('toGrid', () => {
  it('asks for enough points for a full day of minute buckets', () => {
    expect(HISTORY_POINTS).toBeGreaterThanOrEqual(1441);
  });
  it('keeps the first and the last hour of a full day', () => {
    const day = 24 * 3600 * 1000;
    const pts = [];
    for (let ts = 0; ts < day; ts += MIN) pts.push([ts, 20, 60]);
    const g = toGrid(H({ [t.outside]: S(pts) }), t, 0, day, STEP_MS);
    expect(g.xs).toHaveLength(288); // 288 five-minute slots covering [from, to), spec R3.4
    expect(g.cols[t.outside][0]).toBe(20);
    expect(g.cols[t.outside][287]).toBe(20);
  });
  it('weights temperatures by coverage', () => {
    const g = toGrid(H({ [t.flow]: S([[0, 10, 60], [MIN, 40, 1]]) }), t, 0, STEP_MS, STEP_MS);
    expect(g.cols[t.flow][0]).toBeCloseTo((10 * 60 + 40) / 61);
  });
  it('keeps a short defrost or DHW run', () => {
    const g = toGrid(H({ [t.defrost]: S([[0, 0, 60], [MIN, 0.1, 60]]), [t.valve]: S([[0, 0.05, 60]]) }), t, 0, STEP_MS, STEP_MS);
    expect(g.cols[t.defrost][0]).toBe(1);
    expect(g.cols[t.valve][0]).toBe(1);
  });
  it('takes the last integer mode and drops fractional ones', () => {
    expect(toGrid(H({ [t.mode]: S([[0, 4, 60], [MIN, 2.5, 60]]) }), t, 0, STEP_MS, STEP_MS).cols[t.mode][0]).toBe(4);
    expect(toGrid(H({ [t.mode]: S([[0, 2.5, 60], [MIN, 0.4, 60]]) }), t, 0, STEP_MS, STEP_MS).cols[t.mode][0]).toBe(null);
  });
  it('blanks slots inside a break, empty slots and missing series', () => {
    const g = toGrid(H({ [t.flow]: S([[0, 30, 60], [STEP_MS + MIN, 31, 60]], { breaks: [[STEP_MS, 2 * STEP_MS]] }) }), t, 0, 3 * STEP_MS, STEP_MS);
    expect(g.cols[t.flow]).toEqual([30, null, null]);
    expect(g.cols[t.ret]).toEqual([null, null, null]);
  });
  it('blanks a slot that only partly overlaps an outage', () => {
    const g = toGrid(H({ [t.flow]: S([[0, 30, 60], [3 * MIN, 31, 60]], { breaks: [[MIN, 2 * MIN]] }) }), t, 0, STEP_MS, STEP_MS);
    expect(g.cols[t.flow]).toEqual([null]);
  });
  it('reports truncated series', () => {
    const g = toGrid(H({ [t.flow]: S([[0, 30, 60]], { truncated: true }) }), t, 0, STEP_MS, STEP_MS);
    expect(g.truncated).toEqual([t.flow]);
  });
});

describe('activityRuns', () => {
  const cols = (d, v, h, m) => ({ [t.defrost]: d, [t.valve]: v, [t.heatpump]: h, [t.mode]: m });
  it('merges equal neighbours and keeps a short defrost', () => {
    expect(activityRuns([0, 300, 600, 900], cols([0, 0, 1, 0], [0, 0, 0, 0], [1, 1, 1, 1], [heat, heat, heat, heat]), t)).toEqual([
      { from: 0, to: 600, activity: 'heating' },
      { from: 600, to: 900, activity: 'defrost' },
      { from: 900, to: 1200, activity: 'heating' },
    ]);
  });
  it('is unknown when an input needed to exclude a higher priority is missing', () => {
    expect(activityRuns([0], cols([null], [0], [1], [heat]), t)[0].activity).toBe('unknown');
    expect(activityRuns([0], cols([0], [null], [1], [heat]), t)[0].activity).toBe('unknown');
    expect(activityRuns([0], cols([0], [0], [1], [null]), t)[0].activity).toBe('unknown');
    expect(activityRuns([0], cols([1], [null], [null], [null]), t)[0].activity).toBe('defrost');
  });
  it('shows why the band is labelled approximate', () => {
    // 30 s of mode 0 and 30 s of mode 2 (both heating) average to 1, a cooling mode
    expect(modeSets.cooling).toContain(1);
    const g = toGrid(H({ [t.mode]: S([[0, 1, 60]]), [t.defrost]: S([[0, 0, 60]]), [t.valve]: S([[0, 0, 60]]), [t.heatpump]: S([[0, 1, 60]]) }), t, 0, STEP_MS, STEP_MS);
    expect(activityRuns(g.xs, g.cols, t)[0].activity).toBe('cooling');
  });
});

describe('powerSum and tempRange', () => {
  it('sums the known consumption topics in kW', () => {
    const cols = { [t.powerHeat]: [1000, null, null], [t.powerCool]: [null, null, null], [t.powerDhw]: [500, 2000, null] };
    expect(powerSum(cols, t)).toEqual([1.5, 2, null]);
  });
  it('fits the temperature axis to the data, rounded out to 10 °C', () => {
    expect(tempRange([[-7.5, 20], [48, null]])).toEqual([-10, 50]);
    expect(tempRange([[20]])).toEqual([20, 30]);
    expect(tempRange([[null], []])).toEqual([0, 60]);
  });
});

describe('timelineTopics', () => {
  it('stays within the 20-topic history limit', () => {
    expect(Object.values(timelineTopics(null)).length).toBeLessThanOrEqual(20);
  });
});
```

If `modeSets.cooling` does not contain 1 in `rules.json`, pick two heating modes whose average is a cooling mode and keep the point of the test (a mixed minute can average to another valid mode); report the substitution.

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: Implement `frontend/src/features/overview/timeline.js`**

```js
/** 24 h timeline data (spec R3.4): minute buckets reduced to a 5-minute grid, and activity runs. */
import { activityFrom } from '../../lib/domain/activity.js';
import { powerPairs } from '../../lib/domain/power.js';

export const STEP_MS = 5 * 60 * 1000;
// 24 h is served at 1-minute resolution and the backend keeps the newest max_points: 1500 covers a day.
export const HISTORY_POINTS = 1500;

export function timelineTopics(profile) {
  return {
    outside: 'main/Outside_Temp',
    flow: 'main/Main_Outlet_Temp',
    ret: 'main/Main_Inlet_Temp',
    target: 'main/Main_Target_Temp',
    // total power in = heat + cool + DHW consumption (spec R3.4)
    powerHeat: powerPairs(profile).pairs.heat[1],
    powerCool: powerPairs(profile).pairs.cool[1],
    powerDhw: powerPairs(profile).pairs.dhw[1],
    defrost: 'main/Defrosting_State',
    valve: 'main/ThreeWay_Valve_State',
    heatpump: 'main/Heatpump_State',
    mode: 'main/Operating_Mode_State',
  };
}

/** One history point as {ts, v, w}: w is covered seconds (1 for raw points); null without a covered value. */
export function pointValue(point, resolution) {
  if (!Array.isArray(point)) return null;
  const v = point[1];
  if (typeof v !== 'number' || !Number.isFinite(v)) return null;
  if (resolution === 'raw') return { ts: point[0], v, w: 1 };
  return point[2] > 0 ? { ts: point[0], v, w: point[2] } : null;
}

const REDUCE = {
  mean(items) {
    const w = items.reduce((sum, p) => sum + p.w, 0);
    return w > 0 ? items.reduce((sum, p) => sum + p.v * p.w, 0) / w : null;
  },
  any: (items) => (items.some((p) => p.v > 0) ? 1 : 0),
  half: (items) => (items.some((p) => p.v >= 0.5) ? 1 : 0),
  lastInteger(items) {
    for (let i = items.length - 1; i >= 0; i--) {
      const r = Math.round(items[i].v);
      if (Math.abs(items[i].v - r) <= 0.01) return r;
    }
    return null;
  },
};
const ROLE_REDUCER = { defrost: 'any', valve: 'any', heatpump: 'half', mode: 'lastInteger' };

/** Reduce each topic to one value per slot [from + i·step, from + (i+1)·step). */
export function toGrid(history, topics, from, to, stepMs) {
  const n = Math.max(1, Math.ceil((to - from) / stepMs));
  const xs = Array.from({ length: n }, (_, i) => (from + i * stepMs) / 1000);
  const cols = {};
  const truncated = [];
  for (const [role, key] of Object.entries(topics)) {
    const series = history?.series?.[key];
    if (series?.truncated) truncated.push(key);
    const slots = Array.from({ length: n }, () => []);
    for (const point of series?.points ?? []) {
      const p = pointValue(point, history?.resolution);
      if (!p) continue;
      const i = Math.floor((p.ts - from) / stepMs);
      if (i >= 0 && i < n) slots[i].push(p);
    }
    const breaks = series?.breaks ?? [];
    const reduce = REDUCE[ROLE_REDUCER[role] ?? 'mean'];
    cols[key] = slots.map((items, i) => {
      const start = from + i * stepMs;
      if (!items.length || breaks.some(([s, e]) => s < start + stepMs && e > start)) return null;
      return reduce(items);
    });
  }
  return { xs, cols, truncated };
}

/** Total power in per slot in kW: the sum of the known consumption topics, null when none is known. */
export function powerSum(cols, topics) {
  const keys = [topics.powerHeat, topics.powerCool, topics.powerDhw];
  return (cols[keys[0]] ?? []).map((_, i) => {
    const vals = keys.map((k) => cols[k]?.[i]).filter((v) => typeof v === 'number');
    return vals.length ? vals.reduce((a, b) => a + b, 0) / 1000 : null;
  });
}

/** Temperature axis range: the plotted values rounded out to 10 °C; 0–60 without data. */
export function tempRange(columns) {
  const vals = columns.flat().filter((v) => typeof v === 'number' && Number.isFinite(v));
  if (!vals.length) return [0, 60];
  const lo = Math.floor(Math.min(...vals) / 10) * 10;
  const hi = Math.ceil(Math.max(...vals) / 10) * 10;
  return [lo, hi > lo ? hi : lo + 10];
}

/** Activity runs for the band, strict: a slot lacking a needed input is 'unknown' (drawn as a gap). */
export function activityRuns(xs, cols, topics, stepSec = STEP_MS / 1000) {
  const runs = [];
  for (let i = 0; i < xs.length; i++) {
    const activity = activityFrom({
      defrost: cols[topics.defrost]?.[i] ?? null,
      valve: cols[topics.valve]?.[i] ?? null,
      heatpump: cols[topics.heatpump]?.[i] ?? null,
      mode: cols[topics.mode]?.[i] ?? null,
    }, { strict: true });
    const last = runs[runs.length - 1];
    if (last && last.activity === activity && last.to === xs[i]) last.to = xs[i] + stepSec;
    else runs.push({ from: xs[i], to: xs[i] + stepSec, activity });
  }
  return runs;
}
```

- [ ] **Step 5: `frontend/src/lib/uplot.js`** — extract the series mapping so it can be tested, add a `stepped` flag and themed axes.

Add a failing test to `tests/charts.test.js` (import `buildSeries` and `themedAxes` next to `createChart`):

```js
describe('buildSeries', () => {
  const Fake = { paths: { stepped: () => 'STEPPED' } };
  it('prepends the x series and steps enum and stepped series', () => {
    const out = buildSeries([{ label: 'a' }, { label: 'b', enumBand: true }, { label: 'c', stepped: true }], Fake);
    expect(out[0]).toEqual({});
    expect(out[1].paths).toBeUndefined();
    expect(out[2].paths).toBe('STEPPED');
    expect(out[3].paths).toBe('STEPPED');
    expect('stepped' in out[3]).toBe(false);
  });
});

describe('themedAxes', () => {
  it('keeps explicit axis colours and fills the rest', () => {
    const [a, b] = themedAxes([{ stroke: 'red' }, {}]);
    expect(a.stroke).toBe('red');
    expect(b).toHaveProperty('grid');
    expect(b).toHaveProperty('ticks');
  });
});
```

Implementation in `frontend/src/lib/uplot.js`:

```js
import { cssVar } from './theme.js';

/** uPlot series: series[0] describes the x axis; enum bands and `stepped` series draw as steps. */
export function buildSeries(series = [], Uplot = null) {
  return [{}, ...series.map((s) => {
    const { enumBand, stepped, ...rest } = s;
    if ((enumBand || stepped) && Uplot?.paths?.stepped) rest.paths = Uplot.paths.stepped({ align: 1 });
    return rest;
  })];
}

/** Axes coloured from the current theme; explicit settings win. */
export function themedAxes(axes = []) {
  const ink = cssVar('--ink-3') || undefined;
  const line = cssVar('--line') || undefined;
  return axes.map((axis) => ({
    stroke: ink,
    grid: { stroke: line, width: 1 },
    ticks: { stroke: line, width: 1 },
    font: '10px "Martian Mono Variable", monospace',
    ...axis,
  }));
}
```

and in `createChart` replace the inline series mapping with
`const series = buildSeries(mergedOptions.series || [], Uplot);`.

- [ ] **Step 6a: jsdom chart harness.** jsdom has no canvas and no `ResizeObserver`, so a component that creates a real uPlot cannot be rendered in Vitest. Create `frontend/tests/setup.js` and register it in `frontend/vitest.config.js` (`test.setupFiles: ['tests/setup.js']`):

```js
import { vi } from 'vitest';

// jsdom has neither canvas nor ResizeObserver. Chart components get a no-op uPlot in every test file;
// a file that mocks 'uplot' itself (charts.test.js) overrides this. Real charts are checked in Playwright.
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

vi.mock('uplot', () => {
  class FakeUplot {
    constructor(opts, data, el) {
      this.opts = opts;
      this.data = data;
      this.el = el;
      this.cursor = { idx: null };
      this.destroyed = false;
      FakeUplot.instances.push(this);
    }
    setData(data) { this.data = data; }
    setSize() {}
    redraw() {}
    valToPos() { return 0; }
    destroy() { this.destroyed = true; }
  }
  FakeUplot.instances = [];
  FakeUplot.paths = { stepped: () => () => null };
  return { default: FakeUplot };
});
```

Run the full suite right after this step: every existing test must still pass. If an existing test file depended on the real uPlot, add `vi.unmock('uplot')` at the top of that file and report it.

- [ ] **Step 6b: Failing component test** `frontend/tests/timeline-chart.test.js`

```js
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/svelte';
import { flushSync } from 'svelte';
import uPlot from 'uplot';
import Timeline24h from '../src/features/overview/Timeline24h.svelte';
import { api } from '../src/lib/api.js';
import { setTheme } from '../src/lib/theme.js';

// createChart can be held open to simulate a slow chart build
const gate = vi.hoisted(() => ({ hold: null }));
vi.mock('../src/lib/uplot.js', async (importOriginal) => {
  const m = await importOriginal();
  return { ...m, createChart: async (...args) => { if (gate.hold) await gate.hold; return m.createChart(...args); } };
});

const MIN = 60_000;
afterEach(() => {
  gate.hold = null;
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function dayHistory(now, flow = 30, extra = {}) {
  const pts = [];
  for (let ts = now - 24 * 3600 * 1000; ts < now; ts += MIN) pts.push([ts, flow, 60]);
  return { resolution: '1m', series: { 'main/Main_Outlet_Temp': { kind: 'number', points: pts, breaks: [] }, ...extra } };
}
function deferred() {
  let resolve;
  const promise = new Promise((r) => { resolve = r; });
  return { promise, resolve };
}
const live = (from) => uPlot.instances.slice(from).filter((u) => !u.destroyed);

describe('Timeline24h', () => {
  it('asks for a full day, draws one chart and reads out the newest slot', async () => {
    const history = vi.spyOn(api, 'history').mockResolvedValue(dayHistory(Date.now()));
    const before = uPlot.instances.length;
    render(Timeline24h, { profile: null, lang: 'en' });
    await waitFor(() => expect(uPlot.instances.length).toBe(before + 1));
    expect(history.mock.calls[0][0].max_points).toBe(1500);
    const readout = screen.getByTestId('timeline-readout').textContent;
    expect(readout).toContain('now');
    expect(readout).toContain('30.0°');
    expect(screen.getByTestId('timeline-approx')).toBeTruthy();
  });
  it('destroys its chart on unmount', async () => {
    vi.spyOn(api, 'history').mockResolvedValue(dayHistory(Date.now()));
    const before = uPlot.instances.length;
    const { unmount } = render(Timeline24h, { profile: null, lang: 'en' });
    await waitFor(() => expect(uPlot.instances.length).toBe(before + 1));
    const chart = uPlot.instances.at(-1);
    unmount();
    expect(chart.destroyed).toBe(true);
  });
  it('reads out the slot under the cursor, including target and power, and "now" when it leaves', async () => {
    const now = Date.now();
    const target = [];
    const power = [];
    for (let ts = now - 24 * 3600 * 1000; ts < now; ts += MIN) { target.push([ts, 35, 60]); power.push([ts, 600, 60]); }
    vi.spyOn(api, 'history').mockResolvedValue(dayHistory(now, 30, {
      'main/Main_Target_Temp': { kind: 'number', points: target, breaks: [] },
      'main/Heat_Power_Consumption': { kind: 'number', points: power, breaks: [] },
    }));
    const before = uPlot.instances.length;
    render(Timeline24h, { profile: null, lang: 'en' });
    await waitFor(() => expect(uPlot.instances.length).toBe(before + 1));
    const chart = uPlot.instances.at(-1);
    chart.cursor.idx = 0;
    flushSync(() => chart.opts.hooks.setCursor[0](chart));
    const readout = screen.getByTestId('timeline-readout').textContent;
    expect(readout).not.toContain('now');
    expect(readout).toContain('35.0°');
    expect(readout).toContain('0.60 kW');
    chart.cursor.idx = null;
    flushSync(() => chart.opts.hooks.setCursor[0](chart));
    expect(screen.getByTestId('timeline-readout').textContent).toContain('now');
  });
  it('refreshes every five minutes', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const history = vi.spyOn(api, 'history').mockResolvedValue(dayHistory(Date.now()));
    render(Timeline24h, { profile: null, lang: 'en' });
    await waitFor(() => expect(history).toHaveBeenCalledTimes(1));
    await vi.advanceTimersByTimeAsync(5 * 60 * 1000);
    expect(history).toHaveBeenCalledTimes(2);
  });
  it('keeps the newest power source when responses arrive out of order', async () => {
    const first = deferred();
    const second = deferred();
    vi.spyOn(api, 'history').mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const F = (value) => ({ value, unknown: false, stale: false });
    const { rerender } = render(Timeline24h, { profile: { has_extra: F(false) }, lang: 'en' });
    await rerender({ profile: { has_extra: F(true) }, lang: 'en' });
    second.resolve(dayHistory(Date.now(), 40));
    await waitFor(() => expect(screen.getByTestId('timeline-readout').textContent).toContain('40.0°'));
    first.resolve(dayHistory(Date.now(), 30));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByTestId('timeline-readout').textContent).toContain('40.0°');
  });
  it('destroys a chart whose slow build is superseded by a theme switch, and one finished after unmount', async () => {
    setTheme('night');
    vi.spyOn(api, 'history').mockResolvedValue(dayHistory(Date.now()));
    const hold = deferred();
    gate.hold = hold.promise;
    const before = uPlot.instances.length;
    const { unmount } = render(Timeline24h, { profile: null, lang: 'en' });
    await waitFor(() => expect(screen.getByTestId('timeline-readout')).toBeTruthy());
    setTheme('day'); // second build starts while the first still waits
    flushSync();
    hold.resolve();
    await waitFor(() => expect(uPlot.instances.length).toBeGreaterThanOrEqual(before + 2));
    expect(live(before)).toHaveLength(1);
    const slow = deferred();
    gate.hold = slow.promise;
    setTheme('night');
    flushSync();
    unmount();
    slow.resolve();
    await new Promise((r) => setTimeout(r, 20));
    expect(live(before)).toHaveLength(0);
  });
  it('ignores a history response that arrives after unmount', async () => {
    let resolve;
    vi.spyOn(api, 'history').mockReturnValue(new Promise((r) => { resolve = r; }));
    const before = uPlot.instances.length;
    const { unmount } = render(Timeline24h, { profile: null, lang: 'en' });
    unmount();
    resolve(dayHistory(Date.now()));
    await new Promise((r) => setTimeout(r, 20));
    expect(uPlot.instances.length).toBe(before);
  });
});
```

- [ ] **Step 6c: Implement `frontend/src/features/overview/Timeline24h.svelte`** (load and render tokens follow `ChartContainer.svelte`: late responses and late charts are discarded)

```svelte
<script>
  import { onDestroy, untrack } from 'svelte';
  import { api } from '../../lib/api.js';
  import { translate } from '../../lib/i18n/index.js';
  import { activityLabel } from '../../lib/format.js';
  import { createChart, themedAxes, timeAxes } from '../../lib/uplot.js';
  import { cssVar, resolvedTheme } from '../../lib/theme.js';
  import { ACTIVITY_VAR } from '../../lib/ui/thermal.js';
  import { HISTORY_POINTS, STEP_MS, activityRuns, powerSum, tempRange, timelineTopics, toGrid } from './timeline.js';

  let { profile = null, lang = 'en' } = $props();
  const t = (key) => translate(lang, `overview.${key}`);
  const REFRESH_MS = 5 * 60 * 1000;
  const BAND = 12;
  const HEIGHT = 250;

  let host = $state(null);
  let data = $state(null); // { xs, cols, truncated, topics, runs, power }
  let cursor = $state(null);
  let chart = null;
  let loadToken = 0;
  let renderToken = 0;
  let alive = true;

  async function load(profileNow) {
    const token = ++loadToken;
    const to = Date.now();
    const from = to - 24 * 3600 * 1000;
    const topics = timelineTopics(profileNow);
    try {
      const history = await api.history({ topics: Object.values(topics), from, to, max_points: HISTORY_POINTS });
      if (!alive || token !== loadToken) return;
      const grid = toGrid(history, topics, from, to, STEP_MS);
      data = { ...grid, topics, runs: activityRuns(grid.xs, grid.cols, topics), power: powerSum(grid.cols, topics) };
    } catch {
      if (alive && token === loadToken) data = null;
    }
  }

  // Load now, when the power source (has_extra) changes, and every 5 minutes; never per live message.
  const extra = $derived(profile?.has_extra?.value === true);
  $effect(() => {
    void extra;
    untrack(() => load(profile));
    const timer = setInterval(() => untrack(() => load(profile)), REFRESH_MS);
    return () => {
      loadToken++;
      clearInterval(timer);
    };
  });

  function bandPlugin(runs) {
    return {
      hooks: {
        drawClear: [(u) => {
          const ctx = u.ctx;
          const dpr = devicePixelRatio || 1;
          const y = u.bbox.top - (BAND + 8) * dpr;
          for (const r of runs) {
            if (r.activity === 'unknown') continue; // drawn as a gap, never as idle
            const x0 = u.valToPos(r.from, 'x', true);
            const x1 = u.valToPos(r.to, 'x', true);
            ctx.fillStyle = cssVar(ACTIVITY_VAR[r.activity]);
            ctx.fillRect(x0, y, Math.max(1, x1 - x0), BAND * dpr);
          }
        }],
      },
    };
  }

  function destroyChart() {
    chart?.destroy();
    chart = null;
  }

  async function draw(d, el, language) {
    const token = ++renderToken;
    destroyChart();
    if (!el || !d) return;
    const { xs, cols, topics, runs, power } = d;
    const temps = [cols[topics.target], cols[topics.outside], cols[topics.ret], cols[topics.flow]];
    const maxKw = Math.max(1, ...power.filter((v) => v !== null));
    const [xAxis] = timeAxes(language);
    let created;
    try {
      created = await createChart(el, {
        width: el.clientWidth || 800,
        height: HEIGHT,
        padding: [BAND + 14, 8, 0, 0],
        legend: { show: false },
        cursor: { y: false, points: { show: false } },
        scales: { x: { time: true }, t: { range: tempRange(temps) }, p: { range: [0, maxKw * 4] } },
        axes: themedAxes([xAxis, { scale: 't', size: 40, values: (u, v) => v.map((n) => `${n}°`) }]),
        series: [
          { label: t('lineTarget'), scale: 't', stroke: cssVar('--ink-3'), dash: [3, 3], width: 1.2 },
          { label: t('lineOutside'), scale: 't', stroke: cssVar('--cold'), width: 1.6 },
          { label: t('lineReturn'), scale: 't', stroke: cssVar('--cool'), width: 1.4 },
          { label: t('lineFlow'), scale: 't', stroke: cssVar('--warm'), width: 1.9 },
          { label: t('linePower'), scale: 'p', stroke: cssVar('--ink-3'), fill: cssVar('--line'), width: 1, stepped: true },
        ],
        data: [xs, ...temps, power],
        plugins: [bandPlugin(runs)],
        hooks: { setCursor: [(u) => { cursor = u.cursor.idx ?? null; }] },
      });
    } catch {
      return;
    }
    if (!alive || token !== renderToken) {
      created.destroy();
      return;
    }
    chart = created;
  }

  // Rebuild when data, host, language or theme change (chart colours are read from CSS at draw time)
  $effect(() => {
    const d = data;
    const el = host;
    const language = lang;
    void $resolvedTheme;
    untrack(() => draw(d, el, language));
  });

  $effect(() => {
    if (!host || typeof ResizeObserver === 'undefined') return undefined;
    const el = host;
    const ro = new ResizeObserver(() => chart?.setSize(el.clientWidth || 800, HEIGHT));
    ro.observe(el);
    return () => ro.disconnect();
  });

  onDestroy(() => {
    alive = false;
    loadToken++;
    renderToken++;
    destroyChart();
  });

  const at = $derived(data ? (cursor ?? data.xs.length - 1) : null);
  const fmt = (v, d = 1) => (v === null || v === undefined ? '—' : v.toFixed(d));
  const val = (role) => (data && at !== null ? data.cols[data.topics[role]][at] : null);
  const runAt = $derived(data && at !== null ? data.runs.find((r) => data.xs[at] >= r.from && data.xs[at] < r.to) : null);
  const timeAt = $derived(data && at !== null && cursor !== null
    ? new Date(data.xs[at] * 1000).toLocaleTimeString(lang === 'nl' ? 'nl-NL' : 'en-GB', { hour: '2-digit', minute: '2-digit' })
    : t('now'));
</script>

<div class="panel" data-testid="timeline">
  <div class="panel-head">
    <h2>{t('timelineTitle')}</h2>
    {#if data && at !== null}
      <div class="read" data-testid="timeline-readout">
        <b>{timeAt}</b>
        {#if runAt}<span>{#if runAt.activity !== 'unknown'}<i style:background={`var(${ACTIVITY_VAR[runAt.activity]})`}></i>{/if}{runAt.activity === 'unknown' ? t('activityUnknown') : activityLabel(runAt.activity, lang)}</span>{/if}
        <span><i style:background="var(--warm)"></i>{t('lineFlow')} <b>{fmt(val('flow'))}°</b></span>
        <span><i style:background="var(--cool)"></i>{t('lineReturn')} <b>{fmt(val('ret'))}°</b></span>
        <span><i style:background="var(--cold)"></i>{t('lineOutside')} <b>{fmt(val('outside'))}°</b></span>
        <span><i class="dash"></i>{t('lineTarget')} <b>{fmt(val('target'))}°</b></span>
        <span><i style:background="var(--ink-3)"></i>{t('linePower')} <b>{fmt(data.power[at], 2)} kW</b></span>
      </div>
    {/if}
  </div>
  <div class="body">
    {#if data}<div bind:this={host} class="host"></div>{:else}<p class="empty">{t('timelineEmpty')}</p>{/if}
    {#if data}
      <p class="note" data-testid="timeline-approx">{t('timelineApprox')}{#if data.truncated.length} · <span data-testid="timeline-incomplete">{t('timelineIncomplete')}</span>{/if}</p>
    {/if}
  </div>
</div>

<style>
  .read { display: flex; gap: 6px 16px; flex-wrap: wrap; font-size: 12px; color: var(--ink-2); }
  .read b { font: 500 12px var(--font-data); font-stretch: 87.5%; color: var(--ink); }
  .read i { display: inline-block; width: 10px; height: 3px; border-radius: 2px; vertical-align: middle; margin-right: 5px; }
  .read i.dash { background: repeating-linear-gradient(90deg, var(--ink-3) 0 3px, transparent 3px 6px); }
  .body { padding: 8px; }
  .host { width: 100%; min-height: 250px; }
  .empty { color: var(--ink-3); margin: 16px 8px; }
  .note { color: var(--ink-3); font-size: 11.5px; margin: 4px 8px 0; }
</style>
```

`linePower` now means total power in; in Task 4 Step 0 its strings are `'power in'` / `'vermogen in'`.

- [ ] **Step 7: Run full Vitest** → PASS.
- [ ] **Step 8: Commit** — done by the orchestrator after the wave is accepted; builders never commit. Write the build report instead.

---

### Task 8: Mini curve, recent events, shared event labels

- Wave: 3
- Dependencies: Task 4
- Owned files: frontend/src/lib/eventtext.js, frontend/src/features/overview/MiniCurve.svelte, frontend/src/features/curve/CurveChart.svelte (the `inactive` prop only), frontend/src/features/overview/RecentEvents.svelte, frontend/src/features/log/LogScreen.svelte, frontend/tests/eventtext.test.js, frontend/tests/mini-curve.test.js
- Shared mutable paths: /tmp/vite-<attempt-id>
- Exclusive resources: none
- Consumed interfaces: CurveChart (features/curve), curvePoints, api.events, api.commands, overview.* keys
- Produced interfaces: kindLabel, commandLabel, detailText, eventTone, commandTone, recentItems; activeCurve(profile); <MiniCurve>, <RecentEvents>
- Acceptance criteria: every step below done; its tests and the full Vitest suite PASS; no file outside the owned files changed
- Validation: `VITE_CACHE_DIR=/tmp/vite-<attempt-id> npm --prefix frontend run test` (full suite) plus the step-specific commands below
- Report pattern: reports/build/T8--<attempt-id>.md

**Files:**
- Create: `frontend/src/lib/eventtext.js`, `frontend/src/features/overview/MiniCurve.svelte`, `frontend/src/features/overview/RecentEvents.svelte`
- Modify: `frontend/src/features/log/LogScreen.svelte` (use `eventtext.js`), `frontend/src/features/curve/CurveChart.svelte` (`inactive` prop only)
- Test: `frontend/tests/eventtext.test.js`, `frontend/tests/mini-curve.test.js`

**Interfaces:**
- Produces: `kindLabel(kind, lang)`, `commandLabel(name, lang)`, `detailText(detail)` (moved verbatim from `LogScreen.svelte`), `eventTone(kind) → 'defrost'|'fail'|'neutral'`, `commandTone(status) → 'ok'|'pending'|'fail'|'neutral'`, `recentItems(events, commands, lang, n = 6) → [{ts, title, detail, tone}]` (newest first).
- Produces: `activeCurve(profile, activity) → {zone: 'z1'|'z2', mode: 'heat'|'cool'}|null` and `miniView({profile, values, zone, mode}) → {curve, shift, showShift, directSetpoint, coupled, inactive, note}` exported from `MiniCurve.svelte`'s `<script module>`; `CurveChart` gains an `inactive` prop (default `false`).
- Consumes: `CurveChart` (features/curve) with `editable={false}`; `curvePoints`, `isCoupled` (curvegeom); `activityOf` (format.js); existing `curve.notActive`, `curve.setpoint` strings.

- [ ] **Step 1: i18n keys** — already added by Task 4 to `overview.en.js` / `overview.nl.js`. Check with `grep -n 'miniCurveHeat' frontend/src/lib/i18n/overview.en.js`. Do not edit the i18n files in this task.

- [ ] **Step 2: Failing tests**

`frontend/tests/eventtext.test.js`:

```js
import { describe, expect, it } from 'vitest';
import { commandTone, eventTone, kindLabel, recentItems } from '../src/lib/eventtext.js';

describe('eventtext', () => {
  it('labels known kinds and falls back to the raw kind', () => {
    expect(kindLabel('defrost_start', 'en')).toBe('Defrost started');
    expect(kindLabel('something_new', 'en')).toBe('something_new');
  });
  it('maps tones', () => {
    expect(eventTone('defrost_end')).toBe('defrost');
    expect(eventTone('command_rejected')).toBe('fail');
    expect(eventTone('mode_change')).toBe('neutral');
    expect(commandTone('confirmed')).toBe('ok');
    expect(commandTone('retried')).toBe('pending');
    expect(commandTone('failed')).toBe('fail');
  });
  it('merges events and commands newest first and caps the list', () => {
    const events = [{ ts: 10, kind: 'defrost_start', detail: null }, { ts: 30, kind: 'mode_change', detail: { to: 4 } }];
    const commands = [{ submitted_ts: 20, name: 'SetDHWTemp', payload: '52', status: 'confirmed' }];
    const items = recentItems(events, commands, 'en', 2);
    expect(items.map((i) => i.ts)).toEqual([30, 20]);
    expect(items[1].tone).toBe('ok');
    expect(items[1].detail).toContain('52');
  });
});
```

`frontend/tests/mini-curve.test.js`:

```js
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import CurveChart from '../src/features/curve/CurveChart.svelte';
import { activeCurve, miniView } from '../src/features/overview/MiniCurve.svelte';

const F = (value, unknown = false) => ({ value, unknown, stale: false });
const curveValues = (z = 'Z1', m = 'Heat') => ({
  [`main/${z}_${m}_Curve_Target_High_Temp`]: 45, [`main/${z}_${m}_Curve_Target_Low_Temp`]: 28,
  [`main/${z}_${m}_Curve_Outside_Low_Temp`]: -10, [`main/${z}_${m}_Curve_Outside_High_Temp`]: 16,
});
const base = { zones: F('z1'), heating_in_use: F(true), cooling_in_use: F(false), heating_control: F('curve'),
  zone: { z1: { sensor: F('water') }, z2: { sensor: F('water') } } };

describe('activeCurve', () => {
  it('picks zone 1 heating by default, also with two zones and during DHW', () => {
    expect(activeCurve({ ...base, zones: F('both') }, 'heating')).toEqual({ zone: 'z1', mode: 'heat' });
    expect(activeCurve(base, 'dhw')).toEqual({ zone: 'z1', mode: 'heat' });
  });
  it('picks zone 2 when only zone 2 is active', () => {
    expect(activeCurve({ ...base, zones: F('z2') }, 'heating')).toEqual({ zone: 'z2', mode: 'heat' });
  });
  it('picks cooling while cooling, or when only cooling is in use', () => {
    expect(activeCurve(base, 'cooling')).toEqual({ zone: 'z1', mode: 'cool' });
    expect(activeCurve({ ...base, heating_in_use: F(false), cooling_in_use: F(true) }, 'idle')).toEqual({ zone: 'z1', mode: 'cool' });
  });
  it('returns null when neither heating nor cooling is in use', () => {
    expect(activeCurve({ ...base, heating_in_use: F(false), cooling_in_use: F(false) }, 'dhw')).toBe(null);
  });
});

describe('miniView', () => {
  const view = (profile, extra = {}) => miniView({ profile, values: { ...curveValues(), ...extra }, zone: 'z1', mode: 'heat' });
  it('curve control: curve plus shift', () => {
    const v = view(base, { 'main/Z1_Heat_Request_Temp': 2 });
    expect(v).toMatchObject({ shift: 2, showShift: true, directSetpoint: null, inactive: false, note: null });
  });
  it('direct control: inactive curve with the absolute setpoint', () => {
    const v = view({ ...base, heating_control: F('direct') }, { 'main/Z1_Heat_Request_Temp': 35 });
    expect(v).toMatchObject({ showShift: false, directSetpoint: 35, coupled: false, note: 'notActive' });
  });
  it('coupled: setpoint is the cold-end target', () => {
    const v = view({ ...base, heating_control: F('direct'), zone: { z1: { sensor: F('ext_thermostat') } } });
    expect(v).toMatchObject({ directSetpoint: 45, coupled: true, note: 'setpoint' });
  });
  it('direct with a missing setpoint: inactive, labelled unavailable', () => {
    const v = view({ ...base, heating_control: F('direct') });
    expect(v).toMatchObject({ directSetpoint: null, inactive: true, showShift: false, note: 'miniSetpointUnavailable' });
  });
  it('unknown control: configuration-only preview', () => {
    const v = view({ ...base, heating_control: F(null, true) }, { 'main/Z1_Heat_Request_Temp': 2 });
    expect(v).toMatchObject({ directSetpoint: null, inactive: true, showShift: false, shift: 0, note: 'miniControlUnknown' });
  });
  it('no curve without all four values', () => {
    expect(miniView({ profile: base, values: {}, zone: 'z1', mode: 'heat' }).curve).toBe(null);
  });
});

describe('CurveChart inactive prop', () => {
  it('draws the inactive line style without a direct setpoint', () => {
    const current = { cold: { outside: -10, target: 45 }, warm: { outside: 16, target: 28 } };
    render(CurveChart, { mode: 'heat', current, editable: false, inactive: true });
    expect(screen.getByTestId('curve-line').getAttribute('class')).toContain('inactive-line');
    expect(screen.queryByTestId('direct-line')).toBe(null);
  });
});
```

Check the curve leaf names against `rules.json` `curve_ends`/`curveLeaf` (`grep -n Curve_Target_High frontend/src/lib/domain/rules.js backend/heishamon_dashboard/rules.json`) and the room-sensor value names against `curvegeom.ROOM_SENSORS` before running; use the exact names.

- [ ] **Step 3: Run** → FAIL.

- [ ] **Step 4: `frontend/src/lib/eventtext.js`** — move `kindLabel`, `commandLabel` and `detailText` out of `LogScreen.svelte` (same bodies, now exported) and add the tone and merge helpers. The complete module:

```js
/** Labels for the event and command logs, shared by the Log screen and the Overview card. */
import { translate } from './i18n/index.js';
import { commandByName } from './catalog.js';

export function kindLabel(kind, lang) {
  const key = `log.kind_${kind}`;
  const text = translate(lang, key);
  return text === key ? kind : text;
}

export function commandLabel(name, lang) {
  const entry = commandByName(name);
  return entry?.label?.[lang] || entry?.label?.en || name;
}

export function detailText(detail) {
  if (detail == null) return '';
  if (typeof detail !== 'object') return String(detail);
  return Object.entries(detail)
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([key, value]) => `${key}: ${typeof value === 'object' ? JSON.stringify(value) : value}`)
    .join(', ');
}

const FAIL_KINDS = new Set(['error_change', 'flush_failed', 'buffer_overflow', 'events_dropped', 'ingest_dropped', 'command_rejected', 'device_offline', 'broker_disconnected']);

export function eventTone(kind) {
  if (kind === 'defrost_start' || kind === 'defrost_end') return 'defrost';
  return FAIL_KINDS.has(kind) ? 'fail' : 'neutral';
}

export function commandTone(status) {
  if (status === 'confirmed' || status === 'sent' || status === 'noop') return 'ok';
  if (status === 'pending' || status === 'retried') return 'pending';
  if (status === 'failed') return 'fail';
  return 'neutral';
}

/** The newest `n` events and commands, merged, for the Overview card. */
export function recentItems(events = [], commands = [], lang = 'en', n = 6) {
  const items = [
    ...events.map((e) => ({ ts: e.ts, title: kindLabel(e.kind, lang), detail: detailText(e.detail), tone: eventTone(e.kind) })),
    ...commands.map((c) => ({
      ts: c.submitted_ts,
      title: `${commandLabel(c.name, lang)} → ${c.payload}`,
      detail: `${c.name} = ${c.payload} · ${c.status}`,
      tone: commandTone(c.status),
    })),
  ];
  return items.sort((a, b) => b.ts - a.ts).slice(0, n);
}
```

In `LogScreen.svelte` delete the three local functions, add `import { commandLabel, detailText, kindLabel } from '../../lib/eventtext.js';`, and remove the `commandByName` import if nothing else in the file uses it (`grep -n commandByName frontend/src/features/log/LogScreen.svelte`). Run `VITE_CACHE_DIR=/tmp/vite-<attempt-id> npm --prefix frontend run test -- screens2` to confirm the Log tests still pass.

- [ ] **Step 5a: `CurveChart` `inactive` prop** — in `frontend/src/features/curve/CurveChart.svelte` add `inactive = false, // draw the curve inactive even without a direct setpoint` to `$props()`, change `{#if directSetpoint === null}` to `{#if directSetpoint === null && !inactive}`, and in the `{:else}` branch wrap the `<line data-testid="direct-line" …/>` in `{#if directSetpoint !== null}…{/if}`. Nothing else in that file changes in this task (Task 10 restyles it). The Heating curve screen passes no `inactive` prop, so its behaviour is unchanged; run `VITE_CACHE_DIR=/tmp/vite-<attempt-id> npm --prefix frontend run test -- curve` → PASS.

- [ ] **Step 5b: `frontend/src/features/overview/MiniCurve.svelte`**

```svelte
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
```

The request-temperature topics are `main/Z1_Heat_Request_Temp`, `main/Z1_Cool_Request_Temp`, `main/Z2_Heat_Request_Temp` (catalog lines checked by the orchestrator) and the matching `Z2_Cool` key; `grep -n '_Request_Temp"' backend/heishamon_dashboard/catalog.json` confirms them.

- [ ] **Step 6: `frontend/src/features/overview/RecentEvents.svelte`**

```svelte
<script>
  import { api } from '../../lib/api.js';
  import { translate } from '../../lib/i18n/index.js';
  import { recentItems } from '../../lib/eventtext.js';

  let { lang = 'en' } = $props();
  let events = $state([]);
  let commands = $state([]);
  const TONE = { defrost: 'var(--cool)', fail: 'var(--fail)', ok: 'var(--ok)', pending: 'var(--pending)', neutral: 'var(--ink-3)' };

  $effect(() => {
    let alive = true;
    const load = () => {
      api.events({ limit: 6 }).then((b) => { if (alive) events = b?.events ?? []; }, () => {});
      api.commands({ limit: 6 }).then((b) => { if (alive) commands = b?.commands ?? []; }, () => {});
    };
    load();
    const timer = setInterval(load, 60_000);
    return () => { alive = false; clearInterval(timer); };
  });

  const items = $derived(recentItems(events, commands, lang, 6));
  const time = (ts) => new Date(ts).toLocaleTimeString(lang === 'nl' ? 'nl-NL' : 'en-GB', { hour: '2-digit', minute: '2-digit' });
</script>

<div class="panel" data-testid="recent-events">
  <div class="panel-head"><h2>{translate(lang, 'overview.recentEvents')}</h2><a class="tag" href="#/log">{translate(lang, 'overview.openLog')} →</a></div>
  {#if items.length}
    <ul>
      {#each items as item}
        <li>
          <time class="num">{time(item.ts)}</time>
          <span class="k" style:background={TONE[item.tone]}></span>
          <div>{item.title}{#if item.detail}<small>{item.detail}</small>{/if}</div>
        </li>
      {/each}
    </ul>
  {:else}
    <p class="empty">{translate(lang, 'overview.noEvents')}</p>
  {/if}
</div>

<style>
  ul { list-style: none; margin: 0; padding: 0; }
  li { display: grid; grid-template-columns: 54px 16px 1fr; gap: 8px; padding: 9px 16px; border-bottom: 1px solid var(--line); font-size: 13px; }
  li:last-child { border-bottom: 0; }
  time { font-size: 12px; color: var(--ink-3); padding-top: 1px; }
  .k { width: 8px; height: 8px; border-radius: 2px; margin-top: 6px; }
  small { display: block; color: var(--ink-3); font-size: 11.5px; overflow-wrap: anywhere; }
  .empty { color: var(--ink-3); padding: 16px; margin: 0; }
  a.tag { text-decoration: none; }
</style>
```

- [ ] **Step 7: Run full Vitest** → PASS.
- [ ] **Step 8: Commit** — done by the orchestrator after the wave is accepted; builders never commit. Write the build report instead.

---

### Task 9: Overview assembly and restyled controls/tiles

- Wave: 4
- Dependencies: Task 3, Task 5, Task 6, Task 7, Task 8
- Owned files: frontend/src/features/overview/OverviewScreen.svelte, QuickControls.svelte, CurveSetpointControl.svelte, Tile.svelte, Sparkline.svelte, sparkline.js, frontend/src/lib/ui/TempDot.svelte, frontend/tests/sparkline.test.js, frontend/src/features/settings/CommandControl.svelte, frontend/src/lib/ui/CommandStatus.svelte, frontend/src/lib/ui/ApplyButton.svelte, frontend/tests/overview.test.js
- Shared mutable paths: frontend/dist, /tmp/vite-<attempt-id>
- Exclusive resources: port 8765 (visual check)
- Consumed interfaces: PlantSchematic, NowPanel, Timeline24h, MiniCurve, RecentEvents
- Produced interfaces: the assembled Overview (data-testid screen-overview, plant, quick-controls, timeline, recent-events, tiles)
- Acceptance criteria: every step below done; its tests and the full Vitest suite PASS; no file outside the owned files changed
- Validation: `VITE_CACHE_DIR=/tmp/vite-<attempt-id> npm --prefix frontend run test` (full suite) plus the step-specific commands below
- Report pattern: reports/build/T9--<attempt-id>.md

**Files:**
- Modify: `frontend/src/features/overview/OverviewScreen.svelte` (markup + style only; the tile/sparkline script stays)
- Modify: `frontend/src/features/overview/QuickControls.svelte` (style), `Tile.svelte` (style), `Sparkline.svelte` (default stroke)
- Modify: `frontend/src/features/settings/CommandControl.svelte` (draft state class + style), `frontend/src/features/overview/CurveSetpointControl.svelte` (Step 5b), `frontend/src/features/overview/sparkline.js` (Step 7b), `frontend/src/lib/ui/CommandStatus.svelte`, `ApplyButton.svelte`
- Create: `frontend/src/lib/ui/TempDot.svelte` (Step 7a), `frontend/tests/sparkline.test.js` (Step 7b)
- Test: `frontend/tests/overview.test.js` (add layout assertions)

**Interfaces:**
- Consumes: `PlantSchematic`, `NowPanel`, `Timeline24h`, `MiniCurve`, `RecentEvents`.

- [ ] **Step 1: Failing test** — add to `frontend/tests/overview.test.js` inside the existing top-level describe (reuse its `profileFixtures`, store setup and `api.history` spy):

```js
it('lays out schematic, now panel, controls, timeline, curve, events and tiles', async () => {
  vi.spyOn(api, 'energy').mockResolvedValue({ periods: {} });
  vi.spyOn(api, 'events').mockResolvedValue({ events: [] });
  vi.spyOn(api, 'commands').mockResolvedValue({ commands: [] });
  state.set(makeState());
  profile.set(profileFixtures.heatPlusDhw);
  prefs.set(makePrefs());
  render(Overview);
  for (const id of ['plant', 'quick-controls', 'timeline', 'recent-events', 'tiles']) {
    expect(screen.getByTestId(id)).toBeTruthy();
  }
  expect(screen.getByTestId('now-cop')).toBeTruthy();
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: OverviewScreen markup and style**

```svelte
<div class="overview" data-testid="screen-overview">
  {#if $stateStore && $profileStore}
    <div class="grid">
      <div class="plant"><PlantSchematic stateData={$stateStore} profile={$profileStore} lang={$language} /></div>
      <aside class="side">
        <NowPanel stateData={$stateStore} profile={$profileStore} lang={$language} />
        <QuickControls profile={$profileStore} stateData={$stateStore} prefs={$prefsStore} lang={$language} commandMap={$commandsStore} />
      </aside>
      <div class="timeline"><Timeline24h profile={$profileStore} lang={$language} /></div>
      <div class="lower">
        <MiniCurve stateData={$stateStore} profile={$profileStore} lang={$language} />
        <RecentEvents lang={$language} />
      </div>
      <section class="pinned">
        <h2 class="tag">{translate($language, 'overview.pinnedTiles')}</h2>
        <div class="tiles" data-testid="tiles">
          {#each activeTiles as tileId}
            {@const topic = getTileTopic(tileId)}
            {@const sparkline = getSparkline(tileId)}
            <Tile
              key={tileId}
              topic={topic}
              sparkline={sparkline}
              lang={$language}
              deviceOnline={$stateStore.device_online}
              isPinned={pinnedTiles.includes(tileId)}
              onPin={handlePin}
              onUnpin={handleUnpin}
            />
          {/each}
        </div>
      </section>
    </div>
  {:else}
    <p class="loading">{translate($language, 'common.ageUnknown')}</p>
  {/if}
</div>

<style>
  .grid { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 16px; }
  .grid > * { min-width: 0; }
  .plant, .timeline { grid-column: 1; }
  .side { grid-column: 2; grid-row: 1 / 3; display: flex; flex-direction: column; gap: 16px; }
  .lower, .pinned { grid-column: 1 / 3; }
  .lower { display: grid; grid-template-columns: 1.1fr 1fr; gap: 16px; }
  .pinned h2 { margin: 4px 0 10px; }
  .tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(10.5rem, 45%), 1fr)); gap: 12px; }
  .loading { color: var(--ink-3); }
  @media (max-width: 1180px) {
    .grid { grid-template-columns: minmax(0, 1fr); }
    .side { grid-column: 1; grid-row: auto; display: grid; grid-template-columns: 1fr 1fr; }
    .lower, .pinned { grid-column: 1; }
    /* stack in the spec order: schematic, timeline, Now + controls, curve + events, tiles */
    .plant { order: 1; }
    .timeline { order: 2; }
    .side { order: 3; }
    .lower { order: 4; }
    .pinned { order: 5; }
  }
  @media (max-width: 759px) {
    .side, .lower { grid-template-columns: 1fr; }
  }
</style>
```

Add the five imports. Keep the whole `<script>` (tiles, pinning, sparklines) as is.

- [ ] **Step 4: QuickControls style** — wrap the section in the panel style:

```css
.quick-controls { background: var(--panel); border: 1px solid var(--line); border-radius: var(--r); padding: 0; }
h2 { margin: 0; padding: 12px 16px; border-bottom: 1px solid var(--line); font: 600 13.5px var(--font-ui); }
.grid { display: flex; flex-direction: column; padding: 0 16px 8px; }
.grid > div { border-bottom: 1px solid var(--line); min-width: 0; }
.grid > div:last-child { border-bottom: 0; }
```

- [ ] **Step 5: CommandControl draft state** — on the control's root element add
`class:draft={toSend != null}` and style:

```css
.draft :is(select, input:not([type='range'])) { border-color: var(--pending); color: var(--pending-ink); }
.draft input[type='range'] { accent-color: var(--pending); }
```

Replace remaining legacy variables in its `<style>` with tokens (mapping in Task 10, Step 1); values
in Martian Mono via `font-family: var(--font-data)` on the current-value read-out.

- [ ] **Step 5b: CurveSetpointControl** (`frontend/src/features/overview/CurveSetpointControl.svelte`, the coupled-mode quick control): give its root element the same `class:draft` as CommandControl, using the condition that already enables its Apply button for a changed value (read the script; do not change its logic), add the same two `.draft` CSS rules as Step 5, and replace its legacy variables: `--text-secondary` → `--ink-2`, `--danger` → `--fail-ink` (text), `--primary` → `--warm-ink` (text). Its existing tests (`grep -n "coupled" frontend/tests/overview.test.js`) must still pass.

- [ ] **Step 6: CommandStatus colours** — replace the six hex values:

```css
.confirmed { background: color-mix(in srgb, var(--ok) 16%, transparent); color: var(--ok-ink); }
.failed { background: color-mix(in srgb, var(--fail) 16%, transparent); color: var(--fail-ink); }
.pending { background: color-mix(in srgb, var(--pending) 16%, transparent); color: var(--pending-ink); }
```

(keep the existing selector names in that file; only the declarations change). `ApplyButton`: add
`class="primary"` to its `<button>`.

- [ ] **Step 7a: TempDot** — create `frontend/src/lib/ui/TempDot.svelte` (spec R4 "Temperatures on every screen"):

```svelte
<script>
  import { tempColor } from './thermal.js';

  let { value = null } = $props();
</script>

{#if typeof value === 'number' && Number.isFinite(value)}<i class="temp-dot" style:background={tempColor(value)} aria-hidden="true"></i>{/if}

<style>
  .temp-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
</style>
```

In `Tile.svelte` render `<TempDot value={topic.value} />` before the value text when the tile's unit (`shown?.unit`) is `°C`, `topic` exists and `topic.sentinel` is false. Add to `frontend/tests/overview.test.js`: a tile for `main/Outside_Temp` with value 6 contains an element `.temp-dot`; a sentinel value renders none.

- [ ] **Step 7: Tile and Sparkline** — Tile: `.tile` becomes `background: var(--panel); border: 1px solid var(--line); border-radius: var(--r); padding: 12px 14px;`, label as `.tag` style (Martian Mono 10.5 px uppercase `--ink-3`), value `font: 500 22px/1.2 var(--font-data); font-stretch: 87.5%;`, pin hover `color: var(--warm-ink)`, sparkline `color: var(--ink-3)`. Sparkline: default `stroke = 'currentColor'`.

- [ ] **Step 7b: 24 h sparklines (spec R3.6)** — `frontend/src/features/overview/sparkline.js` currently asks for `max_points: 96`, which at 1-minute resolution is the last 96 minutes. Failing test first, `frontend/tests/sparkline.test.js`:

```js
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchSparklineValues, reduceToSlots } from '../src/features/overview/sparkline.js';
import { api } from '../src/lib/api.js';

const MIN = 60_000;
afterEach(() => vi.restoreAllMocks());

describe('sparklines cover 24 h', () => {
  it('asks for a full day of minute buckets', async () => {
    const spy = vi.spyOn(api, 'history').mockResolvedValue({ resolution: '1m', series: {} });
    await fetchSparklineValues('main/Outside_Temp', 24 * 3600 * 1000);
    expect(spy.mock.calls[0][0].max_points).toBeGreaterThanOrEqual(1441);
  });
  it('reduces to 96 slots with coverage-weighted means and gaps', () => {
    const from = 0;
    const slot = 15 * MIN;
    const series = { points: [[0, 10, 60], [MIN, 40, 1], [2 * slot, 20, 60]], breaks: [] };
    const out = reduceToSlots(series, '1m', from, from + 96 * slot, 96);
    expect(out).toHaveLength(96);
    expect(out[0]).toBeCloseTo((10 * 60 + 40) / 61);
    expect(out[1]).toBe(null);
    expect(out[2]).toBe(20);
  });
  it('keeps a slot inside a break empty', () => {
    const slot = 15 * MIN;
    const out = reduceToSlots({ points: [[slot + MIN, 5, 60]], breaks: [[slot, 2 * slot]] }, '1m', 0, 96 * slot, 96);
    expect(out[1]).toBe(null);
  });
});
```

Implementation: export `reduceToSlots(series, resolution, from, to, n)` (coverage-weighted mean per slot of `(to − from) / n`, `null` for an empty slot or a slot whose start lies inside a break; raw points weigh 1), and make `fetchSparklineValues(topicKey, now)` request `max_points: 1500` for `[now − 24 h, now]` and return `reduceToSlots(history.series[topicKey], history.resolution, now − 24 h, now, 96)` (or `[]` when the series is missing or the call fails, as today). Keep `normalizeSparkline` unchanged.

- [ ] **Step 8: Run full Vitest** → PASS (fix only selectors that broke because of structure).
- [ ] **Step 9: Visual check** at 1440 px, 1024 px and 390 px against the mockup; both themes.
- [ ] **Step 10: Commit** — done by the orchestrator after the wave is accepted; builders never commit. Write the build report instead.

---

### Task 10: Remaining screens on tokens, remove legacy names

- Wave: 5
- Dependencies: Task 9
- Owned files: every *.svelte under frontend/src/features/{charts,curve,energy,settings,topics,log,system} and frontend/src/lib/ui/ConfirmDialog.svelte, frontend/src/lib/uplot.js, frontend/src/lib/curvegeom.js, frontend/src/app.css, frontend/src/lib/i18n/topics.en.js, frontend/src/lib/i18n/topics.nl.js, frontend/tests/tokens.test.js, frontend/tests/topic-row.test.js, frontend/tests/charts.test.js (palette assertions), frontend/tests/curve.test.js (handle class assertion only)
- Shared mutable paths: frontend/dist, /tmp/vite-<attempt-id>
- Exclusive resources: port 8765 (visual check)
- Consumed interfaces: mixRgb (Task 1), themedAxes (Task 7), resolvedTheme (Task 1)
- Produced interfaces: no legacy token names; hex only in app.css, thermal.js, uplot.js
- Acceptance criteria: every step below done; its tests and the full Vitest suite PASS; no file outside the owned files changed
- Validation: `VITE_CACHE_DIR=/tmp/vite-<attempt-id> npm --prefix frontend run test` (full suite) plus the step-specific commands below
- Report pattern: reports/build/T10--<attempt-id>.md

**Files:**
- Modify: every `*.svelte` under `frontend/src/features/{charts,curve,energy,settings,topics,log,system}` and `frontend/src/lib/ui/ConfirmDialog.svelte`
- Modify: `frontend/src/lib/uplot.js` (palettes), `frontend/src/lib/curvegeom.js` (colours), `frontend/src/features/charts/ChartContainer.svelte` (themed axes, redraw on theme)
- Modify: `frontend/src/app.css` (drop legacy names)
- Test: `frontend/tests/tokens.test.js`; update palette assertions in `frontend/tests/charts.test.js`

- [ ] **Step 1: Mapping** — apply everywhere:

| Old | New |
|---|---|
| `var(--bg)` | `var(--panel)` |
| `var(--bg-secondary)` | `var(--panel-2)` |
| `var(--bg-hover)` | `var(--line)` |
| `var(--border)` | `var(--line)` for panel edges, `var(--line-2)` for control borders |
| `var(--text)` | `var(--ink)` |
| `var(--text-secondary)` | `var(--ink-2)` |
| `var(--primary)` / `--primary-dark` | `var(--warm)` / `var(--hot)` for fills, borders and marks; `var(--warm-ink)` for text; primary buttons use `class="primary"` |
| `var(--danger)` | `var(--fail)` for fills/borders, `var(--fail-ink)` for text |
| `var(--warn-bg)` / `var(--warn-border)` | `color-mix(in srgb, var(--pending) 14%, transparent)` / `var(--pending)` |
| `var(--card-radius)` | `var(--r)` |
| `#666`, `#888`, `#6b7280` (muted text) | `var(--ink-3)` |
| `#ccc`, `#ddd` (borders) | `var(--line)` |
| `#f5f5f5`, `#f9f9f9` (fills) | `var(--panel-2)` |
| `#1976d2` (active toggle) | `var(--ink)` background, `var(--ground)` text |
| `#d32f2f` (error text) | `var(--fail-ink)` |
| `rgba(0,0,0,.7/.8)` (chart overlays) | `color-mix(in srgb, var(--ground) 85%, transparent)` |
| `rgba(255,0,0,.8)` | `color-mix(in srgb, var(--fail) 85%, transparent)` |

Section cards on every screen use the `.panel` / `.panel-head` / `.panel-body` classes from `app.css`;
screen titles `font: 600 22px/1.1 var(--font-ui)`; numeric table cells `font-family: var(--font-data)`.

- [ ] **Step 2: CurveChart colours** (`frontend/src/features/curve/CurveChart.svelte:269-285`, plus line 156):

```css
.grid { stroke: var(--line); stroke-width: 1; }
.label { paint-order: stroke; stroke: var(--panel); stroke-width: 3px; stroke-linejoin: round; fill: var(--ink-3); }
.curve { fill: none; stroke: var(--ink); stroke-width: 2.6; }
.curve.changed { stroke: var(--pending); }
.ghost { fill: none; stroke: var(--ink-3); stroke-width: 2; stroke-dasharray: 6 5; }
.shift { fill: none; stroke: var(--warm); stroke-width: 1.4; stroke-dasharray: 4 4; }
.direct { stroke: var(--warm); stroke-width: 2; }
.handle { fill: var(--panel); stroke: var(--ink); stroke-width: 2.5; cursor: grab; }
.handle.cold { stroke: var(--cold); }
.handle.warm { stroke: var(--warm); }
.threshold { stroke: var(--pending); stroke-width: 1.5; stroke-dasharray: 4 3; }
.threshold.readonly { stroke: var(--ink-3); }
.threshold-grip { fill: var(--pending); cursor: ew-resize; }
.live { stroke: var(--ink-2); stroke-width: 1; stroke-dasharray: 2 3; }
.live-target { fill: none; stroke: var(--warm); stroke-width: 2; }
.live-water { fill: var(--warm); }
.median { fill: none; stroke: var(--ink); stroke-width: 1.3; stroke-dasharray: 1 4; stroke-linecap: round; }
.flat { fill: var(--panel-2); opacity: .6; }
```

Add `class:changed` on the draft curve element (`changed` is already derived in the script),
`class="handle {end}"` on the handle circles (keep their `data-testid`s) plus
`class:changed={Boolean(current) && (shown[end].outside !== current[end].outside || shown[end].target !== current[end].target)}`,
with `.handle.changed { stroke: var(--pending); }` placed after `.handle.cold`/`.handle.warm` so a moved handle shows the draft colour (spec R4);
add a test to `frontend/tests/curve.test.js` that renders CurveChart with a draft whose cold end differs and asserts `handle-cold` has class `changed` and `handle-warm` has not; the
outlined-window stroke `'var(--ink-2)'` instead of `'#333'`, and two `<rect class="flat">` areas
left of the cold end and right of the warm end with a `.label` "model assumption" text using the
existing `curve.*` key for that warning (grep `curve.en.js` for "assumption").

- [ ] **Step 3: `curvegeom.js` colours** — replace `deviationColor`, `sequentialColor` and the literals in `windowColor`:

```js
import { MARK_RGB, RAMP, mixRgb } from './ui/thermal.js';

// one source for the ramp: thermal.js
const NEUTRAL = MARK_RGB.neutral;
const COLD = RAMP[0][1];
const WARM = RAMP[2][1];
const HOT = RAMP[3][1];

/** Diverging colour for a deviation in °C: cold blue below, warm orange above, grey at zero. */
export function deviationColor(v) {
  if (v === null || v === undefined || !Number.isFinite(v)) return mixRgb(NEUTRAL, NEUTRAL, 0);
  return mixRgb(NEUTRAL, v < 0 ? COLD : WARM, Math.min(1, Math.abs(v) / 5));
}

export function sequentialColor(v, lo, hi) {
  if (v === null || v === undefined || !Number.isFinite(v)) return mixRgb(NEUTRAL, NEUTRAL, 0);
  const t = hi > lo ? Math.min(1, Math.max(0, (v - lo) / (hi - lo))) : 0.5;
  return mixRgb(COLD, HOT, t);
}
```

In `windowColor`: no-COP and `before` `mixRgb(NEUTRAL, NEUTRAL, 0)`; `after` `mixRgb(MARK_RGB.ok, MARK_RGB.ok, 0)`.
`curvegeom.js` is then hex-free.

- [ ] **Step 4: Chart palettes** (`frontend/src/lib/uplot.js`)

```js
export const COLORS = ['#f0a04b', '#4fa3e0', '#6cc59a', '#e5533d', '#8fb8c9', '#b48ce0', '#e8c25a', '#93a3b0', '#d07fb0', '#5fc4c0'];
export const ENUM_COLORS = { 0: '#64737f', 1: '#4fa3e0', 2: '#f0a04b', 3: '#6cc59a', 4: '#e5533d', 5: '#b48ce0', 6: '#8fb8c9', 7: '#d07fb0', 8: '#93a3b0', 9: '#e8c25a', 10: '#5fc4c0' };
```

Update the asserted values in `tests/charts.test.js` (lines ~298-301 and ~608-610) to these.
In `ChartContainer.svelte`: pass axes through `themedAxes(...)` and add `void $resolvedTheme;`
inside the effect that creates the chart, so a theme switch rebuilds it.

- [ ] **Step 5: Topics table** (`TopicRow.svelte`, `TopicsScreen.svelte`): key cell in `var(--font-data)` 12 px with the subtree prefix wrapped in a `<span class="prefix">` coloured `--ink-3`; value right-aligned in Martian Mono; a changed value flashes:

```css
.val.flash { animation: flash 1.2s; }
@keyframes flash { from { background: color-mix(in srgb, var(--warm) 25%, transparent); } }
.sentinel-badge { font: 10.5px var(--font-data); border: 1px solid var(--line-2); border-radius: 4px; padding: 1px 5px; color: var(--ink-2); }
```

Trigger `flash` with a `{#key topicValue?.last_change}` block around the value cell.

Sentinels and temperatures in `TopicRow.svelte` (spec R4): when `topicValue?.sentinel` is true, render instead of the value span
`<span class="sentinel-badge" data-testid={`sentinel-${topicKey}`}>{topicValue.raw}{#if SENTINEL_KEY[topicValue.raw]} · {translate(lang, SENTINEL_KEY[topicValue.raw])}{/if}</span>`
with `const SENTINEL_KEY = { '-1': 'topics.sentinelUnknown', '-128': 'topics.sentinelAbsent', '-78': 'topics.sentinelNotConnected', '-127': 'topics.sentinelUnused' };`
and the strings (EN / NL): `sentinelUnknown: 'unknown state'` / `'onbekende toestand'`, `sentinelAbsent: 'sensor absent'` / `'sensor afwezig'`,
`sentinelNotConnected: 'not connected'` / `'niet aangesloten'`, `sentinelUnused: 'unused'` / `'ongebruikt'` in `topics.en.js` / `topics.nl.js`.
When the unit is `°C` and the value is not a sentinel, put `<TempDot value={topicValue?.value ?? null} />` (from `../../lib/ui/TempDot.svelte`) before the value.
Test `frontend/tests/topic-row.test.js`:

```js
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import TopicRow from '../src/features/topics/TopicRow.svelte';

const tv = (value, raw, sentinel) => ({ value, raw, sentinel, kind: 'number', unit: '°C', decimals: 1, enum_label: null, catalogued: true, last_change: 1, last_seen: 1, retained_only: false });
const cat = { unit: '°C', label: { en: 'Temperature', nl: 'Temperatuur' } };

describe('TopicRow', () => {
  it('shows a sentinel as a badge with its meaning', () => {
    render(TopicRow, { topicKey: 'main/Buffer_Temp', topicValue: tv(-128, '-128', true), catalogTopic: cat, lang: 'en', now: 2 });
    expect(screen.getByTestId('sentinel-main/Buffer_Temp').textContent).toBe('-128 · sensor absent');
  });
  it('marks a temperature with a ramp dot', () => {
    const { container } = render(TopicRow, { topicKey: 'main/Outside_Temp', topicValue: tv(6, '6', false), catalogTopic: cat, lang: 'en', now: 2 });
    expect(container.querySelector('.temp-dot')).not.toBeNull();
  });
});
```

- [ ] **Step 6: Drop the legacy names** from `app.css` (the block under "Legacy names").

- [ ] **Step 7: Guard test** `frontend/tests/tokens.test.js`

```js
import { describe, expect, it } from 'vitest';

const files = import.meta.glob('../src/**/*.{svelte,js}', { query: '?raw', import: 'default', eager: true });
const HEX_ALLOWED = ['/lib/ui/thermal.js', '/lib/uplot.js'];
const LEGACY = /var\(--(bg|bg-secondary|bg-hover|border|text|text-secondary|primary|primary-dark|danger|warn-bg|warn-border|card-radius)\)/;

describe('design tokens', () => {
  it('uses no legacy variable names', () => {
    for (const [path, src] of Object.entries(files)) expect(LEGACY.test(src), path).toBe(false);
  });
  it('keeps hex colours out of components', () => {
    for (const [path, src] of Object.entries(files)) {
      if (HEX_ALLOWED.some((p) => path.endsWith(p)) || path.includes('/i18n/')) continue;
      const css = src.match(/<style[\s\S]*?<\/style>/g)?.join('\n') ?? '';
      const code = src.replace(/<style[\s\S]*?<\/style>/g, '');
      const hex = /#[0-9a-fA-F]{3,8}\b/;
      expect(hex.test(css), `${path} <style>`).toBe(false);
      expect(/['"`]#[0-9a-fA-F]{3,8}['"`]/.test(code), `${path} script`).toBe(false);
    }
  });
  it('colours text with the -ink variants of state and accent colours', () => {
    const accentText = /(?<![-\w])color:\s*var\(--(ok|pending|fail|warm|hot|cold|cool)\)/;
    for (const [path, src] of Object.entries(files)) {
      const css = src.match(/<style[\s\S]*?<\/style>/g)?.join('\n') ?? '';
      expect(accentText.test(css), path).toBe(false);
    }
  });
});
```

- [ ] **Step 8: Run full Vitest** → PASS. Fix every file the guard names.
- [ ] **Step 9: Visual pass** — every screen at 1280 px and 390 px, day and night; nothing unreadable, no light-only artefacts.
- [ ] **Step 10: Commit** — done by the orchestrator after the wave is accepted; builders never commit. Write the build report instead.

---

### Task 11: End-to-end visual checks

- Wave: 6
- Dependencies: Task 10
- Owned files: frontend/e2e/visual.spec.js
- Shared mutable paths: frontend/dist, /tmp/vite-<attempt-id>, /tmp/visual-*.png, /tmp/pw-T19-results, /tmp/hm-e2e-pids.json
- Exclusive resources: port 8765, the e2e simulator/broker stack
- Consumed interfaces: data-testid theme-toggle, plant, plant-flow, plant-dhw, plant-dhw-branch, plant-zone-<id>, timeline; THEME_KEY heishamon.theme; simulator presets from tools/presets.py
- Produced interfaces: frontend/e2e/visual.spec.js
- Acceptance criteria: every step below done; the new spec passes; the full Vitest suite passes; no file outside the owned files changed
- Validation: `VITE_CACHE_DIR=/tmp/vite-<attempt-id> npm --prefix frontend run test`; `npm --prefix frontend run build`; then `cd frontend && npx playwright test e2e/visual.spec.js`
- Report pattern: reports/build/T11--<attempt-id>.md

**Files:**
- Create: `frontend/e2e/visual.spec.js`

Documentation (AGENTS.md, README.md) is not touched here; task D1 handles it after verification.

- [ ] **Step 1: `frontend/e2e/visual.spec.js`**

```js
import { test, expect } from '@playwright/test';
import { up, down } from './stack.js';
import { SCREENS, noOverflow, openScreen, watchErrors } from './helpers.js';

/** Product of the opacities of an element and all its ancestors. */
async function effectiveOpacity(locator) {
  return locator.evaluate((el) => {
    let o = 1;
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) o *= Number(getComputedStyle(n).opacity || 1);
    return o;
  });
}

test.describe('visual design @ heat_dhw', () => {
  test.beforeAll(async () => { await up('heat_dhw'); });
  test.afterAll(async () => { await down(); });

  test('theme toggle switches and persists', async ({ page }) => {
    await openScreen(page, 'overview');
    const before = await page.evaluate(() => document.documentElement.dataset.theme);
    await page.getByTestId('theme-toggle').click();
    const after = await page.evaluate(() => document.documentElement.dataset.theme);
    expect(after).not.toBe(before);
    await page.reload();
    expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe(after);
  });

  test('schematic shows readings, keeps dimmed readings readable, and the timeline renders', async ({ page }) => {
    await openScreen(page, 'overview');
    await expect(page.getByTestId('plant')).toBeVisible();
    await expect(page.getByTestId('plant-flow')).not.toHaveText('—');
    await expect(page.getByTestId('timeline')).toBeVisible();
    // whichever branch is dimmed, its readings keep full opacity (spec R1 readable text)
    expect(await effectiveOpacity(page.getByTestId('plant-flow'))).toBe(1);
    expect(await effectiveOpacity(page.getByTestId('plant-dhw'))).toBe(1);
  });

  for (const theme of ['day', 'night']) {
    for (const [width, height] of [[1280, 800], [390, 844]]) {
      test(`all screens render in ${theme} at ${width}px`, async ({ page }) => {
        const errors = watchErrors(page);
        await page.addInitScript((t) => localStorage.setItem('heishamon.theme', t), theme);
        await page.setViewportSize({ width, height });
        for (const name of SCREENS) {
          await openScreen(page, name);
          await page.waitForTimeout(300);
          await noOverflow(page);
          await page.screenshot({ path: `/tmp/visual-${theme}-${width}-${name}.png`, fullPage: true });
        }
        expect(errors).toEqual([]);
      });
    }
  }
});

// Every canonical simulator preset (tools/presets.py PRESETS, aliases excluded) renders the new Overview
// in both themes at both widths (spec R3 acceptance). Where the installation shape is known, the
// schematic must match it (spec R3.1); `null` means: only the common checks.
const PRESETS = [
  ['heat_only', { zones: ['z1'], tank: true }],
  ['cool_only', { zones: ['z1'], tank: true }],
  ['dhw_only', { zones: ['z1'], tank: true }],
  ['heat_dhw', { zones: ['z1'], tank: true }],
  ['cool_dhw', { zones: ['z1'], tank: true }],
  ['auto_heat', { zones: ['z1'], tank: true }],
  ['auto_heat_dhw', { zones: ['z1'], tank: true }],
  ['auto_cool_mode7', { zones: ['z1'], tank: true }],
  ['auto_cool_dhw', { zones: ['z1'], tank: true }],
  ['two_zones_heat_curve_cool_direct', { zones: ['z1', 'z2'], tank: true }],
  ['z1_water_z2_internal_thermostat', { zones: ['z1', 'z2'], tank: true }],
  ['zone2_only_and_thermistor', { zones: ['z2'], tank: true }],
  ['no_dhw_tank', { zones: ['z1'], tank: false }],
  ['with_extra', null],
  ['without_extra', null],
  ['pcb_active', null],
  ['pcb_inactive', null],
  ['no_integrations', null],
  ['all_integrations', null],
  ['fw-3.2.3', null],
  ['unknown-inputs', { zones: ['z1'], tank: true }], // unknown profile inputs → features shown
  ['solar_mode_3', null],
];

for (const [preset, expected] of PRESETS) {
  test.describe(`overview @ ${preset}`, () => {
    test.beforeAll(async () => { await up(preset); });
    test.afterAll(async () => { await down(); });

    for (const theme of ['day', 'night']) {
      for (const [width, height] of [[1280, 800], [390, 844]]) {
        test(`renders in ${theme} at ${width}px`, async ({ page }) => {
          const errors = watchErrors(page);
          await page.addInitScript((t) => localStorage.setItem('heishamon.theme', t), theme);
          await page.setViewportSize({ width, height });
          await openScreen(page, 'overview');
          for (const id of ['plant', 'quick-controls', 'timeline', 'recent-events', 'tiles']) {
            await expect(page.getByTestId(id)).toBeVisible();
          }
          if (expected) {
            for (const z of ['z1', 'z2']) {
              await expect(page.getByTestId(`plant-zone-${z}`)).toHaveCount(expected.zones.includes(z) ? 1 : 0);
            }
            await expect(page.getByTestId('plant-dhw-branch')).toHaveCount(expected.tank ? 1 : 0);
          }
          await noOverflow(page);
          await page.screenshot({ path: `/tmp/visual-preset-${preset}-${theme}-${width}.png`, fullPage: true });
          expect(errors).toEqual([]);
        });
      }
    }
  });
}

// profile-change switches heat → cool (and heating control → direct) after 60 s: the Overview must follow live.
test.describe('overview @ profile-change', () => {
  test.beforeAll(async () => { await up('profile-change'); });
  test.afterAll(async () => { await down(); });

  test('follows a live profile change without reload', async ({ page }) => {
    test.setTimeout(150_000);
    const errors = watchErrors(page);
    await openScreen(page, 'overview');
    await expect(page.getByTestId('plant')).toContainText('Heating');
    await expect(page.getByTestId('plant')).toContainText('Cooling', { timeout: 120_000 });
    await expect(page.getByTestId('now-mode')).toHaveText('Cooling');
    expect(errors).toEqual([]);
  });
});
```

Before running, check the preset list against `tools/presets.py` `PRESETS` (every key except `_ALIASES`) and each expected zones/tank value against the preset's Zones_State and DHW_Installed. The unknown-profile rule applies (unknown → shown). If a preset's facts differ, correct the expectation and report it; never drop a preset. The Overview texts "Heating"/"Cooling" assume the English UI default of a fresh browser; if the stack starts in Dutch, use the NL strings. No preset has a buffer tank; the buffer drawing is covered by the PlantSchematic component test in Task 5. This matrix is long (22 presets × 4 runs plus profile-change); run it once, serially.

- [ ] **Step 2: Build first** — `npm --prefix frontend run build` (the e2e stack serves `frontend/dist`, so a stale build would test old code).

- [ ] **Step 3: Run** — `cd frontend && npx playwright test e2e/visual.spec.js` → PASS. Then the full Vitest suite. Do not run pytest or other Playwright files in parallel.

- [ ] **Step 4: Report** — list the screenshots written to `/tmp/visual-*.png` and any preset expectation you corrected.

---

### Task D1: Documentation reconciliation (deferred)
- Wave: 7
- Dependencies: Task 1, Task 2, Task 3, Task 4, Task 5, Task 6, Task 7, Task 8, Task 9, Task 10, Task 11
- Owned files: /workspace/heishamon-dashboard/AGENTS.md (real file; CLAUDE.md is a symlink to it), /workspace/heishamon-dashboard/README.md
- Shared mutable paths: none
- Exclusive resources: none
- Consumed interfaces: the verified integrated diff of `feat/visual-redesign` against `main`
- Produced interfaces: per-file documentation proposal, then applied approved edits
- Acceptance criteria: per `doc-reconciliation.md` of paseo-autopilot — assessment proposal, verifier audit, owner decision per file, apply only approved content
- Validation: `readlink -f CLAUDE.md` still resolves to AGENTS.md after any edit
- Report pattern: reports/build/D1--<attempt-id>.md
- Execution: deferred — not run during BUILD_WAVES; runs after VERIFY passes.
