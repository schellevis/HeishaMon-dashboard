# HeishaMon dashboard

Self-hosted web dashboard for a Panasonic Aquarea heat pump connected through [HeishaMon](https://github.com/heishamon/HeishaMon). It talks to HeishaMon **only over MQTT**: it shows the live state, applies settings (including the heating curve), and keeps a history in SQLite.

One heat pump (one MQTT base topic) per instance. Run another container for another heat pump.

> ## No authentication
>
> **This program does not authenticate anyone.** There are no users, passwords or sessions.
>
> Anyone who can open the dashboard can read every value and send every setting to the heat pump, including switching it off.
>
> **Never expose it without an authenticating reverse proxy.** That means not on the public internet, not on a guest network, and not on an untrusted LAN. Binding a host port is not access control.
>
> The proxy must terminate TLS and require authentication before a request reaches this process. The recipe is below. `ALLOWED_ORIGINS` is only for deliberately embedding the API on another site — leave it empty otherwise.

## Requirements

- HeishaMon firmware **3.2.3 or newer** (the topic names this dashboard understands). Older firmware still shows up as raw, uncatalogued values.
- An MQTT broker that HeishaMon already uses.
- Docker, for the container below. A checkout with the provided `.venv` can run the same process without Docker.

The application reads **environment variables only**. It does not open a `.env` file. Compose `environment` / `env_file`, or your shell, must supply them. Copy [`.env.example`](.env.example) to `.env` for local values. `.env` is gitignored. Do not commit it.

## Run with Docker

From this directory, after editing the placeholders in `docker-compose.example.yml`:

```sh
docker compose -f docker-compose.example.yml up -d --build
```

The example publishes **127.0.0.1:8000** only, so the process is reachable on that host and not on other interfaces. Put the reverse proxy in front of it. The sample `PUBLIC_ORIGINS` is `https://heatpump.example.invalid`, so open the site at that origin through the proxy. A direct request to `http://127.0.0.1:8000` is rejected (`403 bad_host`) because its `Host` header does not match.

The image listens on all container interfaces (`0.0.0.0`) on `HTTP_PORT` (default 8000). The data volume is `/data` (SQLite). The container runs as uid **10001** (`dashboard`). `stop_grace_period` is **60s** so a `docker stop` can finish the shutdown flush (the process allows 45 s for that shutdown).

History is buffered in memory and written in one transaction every `FLUSH_INTERVAL_SECONDS` (default 900, which is 15 minutes), when the buffer reaches its size cap, and on SIGTERM/SIGINT. A crash or power loss can drop up to one interval of samples. Preferences are written immediately.

### Release check (operator)

Image build and the volume check are not run in development (`docker` is not part of the test loop). After you build:

```sh
docker compose -f docker-compose.example.yml up -d --build
# use the dashboard so it has written under /data, then:
docker compose -f docker-compose.example.yml stop
docker compose -f docker-compose.example.yml start
```

Confirm the history and preferences from before `stop` are still there. `stop` must return within 60 seconds.

## Reverse proxy

Spec §13. The proxy terminates TLS and authenticates. This process is reached over plain HTTP behind it. It **does not trust** `X-Forwarded-*` headers. When `PUBLIC_ORIGINS` is set, the `Host` header must match one of those origins (`host` and optional port); otherwise the request is `403 bad_host`. An empty `PUBLIC_ORIGINS` skips the `Host` match and logs a warning at startup — set it. Without it, writes (`POST`/`PUT`) and WebSocket connections are accepted only when the `Host` is `localhost` or an IP literal (`127.0.0.1:8000`, `[::1]:8000`, `192.168.1.10:8000`). A DNS name gets `403 bad_host` until you set `PUBLIC_ORIGINS`; reads are unaffected. Request bodies above 64 KiB are refused with `413`, and the CSV export prefixes text cells that start with `=`, `+`, `-`, `@`, TAB or CR with `'` so spreadsheets do not run them as formulas.

Set:

```text
PUBLIC_ORIGINS=https://heatpump.example.invalid
```

to the exact origin users type, including `https` and a non-default port if there is one. Several origins are comma-separated. Add `ALLOWED_ORIGINS` only when another site should call the API from a browser.

The proxy must:

- forward the `Host` header **unchanged** (the public host, not the container name);
- pass the WebSocket upgrade on `/api/ws`.

Browser writes (`POST /api/command`, `PUT /api/prefs`, `POST /api/system/flush`) must come from a trusted `Origin` and use `Content-Type: application/json`. `Origin: null` is rejected.

### Caddy

Caddy forwards `Host` and upgrades WebSockets by default. Put authentication in this site block (basic auth, or your identity provider). `127.0.0.1` is the compose port.

```caddy
heatpump.example.invalid {
	# Require authentication here, before reverse_proxy.
	reverse_proxy 127.0.0.1:8000
}
```

### nginx

`map` belongs in the `http` block. Authentication (for example `auth_request` or `auth_basic`) belongs in this server **before** the proxy.

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl;
    server_name heatpump.example.invalid;
    # ssl_certificate and authentication go here.

    location /api/ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }
}
```

`HTTP_PORT` and the host port in compose must match the proxy's upstream port.

## Configuration

Spec §12. A missing required variable, or a value outside its range, stops startup with exit code 2 and a message that names the variable.

| Variable | Accepted values | Default | Required |
|---|---|---|---|
| `MQTT_HOST` | hostname | — | yes |
| `MQTT_PORT` | integer 1–65535 | `1883` | no |
| `MQTT_USER` | string | empty | no |
| `MQTT_PASSWORD` | string | empty | no |
| `MQTT_TLS` | `1`, `true`, `yes` (any case) turn TLS on; anything else leaves it off | off | no |
| `MQTT_CA_FILE` | path to a PEM CA bundle used to verify the broker when `MQTT_TLS` is on; the file must exist | empty (system CAs) | no |
| `MQTT_BASE_TOPIC` | 1–128 bytes UTF-8; `/`-separated non-empty segments; no leading or trailing `/`; no `+`, `#` or NUL; must not start with `$` | `panasonic_heat_pump` | no |
| `DATA_DIR` | writable directory | `/data` | no |
| `FLUSH_INTERVAL_SECONDS` | integer 10–86400 | `900` | no |
| `BUFFER_MAX_ENTRIES` | integer ≥ 1000 | `200000` | no |
| `BUFFER_MAX_BYTES` | integer ≥ 16777216 (16 MiB) | `268435456` (256 MiB) | no |
| `AUDIT_BUFFER_MAX` | integer 100–100000 | `10000` | no |
| `COMMAND_RATE_MAX` | integer ≥ 1; publish attempts per command name per window (retries count) | `6` | no |
| `COMMAND_RATE_WINDOW_S` | integer ≥ 1; sliding window in seconds | `3600` | no |
| `RAW_RETENTION_DAYS` | integer ≥ 1, or empty to keep raw samples | empty | no |
| `HTTP_PORT` | integer 1–65535 | `8000` | no |
| `TZ` | IANA name, for example `Europe/Amsterdam`. An unknown name is a startup error | `UTC` | no |
| `PUBLIC_ORIGINS` | comma-separated origins (`scheme://host[:port]`) where users open the dashboard. Empty = derive a same-origin from the `Host` header | empty | no |
| `ALLOWED_ORIGINS` | comma-separated **extra** origins allowed to call the API from another site | empty | no |

