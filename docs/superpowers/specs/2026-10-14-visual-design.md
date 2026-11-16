# Specification: visual design — "the dashboard as a plant schematic"

Amends spec `docs/superpowers/specs/2026-10-11-heishamon-dashboard-design.md` (§4.2 frontend, §7
screens). Approved by the owner on 2026-10-14 from the mockup in
`docs/mockups/2026-10-14-redesign/index.html`, which is the visual reference for everything below.
Behaviour that this document does not mention stays as the main spec defines it. The owner will
fine-tune details later; this document fixes the style, not every pixel.

Durable copy: `.paseo-autopilot/20261014T072835Z-visual-redesign/01-spec.md` (byte-identical).
Visible path requested by the owner's workflow: `docs/superpowers/specs/2026-10-14-visual-design.md`.

## Outcome and non-goals

**Outcome.** The Svelte frontend moves onto a new, distinctive visual design:

- **The Overview opens on a live schematic of the installation.** Outdoor unit, indoor unit, the
  three-way valve, the zone emitters and the DHW tank, drawn like an installer's diagram, with the
  measuring points shown as instrument tags (TT, SC).
- **Colour means temperature.** One cold→warm ramp is used for everything that is a temperature.
  Two state colours exist apart from it: *draft* (amber, not yet sent) and *confirmed* (green).
  Error red is the ramp's hot end, used only for failures. Deliberate exceptions that reuse ramp
  colours for identity rather than temperature: the activity colours (R1), chart series identity
  (R4), the topic-change flash, the focus ring, and the electricity/ambient split in the Now panel.
- **Numbers have their own typeface.** Every measured value uses a monospaced face with tabular
  figures, so live updates never make text jump.
- **Day and night are both first-class.** The theme follows the system setting until the user
  picks one.

**Non-goals.**

- The batched "draft tray" seen in the mockup (one Apply for several changed controls). It changes
  the command flow and needs its own spec change; quick controls keep per-control Apply.
- New screens, and any backend change. The Overview timeline, Now panel and events card use
  existing endpoints only.
- Pushing, merging to `main`, Docker, deployment.

## Requirements and acceptance criteria

### R1. Tokens

Defined once in `frontend/src/app.css`; components use only these variables.

| Token | Night | Day | Use |
|---|---|---|---|
| `--ground` | `#12181c` | `#e9edf0` | page background |
| `--panel` | `#182026` | `#ffffff` | panels |
| `--panel-2` | `#1e2830` | `#f3f6f8` | inset controls, hover |
| `--line` | `#2a3640` | `#d5dde3` | hairlines |
| `--line-2` | `#364552` | `#bcc8d1` | control borders |
| `--ink` | `#dce3e8` | `#18212a` | text |
| `--ink-2` | `#93a3b0` | `#4f5f6c` | secondary text |
| `--ink-3` | `#8494a1` | `#5a6874` | tags, axes, small functional labels |
| `--pipe-idle` | `#33414c` | `#c9d3da` | pipes without flow |
| `--unit` | `#222c34` | `#f6f8f9` | equipment fill in the schematic |

Theme-independent: `--cold #4fa3e0`, `--cool #8fb8c9`, `--warm #f0a04b`, `--hot #e5533d`,
`--ok #6cc59a`, `--pending #e8c25a`, `--fail #e5533d`.

**Thermal ramp** (`tempColor(t)`, linear RGB interpolation, clamped at both ends):
15 °C `#4fa3e0` → 28 °C `#8fb8c9` → 38 °C `#f0a04b` → 55 °C `#e5533d`.

**Activity colours** (used wherever an activity is marked): heating `--warm`, DHW `--hot`,
cooling `--cold`, defrost `--cool`, idle `--line-2`.

**Type:**
- UI: *Instrument Sans* 400/500/600.
- Data: *Martian Mono* (variable; width 87.5 % for readings, 75 % for the big COP figure).
- Tags (eyebrows, axis labels, instrument tags): Martian Mono 10.5 px, uppercase, letter-spacing .08em, `--ink-3`.
- Both fonts are **bundled in the image** (Fontsource packages), never loaded from a CDN: the
  dashboard must work offline and must not leak visits to third parties.

Radius 10 px for panels, 8 px for controls. Focus ring: 2 px `--warm`.

