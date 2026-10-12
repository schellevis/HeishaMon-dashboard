# HeishaMon Dashboard — Design

Date: 2026-10-11
Status: revision 4.2 — revision 4.1 plus the plan-review interface additions (overlay route, catalog
in the frontend build, real-capture replay deferred); firmware facts in
Appendix A. Implemented and independently verified; deviations the build introduced are noted in §4.4
(error codes) and §12 (`STATIC_DIR`)

**Where the authority lives:** this document fixes every behaviour, contract, schema and rule. Three
artefacts are *data* produced during the build and are test-enforced against this document, not
attached to it: the full `catalog.json` (Appendix A fixes its schema, its command inventory and the
rules it must satisfy), the replay fixture, and the numeric test fixtures (§5.4 gives the worked
timelines they must reproduce).

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

**Firmware compatibility contract (operative, not a claim):**

- The firmware version is parsed from `stats.version` with the normative rule in Appendix A.1. That
  rule handles `3.2.3`, two-component `3.9`/`4.0`, `3.61`, `v4.2.3` and suffixes. An absent or
  unparseable version, or a build string (`Local build`, `Alpha-…`, `Nightly-…`), is **unknown**,
  and unknown is treated as the **floor version 3.2.3**.
- Every catalog command carries `min_firmware` (Appendix A.2). Commands present at 3.2.3 have
  `min_firmware: "3.2.3"`. They are the **baseline set** and are available under an unknown
  version. A command whose `min_firmware` is above the detected (or assumed) version is disabled in
  the UI with an explanation. The **backend** rejects it with `422 firmware_too_old`, whatever the
  caller sends.
- `Operating_Mode_State` read values 7 and 8 (the Auto(cool) variants) are **informational**. They
  are displayed with a label, but forms never offer 7/8 as writable options; `SetOperationMode`
  accepts 0–6 only.
- The per-version facts (which commands, topics and stats fields exist at which release) come from
  the firmware spike, `reports/spike/spike-001--att-004.md`, summarised in Appendix A. A topic or
  command first seen in a later release carries its `min_firmware`. Topics also need no version
  gate to be *shown*: anything received is shown.
- **Oldest-version fixture:** the simulator has a `fw-3.2.3` preset. It publishes only the topics
  and stats format of 3.2.3 per Appendix A, and the acceptance matrix (A7) runs against it.

**Internationalisation:** the i18n structure supports adding languages beyond EN/NL without code
changes, through string tables plus catalog labels.

## 2. Scope

In scope:

- MQTT read of `<base>/#`: `main/`, `extra/`, `optional/`, `1wire/`, `s0/`, `opentherm/`, `stats`, `LWT`, `ip`, `log`.
  - Sections without traffic stay hidden.
- All 64 `commands/Set*` commands (Appendix A.2): 50 standard ones, `SetCurves` among them, plus the
  14 optional-PCB commands behind an opt-in toggle.
- OpenTherm `opentherm/read/*` inputs.
- The S0 `WatthourTotal` sync.
- Per-topic visible / hidden / ignored state, with automatic suggestions.
- Long-term storage, rollups, CSV export, derived energy/COP, command audit log, event log.
- Bilingual UI (English / Dutch, user-selectable), responsive for desktop and phone.
- Browser-origin protection (§13).
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

- **Topics the dashboard itself may publish to** (the *dashboard-writable set*): `<base>/commands/#`,
  `<base>/s0/WatthourTotal/{1,2}` (retained sync) and `<base>/opentherm/read/#`. Two of these are also
  read by HeishaMon, and `s0/WatthourTotal/{1,2}` is also *published* by HeishaMon as a value. A message on
  any of them can therefore be our own echo, so none of them ever counts as liveness or as a command
  confirmation (§4.1, §6).
- `extra/` (XTOP0–5) is only published by heat pumps with the extra data block. When it is present, TOP15/16/38–41 are bogus and should be suggested for hiding.
- `optional/` (OPT0–6) is only published when optional PCB emulation is enabled.

**"Not present" values:** `-1` (unknown state), `-128` (absent sensor), `-78` (unconnected NTC input),
`-127` (unused shift). These are the basis for ignore suggestions.

**Commands:**

- HeishaMon subscribes to `commands/#`. A **retained command would be re-executed on every HeishaMon reconnect**, so commands are always sent non-retained.
- The only documented exceptions, where retain is intended:
  - `s0/WatthourTotal/{1,2}` — sync the S0 counter; it is read back at boot.
  - `opentherm/read/{dhw,ch}Set{Upp,Low}Bound` — remembered across reboots.
- Most command payloads are parsed as integers, and boolean commands treat exactly `1` as on.
  - The seven optional-PCB temperature commands parse decimals.
  - `SetSterilizationTemp` and `SetSterilizationMaxTime` are strictly checked; three PCB state
    commands check only an upper bound.
  - Otherwise the firmware does **no range validation**, so the dashboard must validate
    (Appendix A.2).
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
  - Static metadata shipped in the repo as `backend/heishamon_dashboard/catalog.json`. Its schema,
    its rules and the command inventory are fixed in Appendix A.
  - Per topic: key (e.g. `main/Outside_Temp`), upstream id (TOP14), kind (number / enum / text), unit, decimals, enum labels (EN+NL), category, known "not present" sentinel values, display name (EN+NL).
  - Per command: name, payload type, allowed values or range plus step, read-back topic(s) and how to compare, risk level (normal / confirm), whether retain is required (only the two exceptions), PCB-only flag, applicability notes (e.g. "J-series only"), minimum HeishaMon firmware version.
    - Commands newer than the firmware reported in `stats` are shown disabled, with an explanation. For example, `SetHeaterOnOutdoorTemp` needs v4.1.2.
    - Ranges that depend on the mode are expressed as conditions on the profile, e.g. `SetZ1HeatRequestTemperature` is −5..+5 in curve mode and an absolute temperature in direct mode.
  - **Command inventory:** Appendix A.2 lists every command with its class, payload type,
    range or allowed set, read-back topic, comparison rule and `min_firmware`. `catalog.json` must
    contain exactly that inventory. A test fails on any command missing from it, any extra command,
    or any field that differs.
  - **Command classes:**
    - **setting:** idempotent and safe to retry.
    - **trigger:** force defrost, force sterilization and the other entries Appendix A marks as
      trigger. Never retried automatically; one explicit confirmation per send.
    - **retained exception:** the two retain paths. Sent once, with no confirmation cycle (§6).
    - **unverifiable:** a setting with no read-back topic. Marked `sent`; never retried.
    - **input:** a non-bound OpenTherm input. Published non-retained once and marked `sent`; never
      retried, with no confirmation cycle.
  - Topics seen on MQTT but missing from the catalog (new firmware, 1-wire addresses) are still shown and stored, as "uncatalogued", with raw values.
- **`mqtt`**
  - Holds one connection and subscribes to `<base>/#`.
  - Reconnects with backoff.
  - Exposes `publish_command(name, payload)`, which is always non-retained.
  - Exposes a separate `publish_retained_exception(topic, payload)`. It only allows the six
    retained paths: `s0/WatthourTotal/{1,2}` and `opentherm/read/{dhw,ch}Set{Upp,Low}Bound`.
  - Exposes `publish_input(topic, payload)`, always non-retained. It only allows the non-bound
    `opentherm/read/<name>` inputs listed in Appendix A.2.
  - **Publish allowlist:** these three are the only publish paths. Any other topic, or a topic
    sent through the wrong path, raises an error. A test enforces this for every catalog entry.
  - **Ingest limits:** a message whose topic exceeds 256 bytes or whose payload exceeds 64 KiB is
    dropped before parsing. It is counted in a per-flush `ingest_dropped` counter, written as one
    aggregated event per flush.
- **`state`**
  - Keeps the current value, last-change time and last-seen time per topic.
  - Tracks two separate connection states: **broker connected** (the MQTT client's own connection,
    with reconnect backoff) and **device online** (HeishaMon liveness). Both are surfaced to the UI.
  - Derives **device online** status with one ordered rule list, evaluated per received message.
    The first matching rule decides:
    1. **Retained flag set** (snapshot at subscribe time, or any retained delivery) → stored as a
       value, never liveness, never extends the recency clock.
    2. **Topic in the dashboard-writable set** (§3: `commands/#`, `s0/WatthourTotal/{1,2}`,
       `opentherm/read/#`) → stored as a value where catalogued, never liveness. This covers
       our own echoes and other controllers alike.
    3. **`<base>/LWT` with payload `Offline`** → `offline` immediately. Coverage stops at this
       message's timestamp (§5.2).
    4. **`<base>/LWT` with payload `Online`** (HeishaMon's non-retained heartbeat; interval per
       Appendix A.1) → qualifying.
    5. **Live message on `main/#`, `extra/#`, `optional/#`, `1wire/#`, `s0/Watt/#`,
       `s0/Watthour/#`, `opentherm/write/#` or `stats`** → qualifying.
    6. Anything else (e.g. `log`, `ip`, unknown subtrees) → stored or ignored as usual, never
       liveness.
  - **States:**
    - `unknown` at startup;
    - `online` on a qualifying message;
    - `offline` on rule 3, or when the liveness timeout passes without a qualifying message. The
      timeout is `max(30 s, 3 × median interval of the last 10 LWT=Online messages)`, because
      HeishaMon's heartbeat follows its configurable `waitTime` (Appendix A.1).
    - The timeout case is **backdated**: the outage starts at the last qualifying message's
      timestamp.
    - After `offline`, only a qualifying message (rules 4–5) returns the state to `online`.
  - Echo policy is topic-based, not content-based. The dashboard never needs to recognise its own
    messages; it only needs to never publish outside the dashboard-writable set, which the `mqtt`
    module enforces.
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
- **Catalog in the frontend:** the SPA imports `backend/heishamon_dashboard/catalog.json` at build
  time. It is the same file the backend loads, so there is no catalog API route and no drift between
  the two.
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
| heating control and cooling control: curve or direct (one value each, **shared by both zones**) | `Heating_Mode` (TOP76), `Cooling_Mode` (TOP81) |
| per zone: sensor type (water / ext. thermostat / int. thermostat / thermistor) | `Z1/Z2_Sensor_Settings` |
| DHW tank, buffer tank installed | `DHW_Installed`, `Buffer_Installed` |
| solar (off / buffer / DHW), bivalent, glycol | `Solar_Mode`, `Bivalent_Control`, `Liquid_Type` |
| extra data block present | any `extra/` traffic |
| optional PCB in the heat pump settings / emulation active | `Optional_PCB`, any `optional/` traffic |
| 1-wire, S0, OpenTherm present | any traffic in those subtrees |
| heat-pump model and series (J/K/L/other) | `Heat_Pump_Model` (TOP92) looked up by **exact string match** in the catalog's `models` table (Appendix A.3); no match → `series: null`, no series-specific features |
| pool configured | no pool topic exists in the current catalog; a pool tile appears only if a catalogued pool topic carries traffic (currently: never) |
| firmware version, board | `stats` |

**How the profile is used:**