`STATIC_DIR` is not in that table. It is the directory of the built SPA. Unset, a checkout uses `<repo>/frontend/dist`. The container image sets it to `/app/static`. If that directory is missing, `/` responds with a short “frontend has not been built” page.

UI preferences (write lock, optional-PCB section, topic visibility, tiles, chart presets) are stored in the database, not in these variables. Write lock defaults to off. Language is stored in the browser (`localStorage`), from the browser language, falling back to English.

## Commands, dropped writes, EEPROM

Settings are sent only when you press **Apply**. Dragging a slider or a curve handle does not publish.

HeishaMon sometimes **drops a command**. The dashboard checks the read-back topic. A setting that does not match is retried **once**, about **10 seconds** after the first publish, and marked failed about **20 seconds** after the first publish if it still does not match. Triggers are not retried. A value that already matches a recent live read-back is not published again.

Those writes are stored in the heat pump's **EEPROM**. Repeating them wears it out. The UI warns when the same setting has been applied 3 or more times in the last 60 minutes. Do not work around a failure by publishing the command yourself with the retained flag: HeishaMon subscribes to `commands/#`, and a retained command runs again on every reconnect. This dashboard publishes commands non-retained. The two exceptions it does retain, on purpose, are the S0 counter sync (`s0/WatthourTotal/1` and `…/2`) and the OpenTherm bound inputs under `opentherm/read/`.