**Readable text.** Every text colour used for functional text (labels, tags, axis text, nav
labels, values) has a WCAG contrast ratio of at least 4.5:1 against `--panel`, `--panel-2` and
`--ground` in its theme. `--ink-3` was lightened (night) and darkened (day) from the mockup's
values (`#64737f` / `#7d8c98`, about 3.4:1) to meet this: night `#8494a1` gives 5.29 / 4.80 / 5.74,
day `#5a6874` gives 5.73 / 5.28 / 4.86. `--line` and `--line-2` are decoration only and carry no text.
State and accent colours are fills, borders and marks; where one of them colours **text** (command
status, the unlocked write-lock chip, a draft value, the flush error, an accent link) the text uses
its `-ink` variant, defined per theme:

| Token | Night | Day |
|---|---|---|
| `--ok-ink` | `#6cc59a` | `#2a7050` |
| `--pending-ink` | `#e8c25a` | `#7a5d0a` |
| `--fail-ink` | `#ef6a55` | `#b8321f` |
| `--warm-ink` | `#f0a04b` | `#8f520f` |

All four meet 4.5:1 against `--panel`, `--panel-2` and `--ground` of their theme (lowest: night
`--fail-ink` 4.90, day `--pending-ink` 5.25).

Acceptance: the contrast rule above holds for both themes; hex colour literals appear only in `frontend/src/app.css`, `frontend/src/lib/ui/thermal.js`
and `frontend/src/lib/uplot.js`; no component uses the old variable names (`--bg`, `--text`,
`--primary`, …); `npm --prefix frontend run build` emits the font files into `dist/assets`.

### R2. Shell

- **Desktop (≥ 760 px):** a 76 px icon rail on the left (icon + short label per screen; Log and
  System at the bottom), and a sticky status strip at the top.
- **Phone (< 760 px):** the rail becomes a fixed bottom tab bar that scrolls horizontally, so all
  eight screens stay reachable.
- **Status strip:** pulse dot + online state (the dot pulses on every device message), age of the
  last message, operating mode, activity, error, broker state, firmware; then on the right the
  write-lock chip (green border when locked, amber when unlocked), the theme toggle and the
  language switch; the flush-error notice stays.
- **Theme** is browser-local like the language (localStorage key `heishamon.theme`, values
  `day`/`night`, absent = follow `prefers-color-scheme`). It is not a server pref.

Acceptance: every existing `data-testid` of the shell remains; the theme toggle switches
`document.documentElement.dataset.theme` and the choice survives a reload.

### R3. Overview

Layout (desktop): schematic panel and timeline in the left column, a side column with the *Now*
panel and the quick controls, then a row with the mini heating curve and recent events, then the
pinned tiles. On narrow screens everything stacks in that order.

**R3.1 Plant schematic.**

- **Built from the profile, never from the owner's setup** (main spec §1.1):
  - DHW branch and tank only when `dhw_installed` is true or unknown;
  - one emitter per active zone (`zones`: z1, z2 or both; unknown → z1);
  - a buffer tank on the zone branch when `buffer_installed` is true.
- **Readings** (a sentinel or missing topic shows `—`): outside temp (tag TT OUT), compressor
  frequency (tag SC CMP), flow (tag TT FLW, with target `Main_Target_Temp`), return (tag TT RET,
  with ΔT), pump flow (l/min, at the pump symbol), DHW temperature and target, and per zone
  `Z1/Z2_Water_Temp` when that sensor is present.
- **Live behaviour:**
  - pipes take the ramp colour of the water in them (flow pipes: `Main_Outlet_Temp`, return pipes:
    `Main_Inlet_Temp`);
  - the branch the three-way valve points at (`ThreeWay_Valve_State`: 0 room, 1 DHW) is drawn
    active; the other is dimmed;
  - when `Pump_Flow` > 0 a dash pattern moves along the active pipes, with a period inversely
    proportional to the flow;
  - the outdoor fan spins while `Compressor_Freq` > 0 and no defrost is running;
  - the title shows the current activity (`activityOf`) with a small qualifier (zone and control
    mode, DHW target, …).
- `prefers-reduced-motion: reduce` stops all movement; colours still update.
- On phones the schematic keeps a minimum width of 720 px and scrolls horizontally inside its panel.

