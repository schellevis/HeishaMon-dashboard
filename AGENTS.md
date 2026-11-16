# AGENTS.md

Context and ground rules for AI agents (and humans) working on this repo.

## Project

A self-hosted, interactive web dashboard for Panasonic Aquarea heat pumps connected through
[HeishaMon](https://github.com/heishamon/HeishaMon), working exclusively over MQTT.

It has to let you see everything, set everything and log everything, and it includes a strong
heating-curve ("stooklijn") module.

**The design spec is the source of truth:**
`docs/superpowers/specs/2026-10-11-heishamon-dashboard-design.md`.

Status (2026-10-14): spec (revision 4.2, amended) written, plan executed, build complete and
independently verified (backend, frontend, simulator and capture tool). A review-fixes refactor
(command-safety fixes, HeishaMon conformity, security hardening, `rules.json`, module split) was
verified and merged into `main` on 2026-10-13. Open item:
the real-capture replay fixture, which the owner records with `tools/capture.py` (decision-006); that
test stays skipped until `backend/tests/fixtures/replay_real.json` exists. The Docker image was never
built in development; the release check is in the README.
A visual redesign (design tokens, day/night theme, new Overview with plant schematic, Now panel, 24-hour
timeline and mini curve) was built, verified and merged into `main` on 2026-11-16 (PR #1). Spec: `docs/superpowers/specs/2026-10-14-visual-design.md`; static mockup:
`docs/mockups/2026-10-14-redesign/index.html`.

**Workflow:** brainstorm → spec → implementation plan → build. Do not start building without an
approved plan.

## Hard rules

- **Public repo — never commit secrets or installation-specific data.**
  - Off limits: hostnames, IPs, usernames, passwords, MQTT captures that contain the `ip` topic, and so on.
  - Config comes from environment variables; local values live in `.env`, which is gitignored. Only `.env.example` is committed.
  - Editor swap files (`*.swp`) are ignored because they can contain `.env` contents.
  - The author's email in commits is fine.
- **The real MQTT broker** (credentials in `.env`) may be used **read-only** to observe behaviour.
  - Never publish to it — in particular nothing to `<base>/commands/…` — unless the user explicitly asks.
  - No destructive actions. The broker may also carry unrelated topics; ignore them.
- **Installation-agnostic.**
  - The dashboard must work for any HeishaMon installation and any operating mode. The owner switches modes a lot, and the repo is meant for others too.
  - Never hard-code the owner's setup. What they run serves only as a test fixture.
  - UI and behaviour are driven by a live *installation profile* derived from HeishaMon's configuration topics (spec §1.1, §4.3).
- **HeishaMon has no LICENSE file.** Do not copy its docs or code. Write the topic/command catalog in our own words, from facts.

## Decisions taken (see spec for detail)

**Stack and deployment:**

- Python 3.12 (`uv`), FastAPI + aiomqtt backend, and a Svelte + Vite static SPA frontend.
- uPlot for time series; hand-written SVG for the heating-curve editor.
- Deployment is one Docker container with a `/data` volume, run on an always-on home server or NAS.

**Storage:** SQLite (WAL).

- **No continuous disk writes:**
  - Everything is buffered in RAM and flushed in one transaction every 15 min (`FLUSH_INTERVAL_SECONDS`), on `SIGTERM`/`SIGINT`, and when the buffer passes a size cap.
  - Compose uses `stop_grace_period: 60s`.
  - Accepted risk: up to one interval of history is lost on a crash or power cut.
  - User prefs are the exception and are written immediately.
- **What is stored:**
  - only real changes (dedupe the 300 s full re-publish);
  - time-weighted 1-minute and 1-hour rollups;
  - a gaps table;
  - a command audit log;
  - an events table.
- History reads merge the DB with the unflushed buffer.

**Scope boundaries:**

- **No authentication.** It sits behind the user's reverse proxy; the README must warn loudly.
- **UI:** bilingual EN/NL (extensible string tables), responsive for desktop and phone equally.
- **Look and feel:** day and night themes (spec `2026-10-14-visual-design.md`). The theme is browser-local
  like the language: `localStorage` key `heishamon.theme`, falling back to `prefers-color-scheme`, never a
  server pref (`lib/theme.js`). Fonts are bundled through Fontsource (Instrument Sans, Martian Mono), so
  the UI makes no external font requests.
- **Out of scope:** `SendRawValue`, alerts/notifications, and room temperature from arbitrary external MQTT sources.
- **Deferred to the future:**
  - "Option B": integration with the HeishaMon device's HTTP interface (rules, device settings, console);
  - an auto-suggested heating curve, offered as a ghost curve only and never auto-applied.

## HeishaMon facts (verified against firmware source, commit `6c35bd9` = v4.2.3-1, and live observation)

Note: `heishamon/HeishaMon` and `Egyras/HeishaMon` are the same repository.

### Topics

- **Base topic:** default `panasonic_heat_pump`, configurable.
- **Published subtrees:**
  - `main/` — TOP0–143;
  - `extra/` — XTOP0–5. Only heat pumps with the extra data block (K/L series and newer) send it. When present, TOP15/16/38–41 are bogus; use XTOP instead.
  - `optional/` — OPT0–6. Only when optional PCB emulation is on.
  - `1wire/<addr>` and `1wire/<addr>/alias`;
  - `s0/{Watt,Watthour,WatthourTotal}/{1,2}`;
  - `opentherm/write/<name>`;
  - `stats` (JSON: uptime, heap, read counters, version, board, active rule count);
  - `LWT`, `ip`, `log`.
- **Subscribed by HeishaMon:** `commands/#`, `SendRawValue`, `opentherm/read/#`, `gpio/relay/…`, and its own `1wire/…` (to restore at boot).
- **Retain:**
  - All values are published **retained**, including 1-wire, S0 and `stats`.
  - Exceptions: the `Online` LWT message, the log, and raw data.
- **Change-only publishing:**
  - Values are sent only on change, plus a full re-publish every `updateAllTime` (default 300 s) and on the first MQTT connect.
  - Treat values as LOCF.
- **Polling:** every `waitTime` seconds. One observed installation averaged about 0.9 value msgs/s, plus `stats` and `LWT` every 5 s.
- **LWT quirk:**
  - The broker holds a retained `Offline` (the will), and HeishaMon sends a non-retained `Online` every 5 s.
  - Derive online state from live messages and recency, never from the retained LWT value.
- **"Not present" sentinels:**
  - `-1` — unknown state;
  - `-128` — absent sensor;
  - `-78` — unconnected NTC input;
  - `-127` — unused shift.
  
  These drive the "ignore topic" suggestions; the user decides.
- **Payloads:** plain text. TOP44 `Error` and TOP92 `Heat_Pump_Model` (hex bytes) are strings; everything else is numeric.

### Commands

- **Format:** publish the plain-text value to `<base>/commands/<Name>`.
  - The same is possible over HTTP: `GET /command?SetX=v`.
  - There are 64 commands: 50 standard (including `SetCurves`) plus 14 optional-PCB. PCB commands only work with emulation on.
- **Always publish commands NON-retained.**
  - HeishaMon subscribes to `commands/#`, so a retained command is re-executed on every reconnect.
  - That overrides later changes and wears the heat pump's EEPROM.
- **Only two documented exceptions use retain:**
  - `s0/WatthourTotal/{1,2}` — sync the S0 counter; read back at boot.
  - `opentherm/read/{dhw,ch}Set{Upp,Low}Bound`.
- **Parsing and validation:**
  - Most payloads are parsed as **integers** (`toInt()`), and booleans treat exactly `1` as on. The
    seven optional-PCB temperature commands parse decimals (spike-001, spec §3 / Appendix A.2).
  - The firmware does almost **no range validation**; only `SetSterilizationTemp` and `SetSterilizationMaxTime` are checked. The dashboard must validate.
- **Reliability and wear:**
  - The heat pump sometimes drops commands. Verify via the read-back topic and retry once after ~10 s.
  - Frequent writes wear the EEPROM, so only send on an explicit Apply.
- **Command quirks:**
  - `SetOperationMode` accepts 0–6, but the read side also reports 7 and 8 (the Auto(cool) variants).
  - Some commands are series-specific (e.g. the J-series heater settings).
  - Some require newer firmware, e.g. `SetHeaterOnOutdoorTemp` and `SetDHWHeaterState` need v4.1.2.
- **Optional PCB:**
  - State is persisted by HeishaMon in flash (`/optionalpcb.raw`, every 300 s), so no retain is needed.
  - With emulation on, if HeishaMon stops sending for ~40 s the heat pump raises **H74** and goes to standby.
  - PCB emulation also has to be enabled in the heat pump's service settings.
- **Listen-only mode:** HeishaMon never transmits and drops commands. It turns on automatically at boot if the line is busy, e.g. when a CZ-TAW1 is present.

### Heating curve

- **The naming is crosswise.** Upstream docs mislabel it, and the Homey integration shipped a bug because of it (issue #770).
  - `*_Heat_Curve_Target_High_Temp` pairs with `*_Heat_Curve_Outside_Low_Temp` → the **cold end**.
  - `*_Heat_Curve_Target_Low_Temp` pairs with `*_Heat_Curve_Outside_High_Temp` → the **warm end**.
  - The UI says "cold end / warm end", never "high/low".
- **`SetCurves` JSON:**
  - Format: `{"zone1|zone2":{"heat|cool":{"target":{"high","low"},"outside":{"high","low"}}}}`.
  - Partial JSON is allowed, and omitted keys stay unchanged.
  - Values are integers, stored as value+128, with no firmware range check.
  - Sensible limits (as used by the HA integration): heat outside −20..30 and target 15..75; cool outside 15..30 and target 5..20.
- **Request temperatures:**
  - `Set{Z1,Z2}{Heat,Cool}RequestTemperature` is a **−5..+5 shift** in curve mode, or an **absolute** temperature in direct mode.
  - The mode comes from `Heating_Mode` (TOP76) and `Cooling_Mode` (TOP81), where 0 = curve and 1 = direct.
  - With a thermostat or thermistor zone sensor in direct mode, the direct temperature is stored in the curve's `target.high`.
- **Related settings:**
  - `SetHeatingOffOutdoorTemp` (5..35, TOP77) and `SetHeaterOnOutdoorTemp` (−15..20, TOP78).
  - `Heat_To_Cool_Temp` and `Cool_To_Heat_Temp` are read-only.
- **Flat ends are unconfirmed.** Flat clamping beyond the two curve points is not confirmed by Panasonic docs; check it live against `Z1/Z2_Water_Target_Temp`.
- **The useful configuration topics for the installation profile:**
  - `Operating_Mode_State`, `Zones_State`;
  - `Heating_Mode`, `Cooling_Mode`;
  - `Z1/Z2_Sensor_Settings`;
  - `DHW_Installed`, `Buffer_Installed`, `Solar_Mode`, `Bivalent_Control`, `Liquid_Type`, `Optional_PCB`;
  - plus whether `extra/`, `optional/`, `1wire/`, `s0/` and `opentherm/` carry any traffic.

### Heating-curve UI research (patterns to reuse)

- **Draggable two-point handles:**
  - snap to 1 °C, cannot cross, synced numeric inputs;
  - plus a slope/level mode (like Daikin's two curve types).
- **Everyday shift kept separate from curve setup:** NIBE and Daikin offsets.
- **Draft, then apply:**
  - draw the draft as a ghost over the current curve, with a diff;
  - send one partial `SetCurves`;
  - confirm via read-back;
  - keep a change log with revert, and advise waiting 24–48 h before judging.
- **Live markers:** current outside temperature with reported target and actual water temperature. Warn if our model disagrees with the reported target.
- **Measured-data overlay:**
  - No existing tool overlays the configured curve on measured data. heatpumpmonitor.org's signature explorer comes closest, with scatter only.
  - Plot 15-minute averages of outside vs water temperature, per mode.
  - Filter out defrost, DHW runs plus settling time, compressor off, and the first ~10 minutes after compressor start.
  - Colour by water − target (default), COP, compressor frequency, before/after the last change. Offer room − setpoint only when a room sensor is configured.
  - Add a median line per 2 °C outside band and an hours-per-band histogram.

## Code layout

- Backend `backend/heishamon_dashboard/`: packages `commands/` (planner, gates, lifecycle, transport,
  service), `store/` (buffer, outages, records, rollups, queries, sqlite) and `api/` (one module per
  feature, `api.register(app, svc, static_dir)`), plus `catalog.json` (sections `topics`, `commands`, `inputs`
  and `models`; every command and input carries a required `ui_group`, topics and models do not) and `rules.json` (shared domain rules: curve limits and leaves, mode sets, power
  pairs, built-in tile ids).
- **`rules.json` is the single source for those rules.** Python reads it through `rules.py`, the
  frontend through `lib/domain/rules.js` (`$rules` alias). Do not re-declare them in code; a grep test
  (`test_rules.py`) fails on mode-set literals and curve-leaf patterns in the Python sources and the
  simulator. Other rules (power pairs, tiles, curve limits) are not grep-checked.
- Frontend `frontend/src/`: `app/` (shell and the route registry), `features/<id>/` (one folder per
  screen, default export `{id, navKey, order, component}`), `lib/` (stores, api, domain, commands
  controller, i18n, ui).
- **Design tokens:** colours, spacing and type live as CSS custom properties in `frontend/src/app.css`
  (one block per theme). Hex colours are allowed only in `app.css`, `lib/ui/thermal.js` (the temperature
  ramp), `lib/uplot.js` and the `lib/i18n/` files; `frontend/tests/tokens.test.js` fails otherwise.
  Components use `var(--…)`; charts read the active values with `cssVar()` from `lib/theme.js`.
  `frontend/tests/contrast.test.js` checks text contrast for both themes, so a token change can fail it.

## Development notes

- Use `uv`. When running Python against downloaded or untrusted files, use `python -I`.
- Run the app from a checkout with `.venv/bin/python -m heishamon_dashboard` (config from environment
  variables only; `STATIC_DIR` optionally points at the built SPA, default `frontend/dist`).
- **Testing:**
  - pytest for the backend (`backend/tests`) and Vitest plus Playwright for the frontend
    (`npm --prefix frontend run test`; Playwright in `frontend/e2e`, run from `frontend/`).
  - Vitest runs `frontend/tests/setup.js` first: it installs a no-op `ResizeObserver` and a global fake
    `uplot`, because jsdom has no canvas. A test that needs its own uPlot mock overrides it (see
    `charts.test.js`). Real charts are only exercised in Playwright.
  - `frontend/e2e/visual.spec.js` is slow. It walks every screen in both themes at desktop and phone width
    under one preset (`heat_dhw`), then renders the Overview again for every simulator preset. Run it on its
    own with `npx playwright test e2e/visual.spec.js` from `frontend/`.
  - A **simulator** with profile presets (heat-only, Heat+DHW, Cool+DHW, auto, two zones with mixed modes, thermostat sensor, no DHW tank, with/without `extra/`, PCB on) lets every UI variant be tested without a heat pump.
  - Replay fixtures must have the `ip` topic and any identifying data stripped.
  - Run the suites one after another, never in parallel. Playwright starts its own app, simulator and
    embedded broker on port 8765, and fails intermittently when pytest runs at the same time.
- Commit only when asked. The default branch is `main`.
- `CLAUDE.md` is a symlink to this file; edit `AGENTS.md` only.