Optional-PCB commands stay hidden until that section is enabled, and they only take effect when PCB emulation is actually active. If emulation is on and HeishaMon stops sending for about 40 seconds, the heat pump raises **H74** and goes to standby.

If several settings fail in a row while other values keep changing, the UI can show that HeishaMon may be in listen-only mode (it received the bus but is not transmitting). Commands stay failed; nothing is silently marked successful.

## Firmware 3.2.3 and newer

Supported HeishaMon versions start at **3.2.3**. The version is the `version` field of the `stats` payload. Versions such as `3.9`, `4.0`, `3.61` and `v4.2.3` are recognised. A missing version, or a string that is not a release (`Local build`, `Alpha-…`, `Nightly-…`), is treated as **3.2.3**.

Every command has a minimum firmware. Commands introduced at 3.2.3 stay available when the version is unknown. A command whose minimum is **above** the detected version (or above 3.2.3 when the version is unknown) is disabled in the UI and rejected by the API with `422 firmware_too_old`.

Gated examples (not available on 3.2.3):

| Minimum | Commands |
|---|---|
| 3.9 | `SetExternalControl`, `SetExternalError`, `SetExternalCompressorControl`, `SetExternalHeatCoolControl`, `SetBivalentControl`, `SetBivalentMode`, `SetBivalentStartTemp`, `SetBivalentAPStartTemp`, `SetBivalentAPStopTemp` |
| 4.0 | `SetHeatingControl`, `SetSmartDHW`, `SetQuietModePriority`, `SetPumpFlowrateMode` |
| 4.1.2 | `SetDHWSensorSelection`, `SetDHWHeaterState`, `SetRoomHeaterState`, `SetHeaterOnOutdoorTemp` |
| 4.2.0 | `SetForceHeater` |
| 4.2.3 | `SetSterilizationTemp`, `SetSterilizationMaxTime` |

OpenTherm `opentherm/read/…` inputs need firmware 3.5 or newer. Operating-mode values 7 and 8 are shown when the heat pump reports them; `SetOperationMode` only accepts 0–6.

The simulator preset `fw-3.2.3` publishes the 3.2.3 topic set and stats shape, so the gated commands above stay disabled.

## Simulator

`tools/simulator.py` publishes a fake HeishaMon topic stream and echoes commands onto the read-back topics. It is for development and UI tests. **Do not point it at the live heat pump's base topic.** It would inject a second device and answer real commands. Use a test broker, or a base topic HeishaMon is not using.

It is not inside the runtime image. From a checkout (the virtualenv already includes the MQTT client):

```sh
.venv/bin/python tools/simulator.py \
  --host 127.0.0.1 \
  --port 1883 \
  --preset heat-only \
  --base panasonic_heat_pump \
  --fault SetQuietMode=drop
```

`--fault` may be repeated. The form is `NAME=MODE`. `NAME` is a command name or `*` for every command. Modes: `echo` (confirm immediately), `drop` (never confirm), `drop_first` (confirm on the retry), `delay:<seconds>`, `partial` (heating-curve JSON with one leaf omitted), `listen_only` (no command read-backs).