- **Hiding:** a feature whose prerequisite is absent is hidden, with a "show anyway" override. An example is the Z2 controls when only Z1 is active.
- **Mode-dependent controls:** a control whose meaning depends on the mode adapts its label, unit and range live.
- **Unknown inputs:** when a profile input is unknown (`-1`, not yet received), the feature is shown rather than hidden.

**Profile schema (exact JSON, as served by `GET /api/profile` and the WebSocket):**

Every field `f` is serialized as `{"value": <v or null>, "unknown": bool, "stale": bool}`, written
`F<type>` below.

- `unknown` is true when the input was never received, or its last value is a sentinel or outside
  the enum's value set.
- `stale` is true when the input's `last_seen` is older than 660 s (two full re-publish periods
  plus 60 s) while the device is online.
- For gating (§6), a stale field counts as unknown. For display, a stale field keeps its last value.

```json
{
  "computed_at": 1760000000000,
  "operating_mode": F<int 0..8>,           // Operating_Mode_State; decode table Appendix A.4
  "heating_in_use": F<bool>, "cooling_in_use": F<bool>, "dhw_in_use": F<bool>,  // from operating_mode, A.4
  "zones": F<"z1"|"z2"|"both">,             // Zones_State
  "heating_control": F<"curve"|"direct">,   // Heating_Mode: 0 curve, 1 direct
  "cooling_control": F<"curve"|"direct">,   // Cooling_Mode: 0 curve, 1 direct
  "zone": {
    "z1": {"active": F<bool>, "sensor": F<"water"|"ext_thermostat"|"int_thermostat"|"thermistor">,
           "heat_control": F<…>, "cool_control": F<…>},   // inherited copies of heating_/cooling_control
    "z2": { …same… }
  },
  "dhw_installed": F<bool>, "buffer_installed": F<bool>,
  "solar": F<"off"|"buffer"|"dhw">, "bivalent": F<bool>, "glycol": F<bool>,
  "optional_pcb_setting": F<bool>,          // Optional_PCB
  "pcb_emulation_active": F<bool>,          // live optional/ message within the last 360 s
  "has_extra": F<bool>, "has_1wire": F<bool>, "has_s0": F<bool>,
  "has_opentherm": F<bool>,                 // opentherm/write/# or the pre-3.5 opentherm/<name> namespace
  "model": F<string>, "series": F<"J"|"K"|"L"|"other">,
  "firmware": F<string>, "firmware_assumed": bool,   // true when the version is unknown and 3.2.3 is assumed
  "board": F<string>
}
```

**Field rules:**

- **Shared control mode:** `heat_control` and `cool_control` under each zone are inherited copies
  of the installation-wide fields. They exist only so that consumers can read per-zone values; there
  is no per-zone source.
- **Presence fields** (`has_*`): a `has_*` field becomes true on any message in that subtree,
  retained or live, and false only after a full broker reconnect plus 360 s without any message in
  it. It is never unknown, starting at false.
- **Enum decodings:** the value sets and decodings of every enum input are fixed in Appendix A.4.

**Profile hiding versus topic visibility:**

- **Profile hiding** acts on *features* (sections, tiles, controls), with a per-feature "show
  anyway" override stored in prefs `feature_overrides`.
- **Topic visibility** acts on *topics*. `prefs.topic_visibility` holds only the user's
  **explicit** per-topic choices. A topic with no entry is visible, and ignore suggestions never
  write entries automatically.
- **Precedence for a topic's display:**
  1. an explicit `ignored` or `hidden` entry;
  2. otherwise the topic follows its feature's profile hiding (and that feature's override);
  3. otherwise visible.
- **Storage:** only `ignored` stops storage.

### 4.4 API and WebSocket contract

The frontend speaks only this contract; the backend implements exactly this contract. Timestamps are
unix milliseconds UTC. All request and response bodies are JSON (`application/json`); mutations
reject any other content type (CSRF protection, §13).

REST endpoints (all under `/api`). Shapes use the record types defined after the table.

| Method and path | Purpose | Request | Response |
|---|---|---|---|
| `GET /api/state` | full current snapshot | — | `State` |
| `GET /api/profile` | installation profile | — | `Profile` (§4.3) |
| `GET /api/history?topics=a,b&from=ts&to=ts&max_points=n` | history | ≤ 20 catalogue keys or raw topic names; `from < to`; `max_points` 10–10000 (default 1000) | `History` |
| `GET /api/history.csv?…` | same query as history | — | `text/csv` (see below) |
| `POST /api/command` | submit command or input | `{"name": str, "value": int \| number \| object, "confirm": bool}`, where `name` is a command name or a catalog input path (A.2), and the value type follows the entry's payload type (see "Value encoding" below) | `201 Command` (new record, `status` `pending` or `sent`), `200 Command` for a no-op (`status: "noop"`), `422 Error`, `503 Error` |
| `GET /api/commands/{uuid}` | command status | — | `Command` or `404` |
| `GET /api/commands?since=ts&limit=n` | audit log, newest first, `limit` ≤ 1000 (default 200) | — | `{"commands": [Command…]}` |
| `GET /api/events?since=ts&kind=k&limit=n` | event log, newest first | — | `{"events": [Event…]}` |
| `GET /api/prefs` | user preferences | — | `Prefs` |
| `PUT /api/prefs` | replace preferences | full `Prefs` object | `200 Prefs`; `422 Error` on unknown key or wrong type |
| `GET /api/system` | system status | — | `System` |
| `GET /api/overlay?zone=z1\|z2&mode=heat\|cool&from=ts&to=ts` | measured-data overlay (§8) | range ≤ 400 days | `Overlay` |
| `POST /api/system/flush` | flush now | `{}` | `202 {"flush_id": uuid}`; `409 Error` (`flush_in_progress`); result arrives as a `flush` event |

**Value encoding (submission → MQTT payload):**

- `int`, `bool`, `int2`, `int12`: the JSON value must be an integer literal. `2.0` is rejected with
  `bad_type`. The payload is the base-10 integer, zero-padded to two digits for `int2`.
- `dec1`: a finite JSON number with at most one fractional digit (checked as `round(v × 10)` within
  1e-9 of `v × 10`), within range and on the step grid. The payload has exactly one decimal digit:
  `20.5` → `"20.5"`, `20` → `"20.0"`.
- `dec3` (S0 total, Wh): a finite JSON number ≥ 0 with at most three fractional digits. The payload
  is plain decimal notation, never an exponent, with trailing zeros removed: `123456.789` →
  `"123456.789"`, `5000` → `"5000"`.
- `json` (`SetCurves`): an object; the payload is compact JSON with integer leaves.
- Fixtures (A2): `SetPoolTemp` 20.5 → `"20.5"`; `s0/WatthourTotal/1` 123456.789 → `"123456.789"`,
  published retained; `opentherm/read/outsideTemp` 7.5 → `"7.5"`, published non-retained.

**Record types (exact keys; `ts` = unix ms UTC):**

- `State`: `{"seq": int, "topics": {key: TopicValue}, "device_online": "unknown"|"online"|"offline",
  "last_device_message": ts|null, "broker_connected": bool, "listen_only_suspected": bool}`.
- `TopicValue`: `{"value": number|string|null, "raw": string, "kind": "number"|"enum"|"text",
  "unit": string|null, "decimals": int|null, "enum_label": {"en": str, "nl": str}|null,
  "catalogued": bool, "sentinel": bool, "last_change": ts, "last_seen": ts, "retained_only": bool}`.
  - `retained_only` is true until a live message for the topic arrives.
- `History`: `{"resolution": "raw"|"1m"|"1h", "partial": bool, "series": {key: Series}}`.
  - **Numeric `Series`:** `{"kind": "number"|"enum", "points": […], "coverage": […]|null,
    "breaks": [[start_ts, end_ts]…]}`. Coverage granularity depends on the resolution:
    - **`raw`:** points are `[ts, value]`, and `coverage` lists the exact covered intervals inside
      `[from, to]` (§5.2). The first point is the LOCF value carried in at `from` (with
      `ts = from`) when one exists.
    - **`1m`/`1h`:** points are `[bucket_start_ts, avg|null, covered_seconds]`, and `coverage` is
      `null`. Bucket-level coverage is the contract at rollup resolution, because rollups do not
      keep sub-bucket interval positions. This works identically before and after raw expiry.
    - `breaks` lists the outages (§5.2) longer than 10 minutes that apply to this topic. The chart
      breaks the line there. Outages are kept forever, so breaks are exact at every resolution.
  - **Text `Series`:** `{"kind": "text", "points": [[ts, string]…], "coverage": […], "breaks":
    […]}`. Text is always served at raw resolution regardless of the range. After raw expiry, text
    history older than the cutoff is unavailable, apart from the anchor.
  - `partial` is true when `max_points` truncated any series. In that case the newest points are
    kept.
- **CSV:** header `topic,ts,resolution,value,covered_seconds`; one row per point; `covered_seconds`
  is empty at raw resolution; text values are RFC 4180-quoted. The CSV export and `History` for the
  same query contain the same points (A4).
- `Command`: `{"id": uuid, "name": str, "payload": str, "retained": bool, "class":
  "setting"|"trigger"|"unverifiable"|"retained_exception"|"input", "status": "pending"|"retried"|
  "confirmed"|"sent"|"noop"|"superseded"|"failed", "submitted_ts": ts, "published_ts": ts|null,
  "confirmed_ts": ts|null, "attempts": int, "prev_value": str|null, "detail": str|null,
  "keys": {key: {"expected": int, "status": "pending"|"confirmed"|"failed"}}|null}`.
  - `keys` is used only by `SetCurves`.
  - Validation and gate rejections create no record. They are returned as `422`/`503 Error` and
    written to the event log as `command_rejected`.
- `Event`: `{"ts": ts, "kind": str, "detail": object}`. The `kind` values are listed in §5.2.
- `Prefs`: `{"write_lock": bool, "pcb_enabled": bool, "topic_visibility": {key:
  "visible"|"hidden"|"ignored"}, "feature_overrides": {feature_id: "show"}, "tiles": [key…],
  "chart_presets": [{"name": str, "topics": [key…]}]}`. All keys are required on `PUT`, and
  unknown keys are rejected. Language is **not** a pref: it lives in the browser (§4.2).
- `System`: `{"broker_connected": bool, "device_online": …, "firmware": str|null,
  "firmware_assumed": bool, "stats": object|null, "listen_only_suspected": bool, "db_bytes": int,
  "last_flush_ts": ts|null, "last_flush_ok": bool, "last_flush_error": str|null,
  "flush_interval_s": int, "buffer": {"samples": int, "sample_bytes": int, "protected": int},
  "dropped": {"samples": int, "ingest": int}}`.
- `Overlay`: `{"zone", "mode", "boundary_ts": ts|null, "windows": [{"start_ts": ts, "outside": num,
  "water": num, "target": num, "water_minus_target": num, "cop": num|null, "freq": num,
  "room_minus_setpoint": num|null, "side": "before"|"after"|"boundary"|null, "eligible_minutes": int}],
  "median": [{"band_lo": int, "value": num, "n": int}], "histogram": [{"band_lo": int, "hours": num}]}`.
  - It lists eligible windows only, computed by the backend exactly per §8 from full `rollup_1m`
    aggregates (avg/min/max/last/covered_seconds) with the read-time recompute of §5.2.
  - `side` is null when no `SetCurves` confirmation exists for that zone/mode.
