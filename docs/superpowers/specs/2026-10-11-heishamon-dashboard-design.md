# HeishaMon Dashboard — Design

Date: 2026-10-11
Status: draft, awaiting review

## 1. Goal

A self-hosted, interactive web dashboard for a Panasonic Aquarea heat pump connected through
[HeishaMon](https://github.com/heishamon/HeishaMon), talking to it exclusively over MQTT.

- **See everything**: every topic HeishaMon publishes, live and historical.
- **Set everything**: every MQTT command HeishaMon accepts, validated, with confirmation feedback.
- **Log everything**: all values, commands and derived events, stored long-term on local disk with minimal disk writes.
- A dedicated, high-quality **heating-curve (stooklijn) module**.

This is a public repository: no hostnames, IPs, credentials or other installation-specific
data may be committed. All configuration comes from environment variables; the repo only ships
`.env.example`.

### 1.1 Design principle: installation-agnostic

The dashboard is for any HeishaMon user, and for any way of running the heat pump. It must not
assume one installation or one operating mode.

**Usage patterns:** heating only, cooling only, auto, DHW only, Heat+DHW, Cool+DHW. One or two zones.
Curve or direct mode. Water temperature, external thermostat, internal thermostat or thermistor as
the zone sensor. With or without DHW tank, buffer, solar, pool, bivalent backup, glycol.

**Heat-pump capabilities:** with or without the `extra/` data block (K/L series and newer). Optional
PCB emulation, 1-wire, S0 and OpenTherm each on or off. Series-specific settings (e.g. J-series-only
heater settings).

The current mode can change at any time, and the UI follows it live.

**Adaptive, never hard-coded:** what is shown and offered comes from an **installation profile**
derived live from HeishaMon's own configuration topics (§4.3).

**Overridable:** the user can override every automatic choice — show a hidden section, pin or unpin
tiles, pick chart presets.

**Generic, not personal:** facts observed on the developer's installation serve only as test
fixtures, never as defaults. Defaults come from Panasonic/HeishaMon documentation.

**One heat pump per instance:** one HeishaMon (one base topic) per container. Run several containers
for several heat pumps.

**Firmware support:** HeishaMon ≥ v3.2.3, the current topic naming. Topics from older firmware, or
topics that are new and not yet catalogued, are still shown and logged as uncatalogued, raw values.

**Internationalisation:** the i18n structure supports adding languages beyond EN/NL without code
changes, through string tables plus catalog labels.

## 2. Scope

In scope:

- MQTT read of `<base>/#`: `main/`, `extra/`, `optional/`, `1wire/`, `s0/`, `opentherm/`, `stats`, `LWT`, `ip`, `log`.
  - Sections without traffic stay hidden.
- All 50 standard `commands/Set*` commands.
- The 14 optional-PCB commands, behind an opt-in toggle.
- `SetCurves`.
- OpenTherm `opentherm/read/*` inputs.
- The S0 `WatthourTotal` sync.
- Per-topic visible / hidden / ignored state, with automatic suggestions.
- Long-term storage, rollups, CSV export, derived energy/COP, command audit log, event log.
- Bilingual UI (English / Dutch, user-selectable), responsive for desktop and phone.
- Single Docker container.

Out of scope:

- **Authentication.** The dashboard has none; it is meant to sit behind a reverse proxy that does auth. The README must say so loudly.
- **`SendRawValue`.** Raw binary datagrams are too dangerous, and every useful setting already has a named command.
- **Room temperature from arbitrary external MQTT sources** (e.g. other sensors on the broker).
  - The heat pump's own room temperature topics are used only when the profile says a room sensor is configured for that zone (`Z1/Z2_Sensor_Settings` ≠ water temperature).
  - Otherwise they are treated as not meaningful.
- **Alerts / notifications.**

Future (explicitly deferred, not designed here):

- **Option B — HeishaMon device HTTP integration.** View and edit rules, device settings (poll interval, PCB emulation on/off, etc.) and the console, via the device's own HTTP endpoints.
- A heating-curve *suggestion* fitted from measured data, shown as a ghost curve the user can adopt; never auto-applied.

## 3. Facts about HeishaMon that shape the design

Verified against firmware source (commit `6c35bd9`, v4.2.3-1) and a 6.5-minute read-only capture of a
real installation running v4.2.1.

**Publishing behaviour:**

- All value topics are published **retained** (`MQTT_RETAIN_VALUES 1`).
  - A new subscriber receives a full snapshot immediately.
- Values are published **only on change**, plus a full re-publish every `updateAllTime` (default 300 s).
  - Storage must treat a value as valid until the next one (last observation carried forward, LOCF).
- The heat pump is polled every few seconds. The real installation averaged about 0.9 value messages/s, plus `stats` and `LWT` every 5 s.

**LWT:**

- The broker holds a *retained* `Offline` (the MQTT will).
- HeishaMon publishes a *non-retained* `Online` every 5 s.
- Online state must therefore be derived from message recency, never from the retained `LWT` value.

**Topic groups:**

- `extra/` (XTOP0–5) is only published by heat pumps with the extra data block. When it is present, TOP15/16/38–41 are bogus and should be suggested for hiding.
- `optional/` (OPT0–6) is only published when optional PCB emulation is enabled.

**"Not present" values:** `-1` (unknown state), `-128` (absent sensor), `-78` (unconnected NTC input),
`-127` (unused shift). These are the basis for ignore suggestions.

**Commands:**

- HeishaMon subscribes to `commands/#`. A **retained command would be re-executed on every HeishaMon reconnect**, so commands are always sent non-retained.
- The only documented exceptions, where retain is intended:
  - `s0/WatthourTotal/{1,2}` — sync the S0 counter; it is read back at boot.
  - `opentherm/read/{dhw,ch}Set{Upp,Low}Bound` — remembered across reboots.
- Command payloads are parsed as integers. Boolean commands treat exactly `1` as on. The firmware does almost **no range validation**, so the dashboard must validate.
- The README warns that commands are occasionally dropped (verify via the read topic, retry after ~10 s). It also warns that frequent writes wear the heat pump EEPROM.
- Optional-PCB state is persisted by HeishaMon itself in flash (`/optionalpcb.raw`, every 300 s). With PCB emulation on, if HeishaMon stops sending for ~40 s the heat pump raises H74.

**Heating-curve naming is crosswise:**

- `*_Target_High_Temp` pairs with `*_Outside_Low_Temp` (the **cold end**).
- `*_Target_Low_Temp` pairs with `*_Outside_High_Temp` (the **warm end**).
- Upstream docs describe this misleadingly, and at least one other integration shipped a bug because of it (HeishaMon issue #770).
- The UI never says "high/low" for curve points; it says "cold end / warm end".

**`SetCurves`:**

- Accepts partial JSON: `{"zone1|zone2":{"heat|cool":{"target":{"high","low"},"outside":{"high","low"}}}}`.
- Omitted keys are left unchanged.
- Integers only, no firmware range check.

HeishaMon has no LICENSE file. The topic/command catalog in this repo is written in our own words from the
facts above; upstream documentation is not copied.

## 4. Architecture

One Docker image, built in two stages:

1. Node builds the frontend.
2. A Python 3.12 runtime serves everything.

The data volume is `/data`, which holds the SQLite database.

```
                 ┌──────────────────────── container ─────────────────────────┐
 MQTT broker ◄──►│ mqtt ──► state (in-memory current values, online status)   │
                 │   │         │                                              │
                 │   │         ├──► store: RAM buffer ──(every 15 min / stop)──► SQLite (/data)
                 │   │         │                                              │
                 │   ◄── commands (validate, publish, confirm, retry, audit)  │
                 │                         ▲                                  │
                 │  api (FastAPI): REST + WebSocket ◄──► Svelte SPA (static)  │
                 └────────────────────────────────────────────────────────────┘
```

### 4.1 Backend modules (Python, FastAPI + aiomqtt)

Each module is a separate unit with a narrow interface.

- **`config`**
  - Reads environment variables:
    - `MQTT_HOST`, `MQTT_PORT`, `MQTT_USER`, `MQTT_PASSWORD`;
    - `MQTT_BASE_TOPIC` (default `panasonic_heat_pump`);
    - `MQTT_TLS` (optional);
    - `DATA_DIR` (default `/data`);
    - `FLUSH_INTERVAL_SECONDS` (default `900`);
    - `HTTP_PORT` (default `8000`);
    - `TZ`.
  - Fails fast on missing required settings.
- **`catalog`**
  - Static metadata shipped in the repo (`catalog.json`, or a Python module).
  - Per topic: key (e.g. `main/Outside_Temp`), upstream id (TOP14), kind (number / enum / text), unit, decimals, enum labels (EN+NL), category, known "not present" sentinel values, display name (EN+NL).
  - Per command: name, payload type, allowed values or range plus step, read-back topic(s) and how to compare, risk level (normal / confirm), whether retain is required (only the two exceptions), PCB-only flag, applicability notes (e.g. "J-series only"), minimum HeishaMon firmware version.
    - Commands newer than the firmware reported in `stats` are shown disabled, with an explanation. For example, `SetHeaterOnOutdoorTemp` needs v4.1.2.
    - Ranges that depend on the mode are expressed as conditions on the profile, e.g. `SetZ1HeatRequestTemperature` is −5..+5 in curve mode and an absolute temperature in direct mode.
  - Topics seen on MQTT but missing from the catalog (new firmware, 1-wire addresses) are still shown and stored, as "uncatalogued", with raw values.
- **`mqtt`**
  - Holds one connection and subscribes to `<base>/#`.
  - Reconnects with backoff.
  - Exposes `publish_command(name, payload)`, which is always non-retained.
  - Exposes a separate `publish_retained_exception(topic, payload)`, which only allows the two documented exception topics.
- **`state`**
  - Keeps the current value, last-change time and last-seen time per topic.
  - Derives online status:
    - `unknown` at startup, ignoring the retained `Offline`;
    - `online` once a live (non-retained) message arrives;
    - `offline` when a live `Offline` arrives (the broker delivering the will), or after 30 s without any message.
  - Fans live changes out to WebSocket clients.
- **`store`** — see §5.
- **`commands`**
  - Handles validation, publish, confirmation and retry — see §6.
- **`profile`** — see §4.3.
- **`derived`**
  - Live COP per mode, from production / consumption power pairs, when consumption > 0.
    - Uses the `extra/` power topics when the profile has them; otherwise the coarse `main/` ones.
  - Energy (kWh) per day, month and year, per mode, as the time integral of the power topics (computed from rollups).
  - Events: defrost start/end, error code change, operating-mode change, three-way-valve change, online/offline transitions.
- **`api`**
  - REST:
    - current state;
    - history (time-bucketed, merges DB and buffer);
    - CSV export;
    - commands (submit plus status);
    - command and event log;
    - prefs;
    - system info.
  - WebSocket: live value changes, command status updates, online status.

### 4.2 Frontend

- **Stack:** Svelte with Vite; a static SPA with no SSR. Built at image build time and served by FastAPI.
- **Charts:**
  - uPlot for time series (handles very large point counts).
  - Hand-written SVG for the heating-curve editor and its scatter overlay.
- **i18n:** one string table per language (EN and NL shipped). Enum labels come from the catalog. The language choice is stored in the browser.
- **Responsive layout:** side navigation on desktop, bottom navigation on phone; tables become cards on narrow screens.

### 4.3 Installation profile

The profile is a live, derived description of what this installation has and how it is running
right now. It is recomputed whenever one of its inputs changes. Screens, quick controls, chart
presets, the energy page, ignore suggestions and the curve module read from it; nothing reads the
raw configuration topics directly.

| Profile field | Source |
|---|---|
| operating mode (heat / cool / auto / DHW combinations) | `Operating_Mode_State` |
| heating / cooling / DHW in use | derived from the operating mode |
| zones active (Z1, Z2, both) | `Zones_State` |
| per zone and per heat/cool: curve or direct mode | `Heating_Mode`, `Cooling_Mode` |
| per zone: sensor type (water / ext. thermostat / int. thermostat / thermistor) | `Z1/Z2_Sensor_Settings` |
| DHW tank, buffer tank installed | `DHW_Installed`, `Buffer_Installed` |
| solar (off / buffer / DHW), bivalent, glycol | `Solar_Mode`, `Bivalent_Control`, `Liquid_Type` |
| extra data block present | any `extra/` traffic |
| optional PCB in the heat pump settings / emulation active | `Optional_PCB`, any `optional/` traffic |
| 1-wire, S0, OpenTherm present | any traffic in those subtrees |
| firmware version, board | `stats` |

**How the profile is used:**

- **Hiding:** a feature whose prerequisite is absent is hidden, with a "show anyway" override. An example is the Z2 controls when only Z1 is active.
- **Mode-dependent controls:** a control whose meaning depends on the mode adapts its label, unit and range live.
- **Unknown inputs:** when a profile input is unknown (`-1`, not yet received), the feature is shown rather than hidden.

## 5. Storage

Constraint: **no continuous disk writes**. Data is buffered in RAM and written in one transaction every
15 minutes (configurable), and on shutdown.

### 5.1 Write path

- **Ingest:** each incoming message is compared with the in-memory current value.
  - Only real changes are appended to the RAM buffer.
  - The periodic full re-publishes are deduplicated away.
  - `last_seen` is still updated in memory.
- **Buffer contents:** value changes, command records (and their status updates), and derived events.
- **Flush:** every `FLUSH_INTERVAL_SECONDS`, on `SIGTERM`/`SIGINT`, and early if the buffer exceeds a size cap (e.g. 200k entries).
  - One SQLite transaction: insert samples, events and commands, then update rollups for every bucket the flushed data touches.
- **Docker shutdown:** compose sets `stop_grace_period: 60s`, so `docker stop` leaves time to flush.
- **Accepted risk:** power loss, `kill -9` or a crash loses at most one flush interval of *history*.
  - Current state is restored immediately after restart from the retained topics.
- **Exception — user preferences** (topic visibility, PCB toggle, write lock and so on) are written immediately. They are rare and user-initiated, and losing them would be surprising.
- **SQLite settings:** WAL mode, `synchronous=NORMAL`, a single writer.

### 5.2 Schema (SQLite)

```sql
topics      (id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL)          -- e.g. 'main/Outside_Temp'
samples     (topic_id INTEGER, ts INTEGER, num REAL, txt TEXT,          -- ts = unix ms UTC; num for numeric/enum, txt for text
             PRIMARY KEY (topic_id, ts)) WITHOUT ROWID
rollup_1m   (topic_id INTEGER, bucket INTEGER, avg REAL, min REAL, max REAL, last REAL,
             PRIMARY KEY (topic_id, bucket)) WITHOUT ROWID
rollup_1h   (same columns as rollup_1m)
commands    (id INTEGER PRIMARY KEY, ts INTEGER, name TEXT, payload TEXT, retained INTEGER,
             prev_value TEXT, status TEXT,       -- pending | retried | confirmed | sent | failed | rejected
             confirmed_ts INTEGER, attempts INTEGER, detail TEXT)
events      (ts INTEGER, kind TEXT, detail TEXT)
prefs       (key TEXT PRIMARY KEY, value TEXT)  -- JSON values
gaps        (start_ts INTEGER, end_ts INTEGER)  -- periods with no data (dashboard down or HeishaMon offline)
```

**Rollups:**

- Numeric topics only.
- `avg` is **time-weighted** (LOCF within the bucket, carried in from the previous bucket).
- LOCF never spans a recorded gap.
- A gap is recorded when the dashboard starts after downtime, or when HeishaMon has been offline for more than 10 minutes. Charts break lines at gaps.

**Retention:** forever by default. An optional `RAW_RETENTION_DAYS` drops raw samples older than N days and keeps rollups.

**Expected size:** about 30M change rows per year, roughly 0.5–1 GB per year.

### 5.3 Read path

History queries choose their resolution from the requested range and width:

- raw samples for short ranges;
- `rollup_1m` for days;
- `rollup_1h` for months and years.

Results **merge DB rows with the unflushed RAM buffer**, so the latest minutes are always visible.

## 6. Commands

1. **Validate** against the catalog: type, range, step and allowed set. Reject (HTTP 422) otherwise.
2. **Gate checks:**
   - Reject with a clear error when:
     - the global **write lock** is on (UI toggle, persisted pref);
     - a PCB command is sent while the PCB section is disabled;
     - HeishaMon is offline.
   - Risky commands need an explicit confirmation flag from the UI:
     - heat pump off;
     - force defrost, force sterilization;
     - all PCB commands;
     - the two retained exceptions.
3. **Publish**
   - Non-retained, QoS 0 (HeishaMon's client is QoS 0).
   - Record `pending` with the previous read-back value.
4. **Confirm**
   - Wait for the read-back topic to match the expected value.
   - Set `confirmed` when it does.
   - After 10 s without a match, retry once (`retried`).
   - After another 10 s, set `failed`, with the last observed value in `detail`.
   - Commands without a reliable read-back (e.g. `SetPump`) are marked `sent`.
5. **Push** status changes over the WebSocket. Every command lands in the audit log.

**EEPROM protection:**

- Sliders and drag handles never send while moving; only an explicit **Apply** sends.
- The UI warns when the same setting has been changed more than a few times in the last hour.

## 7. Screens

A persistent status bar shows: online/offline, time since the last message, error code, the current
operating mode and activity (heating / cooling / DHW / defrost / idle), the write-lock toggle and the
language switch.

Every screen below is driven by the installation profile (§4.3). The lists are what can appear,
not what always appears.

1. **Overview**
   - **Tiles:**
     - The tile set follows the profile: e.g. a DHW tile only with a DHW tank, Z2 tiles only with two zones, buffer/solar/pool tiles only when configured, cooling power only when cooling is in use.
     - The default set covers outside temperature, flow/return temperature and ΔT, compressor frequency, power in/out, live COP, three-way valve and defrost.
     - Each tile has a 24 h sparkline.
     - The user can pin, unpin and reorder tiles, with any catalogued topic as a tile. This is stored as a pref.
   - **Quick controls**, adapting live to the profile:
     - heat pump on/off;
     - operating mode (all modes, whatever the current one);
     - quiet and powerful mode;
     - force DHW (only with a DHW tank, enabled only in a DHW-capable mode);
     - per active zone, the heat and/or cool request: a −5..+5 shift in curve mode, an absolute setpoint in direct mode, labelled accordingly;
     - DHW setpoint (only with a DHW tank).
2. **Charts**
   - Free topic selection plus presets: Temperatures, Power & COP, Compressor, Pump & pressure, DHW, Zones, Cooling.
     - Presets only include topics the profile marks as relevant and that aren't ignored.
     - Users can save their own presets.
   - Zoom and pan from 1 h to years.
   - Enum and state topics are drawn as coloured bands.
   - CSV export.
3. **Energy**
   - kWh per day, month and year, split heat / DHW / cool, consumed vs produced, plus COP/SCOP.
     - Splits with no data are omitted.
   - Uses the `extra/` power topics when available.
   - Without them it is labelled as an estimate, because the `main/` power values come in coarse steps of about 200 W.
   - When S0 meters are present, their measured kWh are shown alongside.
4. **Heating curve** — see §8.
5. **Heat pump settings**
   - All commands grouped by category: Operation, Zones, DHW, Sterilization, Heaters, Bivalent, Solar, Pump, Quiet/schedule, OpenTherm, S0, Optional PCB.
     - Optional PCB appears only when enabled, with the H74 warning and a note that PCB emulation must also be enabled on the device.
   - Categories irrelevant to the profile are collapsed, not removed. Users may want to change a setting that would *enable* a feature.
   - Applicability notes (e.g. "J-series only") are shown inline.
   - Each setting shows its current value, a validated input, Apply, and pending / confirmed / failed status.
   - The two retained exceptions live here as explicit actions with explanation.
6. **All topics**
   - Every topic: name, value with unit, raw value, last change, sparkline, and a visible / hidden / ignored selector.
   - Ignored topics are not stored.
   - An "ignore suggestions" panel lists:
     - topics stuck on a sentinel value for a long time;
     - TOP15/16/38–41 when `extra/` is present;
     - `optional/` when `Optional_PCB=0`.
   - The user decides; nothing is hidden automatically.
7. **Log** — the command audit log and derived events, filterable.
8. **System**
   - MQTT connection status.
   - HeishaMon `stats`: uptime, read quality, firmware version.
   - Database size, last flush time, a "flush now" button and the flush interval.
   - The PCB section toggle.

## 8. Heating-curve module

**Layout:**

- Tabs per zone and mode: Z1 heat, Z1 cool, Z2 heat, Z2 cool.
- All four tabs are always reachable, because people use different modes in different seasons.
  - Tabs for inactive zones or modes are de-emphasised, not removed.
  - The tab matching the current operating mode opens by default.
- Each tab shows a mode badge from `Heating_Mode` / `Cooling_Mode`:
  - **Curve mode:** the request temperature is a −5..+5 shift on the curve.
  - **Direct mode:** the request temperature is an absolute setpoint. The curve is still editable, because it is stored and will apply when switching back, but it is marked "not active".
  - **Thermostat/thermistor zone sensor in direct mode:** the direct temperature is stored in the curve's cold-end target. The UI shows it as the setpoint and explains this.

**Chart** (x: outside °C, y: water °C):

- **Configured curve:**
  - a line between the **cold end** (`Outside_Low`, `Target_High`) and the **warm end** (`Outside_High`, `Target_Low`);
  - flat beyond both ends.
- **Shift** (curve mode): a dashed line parallel to the curve, with a −5..+5 stepper. This is the everyday control and stays separate from curve editing.
- **Direct mode:** a horizontal line at the absolute setpoint.
- **Vertical markers** (heat tabs): "heater on below" (SET46, −15..20 °C) and "heating off above" (SET29, 5..35 °C). Both can be dragged.
- **Vertical markers** (auto mode): the heat↔cool switch temperatures (`Heat_To_Cool_Temp`, `Cool_To_Heat_Temp`). These are read-only, because HeishaMon has no command for them.
- **Live markers** at the current `Outside_Temp`:
  - the target the heat pump reports (`Z1_Water_Target_Temp` / `Z2_…`);
  - the actual water temperature: `Main_Outlet_Temp`, or `Z1/Z2_Water_Temp` when that zone has its own sensor.
- **Model warning:** shown if the model (curve + shift) disagrees with the reported target by more than 1 °C. This also verifies the flat-beyond-ends assumption on real data.

**Editing:**

- **Two-point mode:**
  - Drag handles that snap to 1 °C, mirrored in numeric inputs.
  - The handles cannot cross.
  - They stay within limits: heat outside −20..30 / target 15..75; cool outside 15..30 / target 5..20.
- **Slope/level mode:** moves or tilts both handles together.
- **Draft:**
  - Changes are a draft: a ghost curve over the current one, plus a small diff table.
- **Apply:**
  - Sends one `SetCurves` containing only the changed keys.
  - Confirmed once the matching read topics report the new values.
- **Log and revert:** every applied change is logged, with "revert to previous" and a hint to wait 24–48 h before judging the effect.

**Measured-data overlay** (the differentiator — no existing tool overlays the configured curve on measured data):

- **Scatter:** 15-minute averages of outside temperature vs actual water temperature over a selectable 7, 14 or 30 days or a custom range, drawn on the same axes as the curve.
  - Only intervals where the heat pump was running in *that tab's* mode are included: a heat tab uses heating intervals, a cool tab uses cooling intervals.
  - This works for any history, including periods where the operating mode changed.
- **Filtered out:**
  - defrost (`Defrosting_State`);
  - DHW runs (`ThreeWay_Valve_State` = DHW) plus a settling period, when a DHW tank exists;
  - compressor off (`Compressor_Freq` = 0);
  - the first ~10 minutes after compressor start.
- **Colour by:**
  - **water − target** (default; shows where the heat pump fails to reach its target);
  - COP;
  - compressor frequency;
  - before/after the last curve change;
  - room temperature − setpoint, offered only when the profile reports a room sensor for that zone.
- **Median line** per 2 °C outside band, plus a histogram of hours per band, so the user tunes where the heat pump actually spends its time.

## 9. Error handling

- **MQTT disconnect:**
  - The UI shows "broker disconnected".
  - The backend reconnects with backoff.
  - Commands are rejected while disconnected.
- **HeishaMon offline:** stale values are shown greyed out with their age, and commands are rejected.
- **Unparseable payload:** stored as text and shown as raw; never crash the ingest loop.
- **Flush failure (disk full, etc.):**
  - Keep the buffer.
  - Retry at the next interval.
  - Surface the error in the status bar and on the System page.
- **WebSocket drop:** the frontend reconnects and refetches current state.

## 10. Testing

- **Backend (pytest):**
  - catalog consistency: every command's read-back topic exists, ranges are sane, every enum has EN+NL labels;
  - payload parsing and sentinel detection;
  - change-dedup;
  - time-weighted rollups across bucket boundaries and gaps;
  - buffer flush and the DB+buffer merge on read;
  - flush on SIGTERM;
  - command validation, gating, the confirm / retry / fail state machine (fake clock);
  - the retained-exception allowlist;
  - curve math, including the crosswise mapping;
  - profile derivation and mode-dependent command ranges, run as a matrix test over representative profiles: heat-only single zone, Heat+DHW, Cool+DHW, auto, two zones with mixed curve/direct, thermostat sensor, no DHW tank, with/without `extra/`, PCB on.
- **Integration:**
  - A replay fixture built from a captured real MQTT session, with the `ip` topic and any identifying data stripped, run against an embedded test broker (e.g. amqtt) or a mocked client.
  - A small **simulator** that publishes a realistic HeishaMon topic stream and echoes commands back to read topics, for local development without a heat pump.
    - It takes a **profile preset** (the same representative profiles as above), so every UI variant can be exercised without owning that installation.
- **Frontend:**
  - Vitest for curve geometry, handle constraints, slope/level transforms and i18n completeness.
  - A Playwright smoke test against the simulator, run for several profile presets.

## 11. Repo layout (indicative)

```
backend/heishamon_dashboard/   config, catalog, mqtt, state, store, commands, derived, api
backend/heishamon_dashboard/catalog.json
backend/tests/
frontend/                      Svelte + Vite app
tools/simulator.py
Dockerfile, docker-compose.example.yml, .env.example, README.md
```