**R3.2 Now panel.** The power figures follow the current activity (`activityOf`): DHW → the `dhw`
pair of `powerPairs(profile)`, cooling → the `cool` pair, everything else (heating, defrost,
idle) → the `heat` pair. The panel names the mode it shows ("Heating", "DHW", "Cooling"). Live COP
(or EER for cooling) is production / consumption of that pair as the big figure, `—` when either
value is missing or consumption is 0; `liveCop(values, profile, mode = 'heat')` gains the `mode`
argument (default unchanged). Power out / power in of that pair; for heating and DHW a bar splits
the output into electricity and ambient heat, hidden in cooling and when output ≤ input. Then
compressor frequency, pump flow, and today's consumed kWh and COP from
`GET /api/energy?period=day`: "today" is the period whose label equals the server-local date of
the response's `to` in the response's `tz` (`YYYY-MM-DD`, summed over all modes); when that
period is absent, or the call fails, the two cells are omitted.

**R3.3 Quick controls.** Same controls, gates, confirmation and per-control Apply as main spec §7.
Restyled: a control whose draft differs from the read-back gets the *draft* colour; the command
status uses the state colours.

**R3.4 24-hour timeline.** Replaces the per-tile sparklines as the main history view on the
Overview.

- One uPlot chart over the last 24 h:
  - an **activity band** at the top, derived per bucket from `Defrosting_State`,
    `ThreeWay_Valve_State`, `Heatpump_State` and the operating mode, in the activity colours;
  - temperature lines: flow (`--warm`), return (`--cool`), outside (`--cold`), target (dashed `--ink-3`);
  - total power in (the sum of the heat, cool and DHW consumption topics of `powerPairs(profile)`;
    a slot with none of them known is a gap) as a filled step area in the bottom quarter, on its own scale;
  - the temperature axis fits the plotted values (rounded out to 10 °C, so negative outside
    temperatures and high targets stay visible), 0–60 °C when there is no data.
- A single cursor; the panel header reads out all plotted values at the cursor (activity, flow,
  return, outside, target, power in), and the newest slot, labelled "now", when the cursor is away.
- Data from `GET /api/history` (≤ 20 topics, `max_points` 1500), refreshed every 5 minutes, never
  per live message. A 24 h range is served at 1-minute resolution (about 1440 buckets per topic;
  the backend keeps only the newest `max_points`), so 1500 covers the full day. The frontend
  reduces the buckets to a 5-minute display grid: 288 slots covering [now − 24 h, now), each
  plotted at its start. Outages (`breaks`) break the lines: every slot that overlaps a break is
  `null` for that topic, also when the break lies strictly inside the slot;
  a series flagged `truncated` is reported in the readout as incomplete rather than drawn as an outage.
- **Grid policy** per 5-minute slot, using only buckets with `covered_seconds` > 0:
  temperatures and power → the coverage-weighted mean of the slot's buckets (Σ avg·covered /
  Σ covered); `Defrosting_State`, `ThreeWay_Valve_State` → "on" when any bucket's average is > 0
  (so a short defrost or DHW run is never averaged away), else "off"; `Heatpump_State` → "on" when
  any bucket's average is ≥ 0.5, else "off"; `Operating_Mode_State` → the value of the last bucket
  whose average is within 0.01 of an integer, else `null`. A slot with no covered bucket for an
  input is `null` for that input.
- **The activity band is an approximation and is labelled so** ("approximate, from 1-minute
  averages"). The history API returns only per-minute averages of enum topics, so a minute that
  mixes two modes can average to a third, valid mode (0 and 2 average to 1); the band can then show
  the wrong mode for that minute. Exact categorical history would need a backend contract and is
  out of scope.
- **Activity per slot**, strict, in priority order — a lower-priority activity is only shown when
  every input needed to exclude the higher ones is known: defrost input `null` → **unknown**; on →
  defrost. Valve `null` → unknown; on → DHW. Heat-pump input `null` → unknown; off → idle. Mode
  `null`, or a mode in none of the mode sets → unknown; otherwise the mode's activity (heating,
  cooling, or DHW for a DHW-only mode). A slot inside a break is unknown. Unknown is drawn as a gap
  in the band, never as idle. Live state (status strip, schematic) keeps the existing lenient
  `activityOf` rule.

**R3.5 Mini curve and recent events.**