- `Error`: `{"error": code, "message": str, "detail": object|null}`.
  - Codes: `out_of_range`, `bad_step`, `not_allowed_value`, `bad_type`, `unknown_command`,
    `write_lock`, `pcb_disabled`, `pcb_emulation_inactive`, `device_offline`,
    `broker_disconnected`, `firmware_too_old`, `profile_unknown`, `read_only_value`,
    `confirm_required`, `storage_unavailable`, `bad_origin`, `bad_host`, `flush_in_progress`,
    `bad_request` (400, malformed JSON), `not_found` (404, unknown route or command id),
    `method_not_allowed` (405). Any other framework HTTP error is reported as `http_error`.

**WebSocket `/api/ws`** (JSON messages, origin policy §13):

- **Ordering:** every server message carries a monotonically increasing `seq`, shared with
  `State.seq`. On connect, the server registers the client for fan-out **before** taking the
  snapshot. It then sends `{"type": "hello", "seq": n, "state": State, "profile": Profile}`, where
  `n` is the snapshot's seq. The client drops any later message with `seq ≤ n`. This makes hello a
  complete, gap-free resynchronization.
- **Other server → client messages:**
  - `{"type": "value", "seq", "topic": key, "value", "raw", "ts", "retained": bool}`;
  - `{"type": "profile", "seq", "profile": Profile}`;
  - `{"type": "command", "seq", "command": Command}`;
  - `{"type": "online", "seq", "device": …, "broker": bool, "ts"}`;
  - `{"type": "event", "seq", "event": Event}`.
- **Client → server:** none (the socket is read-only). Pings are protocol-level.

**Status codes:**

- `200`/`201`/`202` as above.
- `400` for malformed JSON.
- `403 bad_origin` / `bad_host` (§13).
- `404` for unknown routes and unknown command ids.
- `415` for a non-JSON mutation body.
- `422` for validation and gate rejections.
- `503` with `broker_disconnected` or `storage_unavailable`.
- `409 flush_in_progress` only for `POST /api/system/flush`. There is no `409` for commands. A newer command for the same read-back topic always succeeds;
  the older record moves to `superseded` and is pushed over the WebSocket (§6).

## 5. Storage

Constraint: **no continuous disk writes**. Data is buffered in RAM and written in one transaction every
15 minutes (configurable), and on shutdown.

### 5.1 Write path

- **Ingest:** each incoming message is compared with the in-memory current value.
  - Only real changes are appended to the RAM buffer.
  - The periodic full re-publishes are deduplicated away.
  - `last_seen` is still updated in memory.
- **Buffer contents:** value changes (*samples*); command records and their status updates and
  events (*protected records*); and liveness transitions (outage start/end, §5.2).
- **Flush:**
  - **When:** every `FLUSH_INTERVAL_SECONDS`, on `SIGTERM`/`SIGINT`, on `POST /api/system/flush`,
    and early when the sample buffer exceeds `BUFFER_MAX_ENTRIES` or `BUFFER_MAX_BYTES`.
  - **What:** one SQLite transaction. It inserts samples, protected records and outages, then
    recomputes rollups for **every bucket** of every numeric topic from that topic's
    `rollup_state.materialized_until` (the final horizon, §5.2) up to the flush time, replacing any
    provisional rows. Last, it writes the `frontier` row.
- **Sample overflow:** when a sample cap is hit and a flush fails or is impossible, the oldest
  samples are dropped first.
  - Entry and byte caps apply independently; whichever hits first triggers.
  - Each topic that lost at least one sample gets its own **topic-scoped** `dropped` outage
    (§5.2). It starts at that topic's oldest dropped sample and ends at that topic's oldest kept
    sample. If none was kept, it stays open until the topic's next received value, which is then
    stored even if it equals the last stored value (dedup is bypassed while the outage is open). Coverage is zero there, so no history is
    reconstructed across discarded changes.
  - One aggregated `buffer_overflow` event per flush cycle is kept and updated in place (count,
    first/last dropped ts). It does not grow with each drop.
- **Protected-record budget:** protected records are never dropped silently. Commands, events and
  outages count toward one unflushed cap, `AUDIT_BUFFER_MAX` (default 10,000; each `detail` is
  truncated to 2 KiB, so ≈ 25 MiB worst case).
  - **Command updates are in place:** a command's status changes update its single buffered record.
    A command flushed earlier and updated later gets one buffered update record.
  - **Reserves:** the last 66 slots are reserved, and no other producer may use them:
    - 64 for terminal updates of in-flight commands (at most 64 commands, one per catalog entry,
      can be in flight);
    - 2 for the saturation records below.
  - **Saturation** begins when the count reaches `AUDIT_BUFFER_MAX − 66`. From then on:
    - new command submissions are **rejected** with `503 storage_unavailable`;
    - derived events are no longer appended individually; one in-place `events_dropped` counter
      event (reserved slot 1) records how many and which kinds;
    - one **global** outage of kind `dropped`, starting at that instant, is opened (reserved slot
      2). While it is open, **no other outage record** of any kind or scope is appended. The
      saturation outage already gives every topic zero coverage, so discarding finer detail can
      never invent coverage.
    - **End of saturation:** the first successful flush closes the outage at its flush time. Normal
      outage tracking resumes from that instant; the current offline state reopens an `offline`
      outage at the same instant if the device is offline.
  - The total RAM envelope is therefore `BUFFER_MAX_BYTES` + ≈ 25 MiB + current state.
- **Docker shutdown:** compose sets `stop_grace_period: 60s`, so `docker stop` leaves time to flush.
- **Loss guarantee (exact):**
  - On a clean shutdown or successful flush nothing is lost.
  - A crash, power loss or `kill -9` loses everything since the last successful flush: at most one
    flush interval in normal operation.
  - During a **persistent storage failure** (disk full, I/O error):
    - samples beyond the caps are dropped oldest-first as above;
    - commands are refused once the audit budget is full, rather than being accepted unlogged;
    - everything still in RAM is lost if the process then dies.
  - The status bar and System page show the failure until a flush succeeds.
  - Current state is restored immediately after restart from the retained topics.
- **Exception — user preferences** are written immediately in their own small transaction. They are
  rare and user-initiated, and losing them would be surprising.
- **SQLite settings:** WAL mode, `synchronous=NORMAL`, a single writer.

### 5.2 Schema (SQLite)

```sql
schema_version (version INTEGER)                                   -- single row; checked at open, migrated forward
topics      (id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL)      -- e.g. 'main/Outside_Temp'
samples     (topic_id INTEGER, ts INTEGER, num REAL, txt TEXT,      -- ts = unix ms UTC; num for numeric/enum, txt for text
             valid INTEGER NOT NULL,                               -- 0 = sentinel or unparseable (no coverage)
             PRIMARY KEY (topic_id, ts)) WITHOUT ROWID
rollup_1m   (topic_id INTEGER, bucket INTEGER,                     -- bucket = unix seconds / 60, UTC-aligned
             first_ts INTEGER, last_ts INTEGER,                     -- first/last covered instant in the bucket (NULL if none)
             covered_seconds REAL NOT NULL,                        -- 0..60
             avg REAL, min REAL, max REAL, last REAL,              -- NULL when covered_seconds = 0
             PRIMARY KEY (topic_id, bucket)) WITHOUT ROWID
rollup_1h   (same columns as rollup_1m, bucket = unix seconds / 3600, covered_seconds 0..3600)
rollup_state(topic_id INTEGER PRIMARY KEY, materialized_until INTEGER)  -- ts up to which rollups are final or partial-written
commands    (id INTEGER PRIMARY KEY, uuid TEXT UNIQUE NOT NULL,    -- uuid is the public id (§4.4)
             submitted_ts INTEGER, published_ts INTEGER, name TEXT, payload TEXT, retained INTEGER,
             class TEXT, prev_value TEXT, status TEXT,             -- statuses as §4.4 Command
             confirmed_ts INTEGER, attempts INTEGER, detail TEXT, keys TEXT)  -- keys = JSON, SetCurves only
events      (ts INTEGER, kind TEXT, detail TEXT)                   -- detail = JSON
prefs       (key TEXT PRIMARY KEY, value TEXT)                     -- JSON values
outages     (start_ts INTEGER, end_ts INTEGER,                     -- end_ts NULL while open
             kind TEXT,                                            -- 'offline' | 'restart' | 'dropped' | 'ignored'
             topic_id INTEGER)                                     -- NULL = all topics; set for 'dropped' and 'ignored'
frontier    (id INTEGER PRIMARY KEY CHECK (id = 1),                -- single row, written by every flush
             flush_ts INTEGER, device_online INTEGER, last_qualifying_ts INTEGER)
```

**Event kinds:** `defrost_start`, `defrost_end`, `error_change`, `mode_change`, `valve_change`,
`device_online`, `device_offline`, `broker_connected`, `broker_disconnected`, `restart`, `flush`,
`flush_failed`, `buffer_overflow`, `events_dropped`, `ingest_dropped`, `command_rejected`,
`listen_only_suspected`, `listen_only_cleared`.

**Coverage (the single rule everything else uses):** a topic is *covered* at instant `t` when all
three of these hold:

1. a valid (non-sentinel, parseable) value for it is known at `t` by LOCF;
2. `t` lies inside no global outage and no outage scoped to this topic;
3. `t` is not before the first **live** qualifying device message after the latest restart.

Retained snapshots set the LOCF value, but they never start coverage on their own.

**Outages (the only source of coverage holes besides invalid values):**

- **`offline`:** from the device going offline (§4.1 — the backdated last qualifying message, or
  the live `Offline` LWT) until the next qualifying live message.
  - Every offline period is recorded, however short.
  - Charts break the line (`breaks` in the History output, §4.4) only for outages longer than
    10 minutes. Shorter ones are drawn as a continuous line, but their coverage is still zero.
- **`restart`:** from the previous run's last durable instant (`frontier.flush_ts` of the last
  successful flush; on a clean shutdown that is the shutdown flush) until the first qualifying live
  message of the new run.
  - An `offline` outage that was still open at that flush **stays open**. It is closed at the same
    instant as the restart outage, so the union of the two covers the whole span.
  - An outage is never closed at or before its own start.
- **`dropped`:** topic-scoped, see §5.1.
- **`ignored`:** topic-scoped. It starts when the user sets the topic to `ignored`. It ends at the
  topic's first received value after the user un-ignores it, and that value is stored even if
  unchanged. Ignoring therefore never lets LOCF carry a pre-ignore value across the ignored period.

**Rollups:**

- Numeric and enum topics only. Text topics have no rollups.
- `avg` is the time-weighted mean over covered seconds only.
- `min`/`max` are taken over covered instants.
- `last` is the value at the bucket's last covered instant.
- **Energy** is `Σ avg × covered_seconds` over buckets. No energy is ever invented across outages or
  invalid values.