`--preset` accepts a canonical name or an alias such as `heat-only`, `Heat+DHW`, `Cool+DHW`, `auto (cool 7)`, `two-zone`, `PCB on`, `fw-3.2.3`. Other presets include `cool_only`, `dhw_only`, `heat_dhw`, `cool_dhw`, `auto_heat`, `auto_cool_mode7`, `two_zones_heat_curve_cool_direct`, `z1_water_z2_internal_thermostat`, `no_dhw_tank`, `with_extra`, `without_extra`, `pcb_active`, `no_integrations`, `all_integrations`, `unknown-inputs` and `profile-change`.

Run the dashboard against that same broker:

```sh
mkdir -p /tmp/heishamon-data
MQTT_HOST=127.0.0.1 MQTT_PORT=1883 DATA_DIR=/tmp/heishamon-data \
  PUBLIC_ORIGINS=http://127.0.0.1:8000 \
  .venv/bin/python -m heishamon_dashboard
```

Build the SPA first so `frontend/dist` exists (`npm --prefix frontend ci` and `npm --prefix frontend run build` in a checkout). Without it, the API still runs and `/` explains that the frontend has not been built.

## Tests

From a checkout (no Docker needed):

```sh
.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend run test
```

`npm --prefix frontend run test` runs Vitest. The Playwright end-to-end suite lives under `frontend/e2e`; run it from `frontend/`. Four backend tests are skipped: the real-capture replay and two catalog tests (`test_model_from_real_capture`, `test_real_capture_sentinels_and_enums`) that read the same fixture all stay skipped until `backend/tests/fixtures/replay_real.json` exists (see below), and one exemption case (`rules.py` itself) in the `rules.json` grep test.

## Privacy and a real MQTT capture

This is a public repository.

- Do not commit hostnames, addresses, usernames, passwords, or an MQTT capture from a real installation.
- The HeishaMon `ip` topic identifies the device. It must not appear in committed fixtures.
- Connection settings stay in the environment or in an uncommitted `.env`.

A real session for the replay test is captured **by the owner, on their own network**. `tools/capture.py` only subscribes. It does not publish. It does not read a `.env` file. Export the MQTT variables in the shell first (`MQTT_HOST` is required; `MQTT_PORT`, `MQTT_USER`, `MQTT_PASSWORD`, `MQTT_TLS`, `MQTT_CA_FILE` and `MQTT_BASE_TOPIC` are the same names as the dashboard).

```sh
MQTT_HOST=mqtt.example.invalid MQTT_PORT=1883 \
  .venv/bin/python tools/capture.py --duration 900 \
  --out backend/tests/fixtures/replay_real.json
```

`--duration` defaults to 900 seconds, long enough for HeishaMon's full re-publish. `--out` defaults to `backend/tests/fixtures/replay_real.json`. The script refuses to overwrite that file unless you pass `--force`.

What it writes is sanitized: the `ip` topic, the `log` topic and anything outside the known HeishaMon subtrees are dropped; `stats` is reduced to the `version` field; 1-wire addresses become stable pseudonyms (`1wire/pseudo-01`, …) and alias text is replaced with that pseudonym; a payload that still contains an IPv4 address, a MAC address or an email address is dropped. The broker address and the base topic are not stored. Topics in the file are relative to the base.

Until `backend/tests/fixtures/replay_real.json` exists, the real-replay test and the two catalog tests that read the same file are skipped. A synthetic replay from the simulator covers the meantime. Read the file before committing it and confirm it has no broker address, account, or `ip` topic.

## Run from a checkout

```sh
npm --prefix frontend ci
npm --prefix frontend run build
mkdir -p /tmp/heishamon-data
MQTT_HOST=mqtt.example.invalid DATA_DIR=/tmp/heishamon-data \
  .venv/bin/python -m heishamon_dashboard
```

Open `http://127.0.0.1:8000` only on a machine you trust, or set `PUBLIC_ORIGINS` and use the proxy above. The process listens on `0.0.0.0` inside its own host, so a firewall or a loopback-only proxy still matters.

## Licence of the data you see

Topic and command labels in this repository are written for this dashboard. HeishaMon's own documentation is not copied here.