- **Mini curve:** a read-only preview of one zone/mode:
  - zone: zone 2 only when `zones` is `z2`; otherwise zone 1 (also with two zones, where the title
    says "zone 1" and the Heating curve screen holds both);
  - mode: cool when the current activity is cooling, or when `heating_in_use` is false and
    `cooling_in_use` is true; otherwise heat (also during DHW, defrost and idle);
  - hidden when `heating_in_use` and `cooling_in_use` are both false, or when the four curve values
    of that zone/mode are not all known;
  - curve control (`heating_control` / `cooling_control` = curve): the configured curve plus the
    dashed shifted curve (shift = `Z<n>_<Heat|Cool>_Request_Temp`);
  - direct control, not coupled: the configured curve is drawn inactive and labelled "not
    active", and the absolute setpoint (`Z<n>_<Heat|Cool>_Request_Temp`) as a horizontal line; no shift;
  - coupled (direct + room thermostat/thermistor, `isCoupled`): the setpoint is the curve's
    cold-end target, drawn as a horizontal line and labelled as such; no shift;
  - control mode unknown (field unknown or stale): a configuration-only preview — the curve drawn
    inactive, no shift line, no setpoint, labelled "control mode unknown";
  - direct control whose setpoint is not available (request topic missing or a sentinel; or, when
    coupled, no cold-end target): the curve drawn inactive and labelled "setpoint unavailable"; no
    shift, no setpoint line;
  - `CurveChart` gains an `inactive` prop that forces the inactive line style even when
    `directSetpoint` is null (today it draws the active curve whenever `directSetpoint` is null);
  - always the live marker (reported `Z<n>_Water_Target_Temp` and the measured water temperature
    at the current outside temperature);
  - these props mirror what the Heating curve screen passes to `CurveChart` for the same zone/mode.
  Links to the Heating curve screen.
- **Recent events:** the six newest entries from the events and command logs merged, with time,
  a colour key (activity colour for defrost events, state colours for commands and failures) and
  the same labels as the Log screen. Links to the Log.

**R3.6 Pinned tiles.** Tiles keep every main-spec §7 behaviour (pin, unpin, any catalogued topic,
prefs storage, 24 h sparkline). They move below the timeline as a compact strip of panels in the
new style. The sparkline fetch has the same truncation problem as R3.4 today (it asks for 96
points of 1-minute data, i.e. the last 96 minutes); it now asks for `max_points` 1500 and reduces
to 96 slots of 15 minutes in the frontend (coverage-weighted mean per slot; a slot without covered
buckets, or inside a break, stays `null` and is drawn as a gap), so the sparkline really covers 24 h.

Acceptance: the Overview renders the schematic, Now panel, quick controls, timeline, recent events
and tiles for every simulator preset without page errors or horizontal page overflow at 1280 px
and 390 px; the schematic follows the profile (no tank without DHW, two emitters for two zones).

### R4. Other screens

All screens move onto the tokens: panels, tags, Martian Mono for values, the temperature ramp for
temperatures. Specific rules:

- **Heating curve:** draft curve and handles in `--pending` while they differ from the current
  curve, the current curve as a dashed ghost in `--ink-3`; flat-end zones shaded `--panel-2` and
  labelled as an assumption; deviation colouring uses `--cold`/`--warm` instead of blue/red.
- **Charts:** the series palette starts with the ramp colours (`--warm`, `--cold`, …); enum bands
  use the new palette; axes take their colours from the current theme and redraw on a theme switch.
- **Topics:** dense table; key in Martian Mono with the subtree prefix in `--ink-3`; a changed
  value flashes `--warm` briefly; a value that is a sentinel shows as a bordered badge with the raw
  value and its meaning: −1 "unknown state", −128 "sensor absent", −78 "not connected", −127
  "unused" (EN/NL strings), any other sentinel the raw value alone.
- **Temperatures on every screen:** a value whose unit is °C (Overview tiles, Topics rows) carries
  a small dot in its ramp colour (`tempColor`) before the number; the number itself stays in
  `--ink` for contrast. Missing or sentinel values get no dot.
- **Heating curve handles:** a handle whose point differs from the current curve is drawn in
  `--pending`, overriding its cold/warm colour.

Acceptance: every screen is readable in both themes; no screen keeps a light-only colour.

## Architecture, interfaces, and data

Frontend only. Pure logic lives in small tested modules; Svelte components only render them.