- **Materialization and the final horizon:** a constant topic produces no samples, but its buckets
  still advance.
  - **Final horizon `H`:** each flush sets `H = flush_ts` when the device is already `offline`, and
    `H = last_qualifying_ts` when it is `online` or `unknown`. A later backdated offline outage
    always starts at or after `H`, so it can never change a bucket that is final.
  - Each flush recomputes every bucket from the previous `H` (stored as
    `rollup_state.materialized_until`) to the flush time, using DB samples, the buffer and the
    outages. Buckets with zero coverage get `covered_seconds = 0` and NULL aggregates.
  - Every row from `H` onward is **provisional**: it is written with `INSERT OR REPLACE` and
    recomputed by the next flush. Nothing is ever added twice.
  - 1-hour buckets are computed from their 60 one-minute rows (coverage-weighted), never from raw
    samples.
- **Read merge:** a history query recomputes, in memory, every bucket of every requested topic
  from `materialized_until` up to `min(to, now)`, using DB samples, the buffer and the outages. This
  includes constant topics with no buffered change. The device's current liveness counts as covered
  up to `now`, provisionally. The result **replaces** the DB rows for those buckets in the response;
  it is never added to them. The latest minutes are therefore always visible, constant topics
  included.
- **Timestamp collisions:** two changes on one topic within the same millisecond bump the second
  `ts` by 1 ms repeatedly until free (order-preserving).
- **Retention:** `RAW_RETENTION_DAYS` (≥ 1; empty = keep forever) deletes raw samples older than the
  cutoff, except one **anchor** per topic: the newest sample before the cutoff, which keeps the
  LOCF carry-in computable. Rollups are kept forever and never recomputed for buckets before the
  cutoff.
- **Expected size:** about 30M change rows per year, roughly 0.5–1 GB per year.

### 5.3 Read path

History queries choose their resolution from the requested range and `max_points`:

- raw samples when `(to − from) ≤ 6 h`, the raw point count fits `max_points`, **and** `from` is not
  before the raw-retention cutoff (`now − RAW_RETENTION_DAYS`). Exact raw coverage is only ever
  returned where raw validity transitions still exist. A query that touches expired raw history
  always uses `rollup_1m` (or `rollup_1h` beyond 14 days), whatever its length;
- `rollup_1m` when the range is ≤ 14 days;
- `rollup_1h` otherwise.

Results merge DB rows with the unflushed RAM buffer under the replace rule above, so the latest
minutes are always visible.

### 5.4 Worked timelines (normative: the A5 fixtures must reproduce these numbers)

Times are `hh:mm:ss` on one UTC day. The topic is `main/Heat_Power_Production` (W). Every
qualifying message refreshes liveness: HeishaMon sends `LWT=Online` and `stats` every 5 s, so the
device is online throughout unless stated otherwise.

**T1 — change inside a bucket, flush mid-bucket.**

- Samples: 1000 W at 00:00:00, 2000 W at 00:00:30. Flush at 00:01:30.
- Bucket 00:00: covered 60 s, avg 1500, min 1000, max 2000, last 2000; energy 90,000 J (0.025 kWh).
- Bucket 00:01 (partial): covered 30 s, avg 2000.
- A second flush at 00:02:00 with no new samples replaces bucket 00:01 with covered 60 s, avg 2000.
- Total energy after the second flush: 90,000 + 120,000 = 210,000 J.

**T2 — unchanged hours.**

- One sample: 500 W at 01:00:00. No change until a flush at 03:00:00.
- The flush writes 120 one-minute rows, each covered 60 s with avg 500, and two hour rows, each
  covered 3600 s with avg 500.
- Energy: 500 × 7200 = 3,600,000 J (1.0 kWh).

**T3 — short outage.**

- Samples: 1000 W at 04:00:00. The last qualifying message is at 04:02:10. Nothing more arrives
  until a qualifying message at 04:04:00 (the value is still 1000).
- At 04:02:40 (30 s timeout) the device goes `offline`, with the outage backdated to 04:02:10.
- Outage `offline` [04:02:10, 04:04:00]; 110 s, so the chart line stays continuous.
- Buckets:
  - 04:00 and 04:01: covered 60 s each;
  - 04:02: covered 10 s;
  - 04:03: covered 0 (avg NULL);
  - 04:04: covered from 04:04:00 onward.
- Energy over 04:00–04:05 at a flush at 04:05:00: 1000 × (60 + 60 + 10 + 0 + 60) = 190,000 J.

**T4 — restart with a retained snapshot.**

- The last successful flush is at 05:00:00 (`frontier.flush_ts`, device online). The dashboard
  crashes at 05:07:00, so samples between 05:00:00 and 05:07:00 are lost.
- It restarts at 05:20:00 and receives retained values at 05:20:01: 800 W, `retained_only`.
- The first live qualifying message (`LWT=Online`) arrives at 05:20:04.
- Outage `restart` [05:00:00, 05:20:04].
- Coverage for 05:00:00–05:20:04 is 0, and the line breaks (outage > 10 min).
- Covered from 05:20:04 with value 800. Bucket 05:20 gets covered 56 s, avg 800.

**T5 — failed flush with overflow.**

- Setup: `BUFFER_MAX_ENTRIES = 1000`; the disk is full from 06:00:00. Samples arrive at
  1 change/s on one topic from 06:00:00 at alternating 1000 and 2000 W (1000 at even seconds).
- At 06:16:40 the buffer holds 1000 samples. Each further sample drops the oldest.
- At 06:20:00 the buffer holds samples 06:03:20–06:19:59. Dropped samples 06:00:00–06:03:19
  form the topic-scoped outage `dropped` [06:00:00, 06:03:20]. The outage ends at the topic's first
  kept sample, so no value is ever carried across the discarded span.
- The disk recovers and the flush at 06:20:00 succeeds:
  - buckets 06:00–06:02 are covered 0;
  - bucket 06:03 is covered 40 s (06:03:20–06:04:00) with avg 1500, because coverage resumes at
    the first kept sample;
  - buckets 06:04–06:19 are covered 60 s with avg 1500.
- One `buffer_overflow` event with count 200.

**T6 — restart while already offline.**

- 1000 W since 04:00:00. The last qualifying message is at 04:02:10. At 04:02:40 the timeout
  opens the `offline` outage [04:02:10, open].
- The flush at 04:03:00 stores `frontier` = (flush 04:03:00, device_online 0, last_qualifying
  04:02:10).
- The process dies and restarts at 04:10:00. The first qualifying live message is at 04:10:05, with
  value 1000.
- Outages: `offline` [04:02:10, 04:10:05] (kept open through the restart) and `restart`
  [04:03:00, 04:10:05].
- Covered time in 04:00–04:11 at the flush at 04:11:00: 130 s + 55 s = 185 s. Energy 185,000 J.

**T7 — flush before a backdated timeout.**

- 1000 W since 04:00:00. The last qualifying message is at 04:02:10. A flush at 04:02:30 (device
  still online) sets `H` = 04:02:10. It writes bucket 04:02 as *provisional*, covered 30 s.
- At 04:02:40 the timeout opens `offline` [04:02:10, open]. Nothing more arrives.
- The flush at 04:05:00 recomputes from 04:02:10:
  - bucket 04:02: covered 10 s (replacing the provisional 30 s);
  - buckets 04:03 and 04:04: covered 0.
- Energy for 04:00–04:05: 130,000 J.

**T8 — only one topic's change dropped.**

- Topic A: 1000 W at 07:00:00 (flushed). From 07:00:30 the disk is full. A changes to 2000 W at
  07:01:00. Topic B changes every second.
- Overflow drops the oldest samples, including A's 07:01:00 sample and B's samples up to
  07:02:00.
- Outages:
  - A gets `dropped`, topic-scoped, [07:01:00, open], because A has no kept sample;
  - B gets `dropped` [07:00:30, its oldest kept sample].
- A's full re-publish at 07:05:00 (2000 W) closes A's outage and is stored.
- A is covered at 1000 W for 07:00:00–07:01:00, covered 0 for 07:01:00–07:05:00, and covered at
  2000 W from 07:05:00. A's LOCF never carries 1000 W past 07:01:00.

**T9 — ignore and un-ignore.**

- A is 500 W (covered) and is set to `ignored` at 08:00:00. It is un-ignored at 08:30:00, and its
  next message arrives at 08:31:00 (500 W).
- Outage `ignored` [08:00:00, 08:31:00]. A is covered 0 in that span, and the sample at 08:31:00
  is stored.

## 6. Commands

Each submission passes through these steps in order. A rejection at steps 1–3 creates no command
record; it is returned as an `Error` and logged as a `command_rejected` event.

1. **Validate** against the catalog (Appendix A.2): payload type, range, step and allowed set,
   including conditional ranges (mode- or sensor-dependent). On failure: `422` with
   `out_of_range`, `bad_step`, `not_allowed_value`, `bad_type` or `unknown_command`.
2. **Gates** — all enforced in the backend. The UI mirrors them, but they are never UI-only. Checked
   in this order:
   1. broker disconnected → `503 broker_disconnected`;
   2. device not `online` → `422 device_offline`;
   3. write lock on → `422 write_lock`;
   4. PCB command while `prefs.pcb_enabled` is off → `422 pcb_disabled`;
   5. PCB command while `profile.pcb_emulation_active` is not true → `422 pcb_emulation_inactive`;
   6. `min_firmware` above the detected version (or above 3.2.3 when the version is unknown) →
      `422 firmware_too_old`;
   7. an applicability condition depends on a profile field that is unknown or stale, and the
      catalog entry is not `safe_under_unknown` → `422 profile_unknown`, naming the field;
   8. a value that is read-only on the write side (operation modes 7/8) → `422 read_only_value`;
   9. a risky command without `confirm: true` → `422 confirm_required`.
      - Risky commands: heat pump off, all triggers, all PCB commands, both retained exceptions.
   10. the protected-record budget is full (§5.1) → `503 storage_unavailable`.
3. **No-op check** (settings only): if the read-back topic's current value equals the requested
   value, and that value was received live (not `retained_only`) within the last 660 s, nothing is
   published.
   - A record with `status: noop` is created and returned with `200`.
   - This avoids needless EEPROM writes and false failures from change-only publishing.
   - For `SetCurves`, keys whose current value already matches are removed from the payload. If no
     key remains, the result is a no-op.
4. **Supersede:** at most one in-flight record per read-back topic.
   - A new record whose read-back topics intersect those of an in-flight record moves that older
     record to `superseded`, atomically. Its retry timer is cancelled, and for `SetCurves` all its
     keys stop, including those not repeated in the new command.
   - The new command then proceeds. The status change is pushed over the WebSocket.
5. **Publish:**
   - Settings, triggers and unverifiable commands are published non-retained, QoS 0, through
     `publish_command`.
   - Retained exceptions are published through `publish_retained_exception`.
   - The record gets `published_ts`, `prev_value` (the read-back value at publish) and `attempts: 1`.
   - Status: `pending` for settings; `sent` for triggers, unverifiable commands and retained
     exceptions. The last three never enter a confirmation cycle and are never retried.
6. **Confirm** (settings only):
   - A read-back message confirms only if it is **fresh**: it arrives after `published_ts` and is
     not retained.
   - A command is `confirmed` when every expected key has a fresh matching value. A single-topic
     command has exactly one key.
   - Each key records its own status. A key that matched stays confirmed even if a later message
     differs.
7. **Retry:**
   - At `published_ts + 10 s`, any key still pending triggers **one** retry.
   - Before retrying, steps 1–2 are re-run **in full** (every gate, against the current profile and
     state), and the command's meaning is re-checked: a conditional range or control mode used at
     submission must still be the same.
     - Any failure → `failed`, with `detail` set to the error code (or `meaning_changed`). Nothing
       is published.
   - Otherwise only the unconfirmed keys are re-published, `attempts: 2` and `retried`.
8. **Terminal failure:** at `published_ts + 20 s` (that is, 10 s after the retry), any key still
   pending makes the record `failed`.
   - `detail` gives the last observed value per failed key.
   - Confirmed keys stay confirmed in `keys`, so a partial `SetCurves` shows exactly which keys
     failed.
9. **Listen-only (suspected):**
   - **Set:** `listen_only_suspected` becomes true when **3 consecutive** settings end `failed` with
     no change at all on their read-back topics, while the device stayed online and other device
     values kept changing, within 30 minutes.
   - No MQTT topic reports listen-only at any version (Appendix A.1), so this heuristic is the only
     mechanism.
   - **Cleared:** on any `confirmed` command.
   - **Effect:** it shows a banner ("commands may be ignored — HeishaMon may be in listen-only
     mode"). Commands are still sent, and their statuses stay truthful (`failed` remains `failed`).
   - Transitions are logged as events.
10. **Push** every status change over the WebSocket. Every record lands in the audit log.

**Retained exceptions and inputs:**

- The retained exceptions are the `s0/WatthourTotal/{1,2}` sync and the four OpenTherm bounds. The
  inputs are the non-bound `opentherm/read/<name>` entries.
- Both are marked `sent` after publish. Only the retained exceptions are published retained.
- They have no confirmation cycle, because their topics are in the dashboard-writable set and any
  echo is indistinguishable from our own publish.
- The UI says "sent". For S0 it adds "HeishaMon reads this at its next MQTT (re)connect"
  (Appendix A.1).
- For S0, it shows the device-published `s0/WatthourTotal/n` value next to the sent value without
  calling it a confirmation.

**EEPROM protection:**

- Sliders and drag handles never send while moving; only an explicit **Apply** sends.
- The UI warns when the same setting has been changed **3 or more times in the last 60 minutes**
  (counted from records with status `confirmed`, `retried` or `failed`).

## 7. Screens

A persistent status bar shows: online/offline, time since the last message, error code, the current
operating mode and activity (heating / cooling / DHW / defrost / idle), the write-lock toggle and the
language switch.

Every screen below is driven by the installation profile (§4.3). The lists are what can appear,
not what always appears.

1. **Overview**
   - **Tiles:**
     - The tile set follows the profile: e.g. a DHW tile only with a DHW tank, Z2 tiles only with two zones, buffer/solar tiles only when configured, a pool tile only if a catalogued pool topic carries traffic (none exists today), cooling power only when cooling is in use.
     - The default set covers outside temperature, flow/return temperature and ΔT, compressor frequency, power in/out, live COP, three-way valve and defrost.
     - Each tile has a 24 h sparkline.
     - The user can pin, unpin and reorder tiles, with any catalogued topic as a tile. This is stored as a pref.
   - **Quick controls**, adapting live to the profile:
     - heat pump on/off;
     - operating mode (all modes, whatever the current one);
     - quiet and powerful mode;
     - force DHW (only with a DHW tank, enabled only in a DHW-capable mode);
     - per active zone, the heat and/or cool request: a −5..+5 shift in curve mode, an absolute setpoint in direct mode, labelled accordingly. In **coupled** mode (direct control with a thermostat/thermistor zone sensor, §8) the control reads and writes the curve's cold-end target (`Z1/Z2_{Heat,Cool}_Curve_Target_High_Temp`) via a partial `SetCurves` with read-back on that leaf, and explains inline that the setpoint is stored there; the request-temperature read-back is not shown as the setpoint;
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
     - topics stuck on a sentinel value for 24 hours;
     - TOP15/16/38–41 when `extra/` is present;
     - `optional/` when `Optional_PCB=0`.
   - The user decides; nothing is hidden automatically.
7. **Log** — the command audit log and derived events, filterable.
8. **System**
   - MQTT connection status.
   - HeishaMon `stats`: uptime, read quality, firmware version.
   - Database size, last flush time, a "flush now" button (`POST /api/system/flush`) and the flush interval.
   - The PCB section toggle.

## 8. Heating-curve module

**Layout:**

- Tabs per zone and mode: Z1 heat, Z1 cool, Z2 heat, Z2 cool.
- All four tabs are always reachable, because people use different modes in different seasons.
  - Tabs for inactive zones or modes are de-emphasised, not removed.
  - The tab matching the current operating mode opens by default.
- Each tab shows a mode badge from `Heating_Mode` / `Cooling_Mode`:
  - **Curve mode:** the request temperature is a −5..+5 shift on the curve.
  - **Direct mode:** the request temperature is an absolute setpoint. The curve is still editable, because it is stored and will apply when switching back, but it is marked "not active" — with the explicit exception of the coupled cold-end target in thermostat/thermistor sensor mode (next bullet), where editing the curve's cold-end target **is** editing the active setpoint, and the editor says so inline.
  - **Thermostat/thermistor zone sensor in direct mode ("coupled"):** the direct temperature is stored in the curve's cold-end target. The UI shows it as the setpoint and explains this.
    - Observed live on such an installation: `Z1/Z2_Heat_Request_Temp` stays 0 while the reported `Z1_Water_Target_Temp` follows `Z1_Heat_Curve_Target_High_Temp` through changes; the warm-end target (`Target_Low`) keeps an unrelated, higher value and has no effect.
    - Coupled is decided per zone and mode from the profile: `heating_control`/`cooling_control` = direct and `zone.zN.sensor` ∈ {external thermostat, internal thermostat, thermistor}. When either field is unknown or stale, the zone/mode is treated as not coupled.

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
- **Model warning:** the flat-beyond-ends rendering is an explicit, labelled *model assumption*
  (unconfirmed by Panasonic docs; check it against `Z1/Z2_Water_Target_Temp` on real data). A
  warning is shown if the model (curve + shift) disagrees with the reported target by more than
  1 °C — noting that a discrepancy can also come from current activity (DHW, defrost, standby) or
  the active control mode, not only from endpoint clamping.

**Editing:**

- **Ordering invariant** (heat and cool alike, following the crosswise naming in §3):
  - `outside.low + 1 ≤ outside.high`, so the cold end lies strictly left of the warm end;
  - `target.high ≥ target.low`, so the cold-end target is never below the warm-end target. Equality
    (a flat curve) is allowed.
  - **Exception — coupled zone/mode** (direct control + thermostat/thermistor sensor, see Layout):
    the target-ordering rule is dropped for that zone and mode, because the cold-end target is the
    setpoint and the warm-end target is unused; real installations hold `target.high < target.low`
    in this mode. The outside ordering and the limits still apply. This holds in the editor (drag,
    inputs, slope/level) and in the backend `SetCurves` validation, and the editor hint says so.
- **Limits:** heat outside −20..30 / target 15..75; cool outside 15..30 / target 5..20.
- **Two-point mode:**
  - Drag handles snap to 1 °C and are mirrored in numeric inputs.
  - A drag or input that would break the ordering invariant or a limit stops at the last valid
    integer: the handle cannot pass it.
- **Slope/level mode:** the outside points stay fixed, and only the two targets move, in 1 °C
  steps.
  - **Level ±1:** both targets change by ±1.
  - **Slope ±1:** the cold-end target changes by ±1 and the warm-end target by ∓1, so `+1` steepens
    the curve.
  - A step that would break a limit or the ordering invariant is refused **as a whole**: the
    button is disabled, and there is never per-handle clamping that would silently change the
    shape.
- **Draft:**
  - Changes are a draft: a ghost curve over the current one, plus a small diff table.
- **Apply:**
  - Curve changes send **one `SetCurves`** containing only the changed keys, after the §6 no-op
    removal.
  - The command's `keys` map lists every sent key with its expected value. Confirmation, retry and
    failure are per key exactly as §6 steps 6–8. The editor shows each key's status, and a partial
    failure names the failed keys.
  - The threshold markers (`SetHeaterOnOutdoorTemp`, `SetHeatingOffOutdoorTemp`) have their **own
    separate Apply buttons and confirm cycles**. They are never silently folded into the curve
    `SetCurves` send. The draft diff table groups pending changes by command, so nothing is sent by
    surprise.
- **Log and revert:** every applied change is logged, with "revert to previous" and a hint to wait 24–48 h before judging the effect.

**Measured-data overlay** (the differentiator — no existing tool overlays the configured curve on
measured data). This is a **declared minute-level approximation**: every rule is evaluated per
1-minute bucket from `rollup_1m` (`min`/`max`/`avg`/`covered_seconds`), conservatively, so a minute
with any doubt is excluded. Results are therefore reproducible from rollups alone, survive raw
expiry, and never depend on sub-minute ordering.

- **Topics per tab:**
  - outside temperature `Outside_Temp`;
  - water temperature `Main_Outlet_Temp`, or `Z1/Z2_Water_Temp` when the zone has its own sensor;
  - target `Z1/Z2_Water_Target_Temp`;
  - state topics `Operating_Mode_State`, `ThreeWay_Valve_State`, `Defrosting_State` and
    `Compressor_Freq`;
  - power topics per §4.1 `derived`;
  - `Z1/Z2_Sensor_Settings`.
- **Minute eligibility** (all conditions must hold for the minute):
  1. every involved topic has `covered_seconds = 60`;
  2. `Defrosting_State` `max = 0`;
  3. the `ThreeWay_Valve_State` `min` and `max` both equal the room/heating position (no DHW at any
     point in the minute);
  4. `Compressor_Freq` `min > 0`, so the compressor ran the whole minute;
  5. `Operating_Mode_State` `min = max`, and that value belongs to the tab's mode set (Appendix
     A.4): heat tabs use the modes that include heating, including Auto(heat); cool tabs use the
     modes that include cooling, including Auto(cool) 7/8;
  6. **startup exclusion:** none of the preceding 10 minutes failed condition 4 or lacked coverage
     for `Compressor_Freq`;
  7. **DHW settling:** none of the preceding 10 minutes had the valve in the DHW position at any
     point (`max` or `min` = DHW).
- **15-minute windows:**
  - Windows are aligned to UTC quarter-hours.
  - A window is **eligible** when at least 12 of its 15 minutes are eligible (80 %). Otherwise it
    is dropped; partial windows are never guessed.
  - Each window value is the mean, over its eligible minutes, of those minutes' `avg`.
- **Scatter:** eligible windows' (outside, water) pairs over 7, 14 or 30 days or a custom range,
  on the curve's axes.