| Module | Interface |
|---|---|
| `frontend/src/lib/ui/thermal.js` | `RAMP`, `ACTIVITY_VAR`, `mixRgb(a, b, f)`, `tempColor(t)` |
| `frontend/src/lib/theme.js` | `THEME_KEY = 'heishamon.theme'`, `themeChoice`, `resolvedTheme`, `initTheme({storage, media, root})`, `setTheme(choice)`, `cssVar(name, root?)` |
| `frontend/src/lib/domain/power.js` | `liveCop(values, profile, mode = 'heat')` — `mode` ∈ heat, cool, dhw selects the pair; default unchanged |
| `frontend/src/lib/domain/activity.js` | `activityFrom({defrost, valve, heatpump, mode}, {strict = false} = {})` — lenient (live, `format.activityOf` delegates to it) or strict (timeline: returns `'unknown'` per R3.4) |
| `frontend/src/lib/eventtext.js` | `kindLabel`, `commandLabel`, `detailText`, `eventTone`, `commandTone`, `recentItems` (shared by Log and Overview) |
| `frontend/src/features/overview/plant.js` | `plantModel(state, profile)`, `plantGeometry(model)` |
| `frontend/src/features/overview/timeline.js` | `timelineTopics`, `pointValue`, `toGrid` (5-minute grid with the R3.4 grid policy), `activityRuns` (strict, with `unknown`), `STEP_MS`, `HISTORY_POINTS = 1500` |
| `frontend/src/lib/uplot.js` | adds `buildSeries(series, Uplot)` (with a `stepped` flag) and `themedAxes(axes)` |

Data comes only from existing contracts: `/api/state` + WebSocket (live values), `/api/profile`,
`/api/history`, `/api/energy?period=day`, `/api/events`, `/api/commands`. No new endpoint, no prefs
change (the theme is localStorage only). New dependencies: `@fontsource/instrument-sans@5.3.0`,
`@fontsource-variable/martian-mono@5.3.0`.

Rejected alternatives: loading fonts from Google Fonts (privacy, offline use); keeping the tile
grid as the Overview's main view (does not show how values relate); a custom SVG timeline instead
of uPlot (main spec fixes uPlot for time series).

## Security, compatibility, rollout, and risks

- No security surface changes: no new endpoint, no new command path, no external request.
- Compatibility: every existing `data-testid` stays so existing Vitest and Playwright tests keep
  working; the theme key is new and browser-local.
- Rollout: on branch `feat/visual-redesign`; merging to `main` only when the owner asks.
- Risks: chart colours read from CSS at draw time must follow theme switches; the schematic is a
  fixed SVG geometry that must stay legible for one or two zones and with or without tank/buffer;
  a Pro-tier builder account limits parallel work.

## Verification

- `npm --prefix frontend run test` — all Vitest suites green, including new tests for the thermal
  ramp, theme, activity rule, plant model and schematic, Now panel, timeline helpers, event texts,
  mini-curve selection, and the token guard.
- `cd frontend && npx playwright test` — existing e2e suites plus `e2e/visual.spec.js` (theme
  toggle persists; schematic shows readings; all screens in day and night at 1280 and 390 px
  without overflow or page errors).
- `.venv/bin/python -m pytest backend/tests -q` — unchanged backend still green.
- `npm --prefix frontend run build` — succeeds with fonts in `dist/assets`.
- Timeline fixtures: a full day of 1-minute buckets keeps both the first and last hour; a mode
  change, a 1-minute defrost and an outage produce heating→defrost→heating runs and an unknown gap;
  a slot whose mode buckets are all fractional is unknown; a missing defrost or valve input makes
  the slot unknown; coverage weighting (a 1-second bucket barely moves the mean); the documented
  0→2 half-minute case is shown as approximate (cooling), proving the label is needed.
- Now panel fixtures for heating, DHW and cooling; mini-curve fixtures for two zones, direct,
  coupled, unknown control, and direct with a missing setpoint.
- Contrast: a unit test computes the WCAG ratio of `--ink`, `--ink-2`, `--ink-3` and the four
  `-ink` state tokens against `--panel`, `--panel-2` and `--ground` for both themes from `app.css`
  and requires ≥ 4.5; the token guard rejects `color: var(--ok|--pending|--fail|--warm)` in
  component styles (text must use the `-ink` variant).
- Visual comparison: the verifier puts the e2e screenshots of the Overview and Heating curve next
  to the mockup and reports deviations from the approved style (layout, palette, typography,
  schematic) as findings.
- Suites run one after another, never in parallel.