- **Colour by:**
  - **water − target** (default);
  - **COP** = Σ production avg / Σ consumption avg over the eligible minutes. When the consumption
    sum ≤ 0, the point is grey with the label "no COP";
  - **compressor frequency** (window mean);
  - **before/after the last curve change**: the boundary is the `confirmed_ts` of the newest
    `SetCurves` record whose keys include this tab's zone/mode. A window containing the boundary is
    shown as neither (outlined);
  - **room − setpoint**: offered only for windows where that window's own `Z1/Z2_Sensor_Settings`
    `last` value says a room sensor is configured. This uses the historical value, never the
    current profile.
- **Median line:**
  - Bands are `[2k, 2k+2)` °C by window outside mean.
  - The line is the plain median of the window water means in that band (each window weighs equally).
  - It is drawn only for bands with ≥ 3 windows.
- **Histogram:** hours per band = (eligible minutes in that band's eligible windows) / 60.

## 9. Error handling

- **MQTT disconnect:**
  - The UI shows "broker disconnected".
  - The backend reconnects with backoff.
  - Commands are rejected while disconnected.
- **HeishaMon offline:** stale values are shown greyed out with their age, and commands are rejected.
- **Unparseable payload:** stored as text with `valid = 0` (no coverage, §5.2) and shown as raw; never crash the ingest loop.
- **Flush failure (disk full, etc.):**
  - Keep the buffer.
  - Retry at the next interval.
  - Surface the error in the status bar and on the System page.
  - While the failure persists, the §5.1 overflow policy and protected-record budget apply, and the
    error stays visible until a flush succeeds.
- **WebSocket drop:** the frontend reconnects; the `hello` message (§4.4) resynchronizes completely.

## 10. Testing

- **Backend (pytest):**
  - catalog: exact match with the Appendix A.2 inventory; every read-back topic exists; every enum
    has EN+NL labels; every `models` entry is well-formed;
  - payload parsing, sentinel detection, ingest limits;
  - change-dedup;
  - coverage, outages, rollups, materialization and retention: the §5.4 timelines T1–T9 as exact
    numeric fixtures;
  - buffer flush, the DB+buffer replace-merge on read, overflow and the protected-record budget;
  - flush on SIGTERM;
  - command validation, every gate in §6 order, no-op, supersede, confirm/retry/fail with full
    re-gating (fake clock);
  - the publish allowlist and the retained-exception path;
  - liveness rule list (§4.1);
  - curve math: crosswise mapping, ordering invariant, slope/level refusal;
  - overlay minute eligibility and window rules on numeric rollup fixtures;
  - profile derivation and mode-dependent command ranges, as a matrix over the profile presets
    below.
- **Profile presets** (used by the backend matrix, the simulator and Playwright):
  - operating modes: heat-only single zone, cool-only, DHW-only, Heat+DHW, Cool+DHW, auto (heat)
    and auto (cool, reporting 7/8);
  - zones and sensors:
    - two zones with the shared modes *heating curve / cooling direct*, inherited identically by
      both zones;
    - two zones with different sensors (Z1 water, Z2 internal thermostat);
    - a thermostat sensor and a thermistor sensor;
  - equipment: no DHW tank, with/without `extra/`, PCB emulation on, no integrations (no
    1-wire/S0/OpenTherm), all integrations;
  - edge cases: `fw-3.2.3` (oldest-version topics and stats, Appendix A); an unknown-inputs preset
    (`-1` values, missing stats version); a **profile-change** preset that switches the operating
    mode and the curve/direct mode mid-stream.
- **Integration:**
  - **Replay:** a fixture built from a captured real MQTT session, with the `ip` topic and any
    identifying data stripped, run against an embedded test broker (`amqtt`).
    - **Deferred (decision-006):** the real capture cannot be made from the build environment. The
      repo ships `tools/capture.py`, a read-only subscriber that never publishes, takes connection
      settings from the environment, and writes a sanitized fixture: no `ip` topic, `stats`
      reduced to `version`, and 1-wire addresses replaced by stable pseudonyms.
    - The owner runs it once on their own network.
    - Until `backend/tests/fixtures/replay_real.json` exists, the real-replay test is **skipped
      with an explicit reason**. The privacy test (A12) runs on whatever fixtures exist.
    - A synthetic replay generated from the simulator, labelled as synthetic, runs meanwhile.
  - A **simulator** (`tools/simulator.py`) publishes a realistic HeishaMon topic stream for a
    profile preset and echoes commands to read topics.
    - Per-command fault modes make every §6 outcome reproducible: `echo` (confirm), `drop`
      (never), `drop_first` (confirm on retry), `delay:<s>`, `partial` (SetCurves: only some keys),
      `listen_only` (drop everything).
- **Frontend:**
  - Vitest for curve geometry, handle constraints, slope/level transforms and i18n completeness.
  - Playwright against the simulator for several presets: a smoke test, keyboard operation and the
    viewport checks in A10.

**Acceptance matrix (measurable pass conditions, traceable to the suites above):**

| # | Outcome | Measurable pass condition |
|---|---|---|
| A1 | See everything | every catalogued topic received appears on the All-topics screen; uncatalogued topics appear as raw; sections without traffic stay hidden |
| A2 | Set everything | all 64 Appendix A.2 commands plus the S0 sync and the OpenTherm `opentherm/read/*` inputs are submittable via API and UI; every rejection code in §6 has a test that produces it |
| A3 | Command lifecycle | under simulator fault modes: `echo` → `confirmed`; `drop_first` → `retried` then `confirmed`; `drop` → `failed` at exactly 20 s; `partial` → `failed` with per-key statuses; trigger → `sent`, never retried; supersede → old `superseded`, no stale retry published; device going offline before the retry → `failed` with `device_offline`, nothing published; no-op → `noop`, nothing published; `listen_only` → banner after 3 failures, statuses stay `failed`; a retained/stale cached match never confirms |
| A4 | Log everything | samples, commands and events land in SQLite; history merges DB + RAM buffer under the replace rule; CSV export equals the history points for the same query |
| A5 | Storage correctness | the T1–T9 timelines of §5.4 reproduce every listed number exactly. The overflow budget test runs a storage failure past every cap, with repeated offline/online transitions, repeated topic-scoped drop/re-establish and ignore/un-ignore cycles, and in-flight commands completing at the reserve boundary. It shows: bounded memory (record count never above `AUDIT_BUFFER_MAX`); topic-scoped `dropped` outages before saturation; exactly one saturation outage afterwards, with no further outage records; refused new commands (`storage_unavailable`); terminal updates still recorded; the aggregated events; and zero coverage for every topic during saturation. After raw expiry, history at `1m`/`1h` returns the same `covered_seconds` and `breaks` as before expiry, and a short (≤ 6 h) query on expired history is served at `1m`, never `raw` |
| A6 | Heating curve | crosswise mapping; ordering invariant and limits (equal targets allowed, equal outside refused; target ordering skipped for a coupled zone/mode); slope/level refusal at bounds; per-key `SetCurves` confirmation; overlay minute/window rules on numeric fixtures, including the startup and DHW-settling 10-minute exclusions and the 12-of-15 rule |
| A7 | Installation-agnostic | every profile preset above passes; unknown/stale inputs show features and gate commands with `profile_unknown`; modes 7/8 are informational only; the `fw-3.2.3` preset disables exactly the commands with `min_firmware` > 3.2.3, as does a missing version |
| A8 | Liveness | per the §4.1 rule list: `LWT=Online` heartbeats alone keep the device online; retained snapshots, `commands/#` echoes, an `s0/WatthourTotal` echo and `opentherm/read/#` never make an offline device online; a live `Offline` wins; the timeout is backdated to the last qualifying message; broker reconnect alone leaves the device `unknown` until a qualifying message |
| A9 | Origin security | per §13: disallowed `Origin` → 403 on every mutation and at WebSocket handshake; `Origin: null` → 403; bad `Host` with `PUBLIC_ORIGINS` set → 403; form-encoded/`text/plain` mutations → 415; a legitimate HTTPS-proxy setup (`PUBLIC_ORIGINS=https://…`, backend reached over HTTP with the proxied `Host`) passes REST and WebSocket |
| A10 | i18n and responsive | every UI string and catalog label exists in EN and NL (test-enforced); at 390 px and 1280 px no page scrolls horizontally (`scrollWidth ≤ clientWidth`) and every control is reachable and operable; every Apply flow (settings, curve, thresholds) can be completed by keyboard alone |
| A11 | Deployment | the process flushes on SIGTERM within 60 s and the data is present after a restart on the same `DATA_DIR` (automated); the Docker image builds and `docker stop` / start on the `/data` volume preserves data (release check); the README carries the loud no-auth warning and the reverse-proxy recipe of §13 |
| A12 | Privacy | every replay fixture (synthetic now; real once captured) contains no `ip` topic and no installation-specific data (test-enforced); `tools/capture.py` sanitizes per §10 and never publishes (test with a fake client) |

## 11. Repo layout (indicative)

```
backend/heishamon_dashboard/   config, catalog, mqtt, state, store, commands, derived, api
backend/heishamon_dashboard/catalog.json
backend/tests/
frontend/                      Svelte + Vite app
tools/simulator.py, tools/presets.py, tools/capture.py
Dockerfile, docker-compose.example.yml, .env.example, README.md
```

## 12. Configuration reference (exact)

All configuration comes from environment variables; the repository ships only `.env.example`.
A missing required variable, or a value outside its accepted range, fails fast at startup with a
message naming the variable.

| Variable | Type / accepted values | Default | Required |
|---|---|---|---|
| `MQTT_HOST` | hostname | — | yes |
| `MQTT_PORT` | integer 1–65535 | `1883` | no |
| `MQTT_USER` | string | — | no |
| `MQTT_PASSWORD` | string | — | no |
| `MQTT_TLS` | boolean: `1`, `true`, `yes` (case-insensitive) → on; anything else off | off | no |
| `MQTT_BASE_TOPIC` | 1–128 bytes UTF-8; `/`-separated non-empty segments; no leading/trailing `/`; must not contain `+`, `#` or NUL; must not start with `$` | `panasonic_heat_pump` | no |
| `DATA_DIR` | writable directory path | `/data` | no |
| `FLUSH_INTERVAL_SECONDS` | integer 10–86400 | `900` | no |
| `BUFFER_MAX_ENTRIES` | integer ≥ 1000 | `200000` | no |
| `BUFFER_MAX_BYTES` | integer ≥ 16777216 (16 MiB) | `268435456` (256 MiB) | no |
| `AUDIT_BUFFER_MAX` | integer 100–100000 | `10000` | no |
| `RAW_RETENTION_DAYS` | integer ≥ 1, or empty = keep forever | empty | no |
| `HTTP_PORT` | integer 1–65535 | `8000` | no |
| `TZ` | IANA timezone name (e.g. `Europe/Amsterdam`); invalid → startup error | `UTC` | no |
| `PUBLIC_ORIGINS` | comma-separated origins (`scheme://host[:port]`) at which users reach the dashboard (§13); empty = derive from `Host` | empty | no |
| `ALLOWED_ORIGINS` | comma-separated *additional* origins allowed to call the API cross-origin (embedding) | empty | no |

`STATIC_DIR` (optional, deployment plumbing, not a user-facing setting): directory of the built SPA.
Unset, the process serves `<repo>/frontend/dist`; the container image sets `/app/static`. If the
directory is missing, the API still runs and `/` returns a short "frontend has not been built" page
(`404`).

Preference defaults (prefs table, changeable in the UI): write lock **off**, optional-PCB section
**off**, topic visibility **no explicit entries** (all visible), feature overrides **none**, tile set
and chart presets **profile defaults**. Language is not a pref: it is stored in the browser
(`localStorage`), defaulting to the browser language with an EN fallback.

## 13. Browser-origin and CSRF policy

The dashboard itself has **no authentication** (§2). It is designed to sit behind a reverse proxy
that does auth, on a trusted LAN or VPN. Within that accepted scope, the backend still refuses
browser-driven writes from foreign origins, and it refuses DNS-rebinding hosts when configured.

- **Trusted origins:**
  - the set `PUBLIC_ORIGINS ∪ ALLOWED_ORIGINS` when `PUBLIC_ORIGINS` is set;
  - otherwise the **derived same origin**, plus `ALLOWED_ORIGINS`. The derived same origin is any
    origin whose `host[:port]` equals the request's `Host` header. The scheme is ignored, so that a
    TLS-terminating proxy that forwards `Host` works.
  - `X-Forwarded-*` headers are never trusted.
- **Host check:** when `PUBLIC_ORIGINS` is set, a request whose `Host` matches none of its
  `host[:port]` values gets `403 bad_host`. This is the DNS-rebinding protection. The README
  recommends always setting `PUBLIC_ORIGINS`, and startup logs a warning when it is empty.
- **Mutations** (`POST /api/command`, `PUT /api/prefs`, `POST /api/system/flush`), enforced
  server-side before any processing:
  - `Origin` present and trusted → allowed.
  - `Origin` present and not trusted, or `Origin: null` → `403 bad_origin`.
  - `Origin` absent → allowed. Browsers always send `Origin` on these methods, so an absent header
    means a non-browser client on the trusted network, consistent with the no-auth scope.
  - The body must be `application/json`; anything else → `415`. Classic HTML-form CSRF cannot
    produce such a request cross-origin without a preflight.
- **CORS:** `Access-Control-Allow-Origin` is sent only for `ALLOWED_ORIGINS` (exact echo, no `*`, no
  credentials). Preflights from other origins get no CORS headers.
- **WebSocket:** the same `Origin` rules apply at the handshake (absent → allowed; null or
  untrusted → rejected with 403), and the same Host check applies.
- **Reverse-proxy recipe (README, acceptance A9/A11):**
  - The proxy terminates TLS and authenticates.
  - It forwards `Host` unchanged and passes WebSocket upgrades on `/api/ws`.
  - The operator sets `PUBLIC_ORIGINS=https://<public host>`.
  - The README states loudly: never expose the dashboard without an authenticating proxy, and only
    add `ALLOWED_ORIGINS` when embedding is intended.

## Appendix A. Firmware facts, catalog schema and command inventory

Source: firmware spike `.paseo-autopilot/20261011T132000Z-heishamon-dashboard/reports/spike/spike-001--att-004.md`.
It inspected HeishaMon tags v3.2.3 … v4.2.3, and commit `6c35bd9`, which has the same firmware
source as v4.2.3. Facts are restated in our own words; nothing upstream is copied. The local run
directory is not committed; the facts that matter are restated here.

### A.1 Version string, stats, LWT, defaults

- **`stats.version`:** `stats` (retained JSON) exists at every version ≥ 3.2.3 and carries a string
  field `version`. Observed formats:
  - three-component `3.2.3`, and betas such as `3.2.4-beta-2`;
  - **two-component** `3.5`, `3.6`, `3.7`, `3.8`, `3.9`, `4.0`;
  - the irregular `3.61` and `3.62` (meaning 3.6.1 and 3.6.2);
  - from v4.1 on, the release workflow writes the tag name, e.g. `v4.1.2` or `v4.2.3`;
  - local and CI builds report `Local build`, `Alpha-<sha>` or `Nightly-<sha>`.
- **Parsing rule (normative):**
  1. strip one leading `v`;
  2. take the leading `major.minor[.patch]` digits;
  3. a missing patch is 0;
  4. a **two-component** string whose minor has exactly two digits `d1d2` with `d1 ≥ 1` is read as
     `major.d1.d2` (so `3.61` → 3.6.1);
  5. any suffix is ignored for comparison;
  6. anything else (including `Local build`, `Alpha-…`, `Nightly-…`) is **unknown** → assumed 3.2.3.
- **Listen-only:** no MQTT topic or stats field reports it at any inspected version. A transient
  `log` line may appear when MQTT logging is on, but it is not a state contract and is not used. The
  §6 heuristic is the only mechanism.
- **LWT:**
  - Every inspected version registers a **retained** `Offline` will on `<base>/LWT`.
  - It publishes a **non-retained** `Online` on connect and then once per main-loop cycle of
    `waitTime` seconds (default 5, user-configurable).
  - The §4.1 liveness timeout is therefore `max(30 s, 3 × median interval of the last 10 LWT=Online
    messages)`. The §5.4 timelines use the default 5 s.
- **Defaults** at every inspected version: base topic `panasonic_heat_pump`, full re-publish
  interval 300 s.
- **Topics per version:**
  - `main/` has TOP0–114 at 3.2.3. Later additions:
    - TOP115–118 (from 3.5);
    - TOP119–138 (from 3.9);
    - TOP139–142 (from 4.0);
    - TOP143 (from 4.1.2).
  - `extra/` XTOP0–5 and `optional/` OPT0–6 are unchanged throughout.
  - Topic names and indices never change, so a topic needs no version gate to be shown.
- **`Heat_Pump_Model` (TOP92):**
  - From 3.9 on, it is a string of ten space-separated two-digit hex bytes.
  - Before 3.9, it is a numeric model index as text.
  - The profile resolves `model`/`series` only for the hex format (A.3); a numeric payload gives
    `series: null`.
- **OpenTherm namespace:** from 3.5 on, inputs are `<base>/opentherm/read/<name>` (subscribed by
  HeishaMon, never published by it) and outputs are `<base>/opentherm/write/<name>`. At 3.2.3 a
  single `<base>/opentherm/<name>` namespace serves both directions.
  - The dashboard's OpenTherm inputs therefore have `min_firmware: "3.5"`.
  - The legacy single namespace counts for `has_opentherm`, but never as liveness (rule 6).
- **S0 total sync:**
  - HeishaMon publishes `s0/WatthourTotal/{1,2}` retained.
  - On each MQTT (re)connect, with S0 enabled, it subscribes once to that topic to restore the
    counter (decimal parse), then unsubscribes.
  - A retained dashboard publish there therefore takes effect at HeishaMon's next (re)connect.
    The UI says so.

### A.2 Command inventory (normative for `catalog.json`)

64 commands under `<base>/commands/`: 50 standard (including `SetCurves`) and 14 optional-PCB (PCB =
yes). The firmware dispatches PCB commands only while PCB emulation is enabled.

Classes are setting (S), trigger (T) and unverifiable (U). The retained exceptions are not under
`commands/` (A.1 and §6).

`min` is the first release that dispatches the command; `3.2.3` means present at the floor. The
read-back is the `main/` topic (TOP index) that reflects the command; "—" means none (class U).

**Comparison rules:**

- **equal** (the default): the read-back value equals the payload;
- **holiday**: payload 1 confirms on a read value of 1 or 2, and payload 0 confirms on 0;
- **curve-leaf**: per `SetCurves` key, the matching curve topic equals the key value.

**Payload types:**

- `int`: decimal integer;
- `bool`: `0`/`1`;
- `dec1`: decimal with up to one fractional digit;
- `json`: `SetCurves` partial JSON;
- `int2`: exactly two digits;
- `int12`: one or two digits.

| Command | PCB | Class | Type | Dashboard range / set | Read-back (TOP) | min |
|---|---|---|---|---|---|---|
| SetHeatpump | no | S (risky when 0) | bool | 0, 1 | Heatpump_State (0) | 3.2.3 |
| SetPump | no | U | bool | 0, 1 | — | 3.2.3 |
| SetMaxPumpDuty | no | S | int | per range rule | Max_Pump_Duty (95) | 3.2.3 |
| SetQuietMode | no | S | int | 0–3 | Quiet_Mode_Level (18) | 3.2.3 |
| SetZ1HeatRequestTemperature | no | S | int | curve: −5..5; direct (water sensor): 20..65; direct (room sensor): 10..30 — in direct + room sensor (coupled, §8) the active setpoint is the curve's cold-end target and this read-back is observed to stay 0; the UI points to the curve leaf | Z1_Heat_Request_Temp (27) | 3.2.3 |
| SetZ1CoolRequestTemperature | no | S | int | curve: −5..5; direct (water): 5..20; direct (room): 18..30 — coupled note as Z1 heat | Z1_Cool_Request_Temp (28) | 3.2.3 |
| SetZ2HeatRequestTemperature | no | S | int | as Z1 heat | Z2_Heat_Request_Temp (34) | 3.2.3 |
| SetZ2CoolRequestTemperature | no | S | int | as Z1 cool | Z2_Cool_Request_Temp (35) | 3.2.3 |
| SetForceDHW | no | S | bool | 0, 1 | Force_DHW_State (2) | 3.2.3 |
| SetForceDefrost | no | T | bool | 1 | — (effect: Defrosting_State 26) | 3.2.3 |
| SetForceSterilization | no | T | bool | 1 | — (effect: Sterilization_State 69) | 3.2.3 |
| SetSterilizationTemp | no | S | int2 | 55–75 (firmware also enforces) | Sterilization_Temp (70) | 4.2.3 |
| SetSterilizationMaxTime | no | S | int12 | 5–60, step 5 (firmware also enforces) | Sterilization_Max_Time (71) | 4.2.3 |
| SetForceHeater | no | S | bool | 0, 1 | Force_Heater_State (68) | 4.2.0 |
| SetHolidayMode | no | S (holiday rule) | bool | 0, 1 | Holiday_Mode_State (19) | 3.2.3 |
| SetPowerfulMode | no | S | int | 0–3 | Powerful_Mode_Time (17) | 3.2.3 |
| SetOperationMode | no | S | int | 0–6 | Operating_Mode_State (4) | 3.2.3 |
| SetDHWTemp | no | S | int | 40–75 | DHW_Target_Temp (9) | 3.2.3 |
| SetCurves | no | S (curve-leaf) | json | §8 limits and ordering (merged state); target ordering skipped for a coupled zone/mode (§8) | TOP29–32, 72–75, 82–89 (16 leaves) | 3.2.3 |
| SetZones | no | S | int | 0–2 | Zones_State (94) | 3.2.3 |
| SetFloorHeatDelta | no | S | int | per range rule | Heat_Delta (23) | 3.2.3 |
| SetFloorCoolDelta | no | S | int | per range rule | Cool_Delta (24) | 3.2.3 |
| SetDHWHeatDelta | no | S | int | per range rule | DHW_Heat_Delta (22) | 3.2.3 |
| SetReset | no | T (risky) | bool | 1 | — | 3.2.3 |
| SetHeaterDelayTime | no | S | int | per range rule | Heater_Delay_Time (96) | 3.2.3 |
| SetHeaterStartDelta | no | S | int | per range rule | Heater_Start_Delta (97) | 3.2.3 |
| SetHeaterStopDelta | no | S | int | per range rule | Heater_Stop_Delta (98) | 3.2.3 |
| SetMainSchedule | no | S | bool | 0, 1 | Main_Schedule_State (13) | 3.2.3 |
| SetAltExternalSensor | no | S | bool | 0, 1 | Alt_External_Sensor (108) | 3.2.3 |
| SetExternalPadHeater | no | S | int | 0–2 | External_Pad_Heater (114) | 3.2.3 |
| SetBufferDelta | no | S | int | per range rule | Buffer_Tank_Delta (113) | 3.2.3 |
| SetBuffer | no | S | bool | 0, 1 | Buffer_Installed (99) | 3.2.3 |
| SetHeatingOffOutdoorTemp | no | S | int | 5–35 | Heating_Off_Outdoor_Temp (77) | 3.2.3 |
| SetExternalControl | no | S | bool | 0, 1 | External_Control (119) | 3.9 |
| SetExternalError | no | S | bool | 0, 1 | External_Error_Signal (121) | 3.9 |
| SetExternalCompressorControl | no | S | bool | 0, 1 | External_Compressor_Control (122) | 3.9 |
| SetExternalHeatCoolControl | no | S | bool | 0, 1 | External_Heat_Cool_Control (120) | 3.9 |
| SetBivalentControl | no | S | bool | 0, 1 | Bivalent_Control (129) | 3.9 |
| SetBivalentMode | no | S | int | 0–2 | Bivalent_Mode (130) | 3.9 |
| SetBivalentStartTemp | no | S | int | per range rule | Bivalent_Start_Temp (131) | 3.9 |
| SetBivalentAPStartTemp | no | S | int | per range rule | Bivalent_Advanced_Start_Temp (134) | 3.9 |
| SetBivalentAPStopTemp | no | S | int | per range rule | Bivalent_Advanced_Stop_Temp (135) | 3.9 |
| SetHeatingControl | no | S | bool | 0, 1 | Heating_Control (139) | 4.0 |
| SetSmartDHW | no | S | bool | 0, 1 | Smart_DHW (140) | 4.0 |
| SetQuietModePriority | no | S | bool | 0, 1 | Quiet_Mode_Priority (141) | 4.0 |
| SetPumpFlowrateMode | no | S | bool | 0, 1 | Pump_Flowrate_Mode (106) | 4.0 |
| SetDHWSensorSelection | no | S | bool | 0, 1 | DHW_Sensor_Selection (143) | 4.1.2 |
| SetDHWHeaterState | no | S | bool | 0, 1 | DHW_Heater_State (58) | 4.1.2 |
| SetRoomHeaterState | no | S | bool | 0, 1 | Room_Heater_State (59) | 4.1.2 |
| SetHeaterOnOutdoorTemp | no | S | int | −15–20 | Heater_On_Outdoor_Temp (78) | 4.1.2 |
| SetHeatCoolMode | yes | U | bool | 0, 1 | — | 3.2.3 |
| SetCompressorState | yes | U | bool | 0, 1 | — | 3.2.3 |
| SetSmartGridMode | yes | U | int | 0–3 | — | 3.2.3 |
| SetExternalThermostat1State | yes | U | int | 0–3 | — | 3.2.3 |
| SetExternalThermostat2State | yes | U | int | 0–3 | — | 3.2.3 |
| SetDemandControl | yes | U | int | per range rule | — | 3.2.3 |
| SetPoolTemp | yes | U | dec1 | −30.0–90.0, step 0.5 | — (approximate: Pool_Temp 48) | 3.2.3 |
| SetBufferTemp | yes | U | dec1 | −30.0–90.0, step 0.5 | — (approximate: Buffer_Temp 46) | 3.2.3 |
| SetZ1RoomTemp | yes | U | dec1 | −30.0–90.0, step 0.5 | — (approximate: Z1_Temp 56) | 3.2.3 |
| SetZ1WaterTemp | yes | U | dec1 | −30.0–90.0, step 0.5 | — (approximate: Z1_Water_Temp 36) | 3.2.3 |
| SetZ2RoomTemp | yes | U | dec1 | −30.0–90.0, step 0.5 | — (approximate: Z2_Temp 57) | 3.2.3 |
| SetZ2WaterTemp | yes | U | dec1 | −30.0–90.0, step 0.5 | — (approximate: Z2_Water_Temp 37) | 3.2.3 |
| SetSolarTemp | yes | U | dec1 | −30.0–90.0, step 0.5 | — (approximate: Solar_Temp 47) | 3.2.3 |
| SetOptPCBByte9 | yes | U | int | 0–255 | — | 3.2.3 |

**Non-`commands/` inputs (§6).** These are the exhaustive set of paths that HeishaMon (v3.5 and
later) reads under `opentherm/read/`, plus the S0 sync. The list comes from the same firmware source
as the spike, read by the orchestrator in the spike's clone. Names are identifiers; nothing is
copied.

| Path | Class | Payload | Range | min |
|---|---|---|---|---|
| `s0/WatthourTotal/1`, `s0/WatthourTotal/2` | retained exception | dec3 | ≥ 0 | 3.2.3 |
| `opentherm/read/dhwSetUppBound`, `dhwSetLowBound`, `chSetUppBound`, `chSetLowBound` | retained exception | int | per range rule | 3.5 |
| `opentherm/read/dhwSetpoint`, `maxTSet` | input (non-retained) | dec1 | per range rule | 3.5 |
| `opentherm/read/outsideTemp`, `inletTemp`, `outletTemp`, `dhwTemp`, `roomSetOverride` | input (non-retained) | dec1 | per range rule | 3.5 |
| `opentherm/read/chPressure` (bar), `relativeModulation` (%) | input (non-retained) | dec1 | per range rule | 3.5 |
| `opentherm/read/flameState`, `chState`, `dhwState`, `coolingState` | input (non-retained) | bool | 0, 1 | 3.5 |

**Range rule** (for every "per range rule" cell, and binding on every `catalog.json` range):

- Each entry carries `range_source`:
  - `panasonic_manual`: the setting range from the Panasonic installer/service documentation,
    restated;
  - `heishamon_fact`: an upstream documentation fact, restated in our own words;
  - `encoding_domain`: no documented range exists. The bound is the firmware encoder's byte
    domain, and the command is risky (`confirm: true`).
- A catalog test fails on an entry without `range_source`, and on any range that contradicts a
  fixed cell in the table above.

**Other inventory facts:**

- Holiday and PowerfulMode encodings differ by version, but the dashboard writes only the
  documented payload values.
- The firmware has no PCB read-back. OPT0–6 describe *outputs* of the heat pump, not the inputs
  these commands set.
- The PCB `dec1` setters accept decimals, and the firmware applies an NTC conversion. "Approximate"
  read-backs are shown for information only and never confirm.

### A.3 `catalog.json` schema

```json
{
  "schema": 1,
  "topics": [{"key": "main/Outside_Temp", "id": "TOP14", "kind": "number|enum|text", "unit": "°C|W|…|null",
              "decimals": 0, "enum": {"0": {"en": "…", "nl": "…"}} , "sentinels": [-128],
              "category": "temperatures", "label": {"en": "…", "nl": "…"}, "min_firmware": "3.2.3",
              "feature": "zone2|dhw|cooling|…|null"}],
  "commands": [{"name": "SetDHWTemp", "pcb": false, "class": "setting|trigger|unverifiable",
                "risky": false, "type": "int|bool|dec1|dec3|json|int2|int12",
                "range": {"min": 40, "max": 75, "step": 1}, "allowed": null,
                "conditional_ranges": [{"when": {"profile.heating_control": "curve"}, "min": -5, "max": 5, "step": 1}],
                "range_source": "panasonic_manual|heishamon_fact|encoding_domain",
                "readback": ["main/DHW_Target_Temp"], "compare": "equal|holiday|curve_leaf",
                "applicability": {"requires": ["profile.dhw_installed"]}, "safe_under_unknown": false,
                "min_firmware": "3.2.3", "category": "dhw", "label": {"en": "…", "nl": "…"}}],
  "inputs": [{"path": "s0/WatthourTotal/1", "class": "retained_exception|input", "retain": true,
              "type": "dec3|dec1|int|bool", "range": {"min": 0}, "range_source": "…", "min_firmware": "3.2.3",
              "label": {"en": "…", "nl": "…"}}],
  "models": [{"hex": "E2 CF 0B …", "name": "WH-…", "series": "J|K|L|other"}]
}
```

**`models` table:** series is the generation letter in the Panasonic model name. Entries are
factual identifiers (byte pattern and model code) and are added as they become known. An unknown
hex string, or a numeric pre-3.9 payload, gives `series: null`.

### A.4 Enum decodings (as published; labels are ours)

| Topic | Values |
|---|---|
| `Operating_Mode_State` (TOP4) | 0 heat · 1 cool · 2 auto (heating) · 3 DHW only · 4 heat+DHW · 5 cool+DHW · 6 auto (heating)+DHW · 7 auto (cooling) · 8 auto (cooling)+DHW · −1 unknown |
| derived `heating_in_use` / `cooling_in_use` / `dhw_in_use` | heating: {0,2,4,6}; cooling: {1,5,7,8}; DHW: {3,4,5,6,8} |
| overlay mode sets (§8) | heat tabs {0,2,4,6}; cool tabs {1,5,7,8} |
| `Heating_Mode` (TOP76), `Cooling_Mode` (TOP81) | 0 curve · 1 direct · other (−1, 2) → unknown |
| `Zones_State` (TOP94) | 0 Z1 · 1 Z2 · 2 both · −1 unknown |
| `Z1/Z2_Sensor_Settings` (TOP111/112) | 0 water · 1 external thermostat · 2 internal thermostat · 3 thermistor · other → unknown |
| `ThreeWay_Valve_State` (TOP20) | 0 room/heating circuit · 1 DHW · other → unknown |
| `Defrosting_State` (TOP26) | 0 not defrosting · 1 defrosting · other → unknown |
| `Buffer_Installed` (TOP99), `DHW_Installed` (TOP100), `Optional_PCB` (TOP110), `Bivalent_Control` (TOP129, from 3.9) | 0 no/disabled · 1 yes/enabled · other → unknown (never truthy) |
| `Solar_Mode` (TOP101) | 0 off · 1 buffer · 2 DHW · other → unknown |
| `Liquid_Type` (TOP107) | 0 water · 1 glycol · other → unknown |

On firmware before 3.9, `Bivalent_Control` is never received, so `profile.bivalent` stays unknown and
bivalent features are shown, per the unknown-input rule (§4.3).

A value outside a topic's set is shown raw and makes the dependent profile field unknown (§4.3).
