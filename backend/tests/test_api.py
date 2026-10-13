"""REST routes of spec §4.4, end to end through FastAPI's TestClient (no network, fake broker)."""
import asyncio
import csv
import io
import json
import sqlite3
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from heishamon_dashboard import config as config_mod
from heishamon_dashboard.app import build
from heishamon_dashboard.types import Message

from ._client import LocalClient

BASE = "panasonic_heat_pump"
T0 = 1_791_000_000_000  # a multiple of 15 minutes
JSON = {"content-type": "application/json"}


# ----------------------------------------------------------------- shared helpers
# (imported by the other test_*.py files of this task)


class FakeClock:
    def __init__(self, t=T0):
        self.t = t

    def now_ms(self):
        return self.t


class NullHandle:
    def cancel(self):
        pass


class NullScheduler:
    """No retry or terminal timers: command confirmation is not under test here."""

    def call_later(self, delay_s, callback):
        return NullHandle()


class FakeBroker:
    """Stands in for aiomqtt: records publishes and lets tests inject received messages."""

    def __init__(self):
        self.published = []  # (topic, payload, qos, retain)
        self.subscribed = []
        self.queue = None

    def factory(self):
        return FakeClient(self)

    async def push(self, topic, payload, retain=False):
        await self.queue.put(SimpleNamespace(topic=f"{BASE}/{topic}", payload=payload.encode(), retain=retain))


class FakeClient:
    def __init__(self, broker):
        self.broker = broker

    async def __aenter__(self):
        if self.broker.queue is None:
            self.broker.queue = asyncio.Queue()
        return self

    async def __aexit__(self, *exc):
        return False

    async def subscribe(self, topic):
        self.broker.subscribed.append(topic)

    async def publish(self, topic, payload, qos=0, retain=False):
        self.broker.published.append((topic, payload, qos, retain))

    @property
    def messages(self):
        return self._messages()

    async def _messages(self):
        while True:
            yield await self.broker.queue.get()


def make_config(tmp_path, **env):
    values = {"MQTT_HOST": "broker.test", "DATA_DIR": str(tmp_path / "data"), "FLUSH_INTERVAL_SECONDS": "900"}
    values.update(env)
    return config_mod.load(values)


def wait_for(predicate, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    raise AssertionError("condition not reached in time")


# live configuration topics that make every catalog command applicable
PROFILE_FEED = {
    "main/Operating_Mode_State": "0",
    "main/Zones_State": "2",
    "main/Heating_Mode": "0",
    "main/Cooling_Mode": "0",
    "main/Z1_Sensor_Settings": "0",
    "main/Z2_Sensor_Settings": "0",
    "main/DHW_Installed": "1",
    "main/Buffer_Installed": "1",
    "main/Bivalent_Control": "1",
    "stats": json.dumps({"version": "v4.2.3", "board": "test-board"}),
}


class Rig:
    """An app with a fake broker inside a running TestClient (lifespan active)."""

    def __init__(self, tmp_path, *, env=None, static_dir=None, tick_interval=3600.0, **kw):
        self.broker = FakeBroker()
        self.clock = FakeClock()
        self.app = build(make_config(tmp_path, **(env or {})), self.broker.factory, self.clock,
                         scheduler=NullScheduler(), static_dir=static_dir or tmp_path / "no-dist",
                         tick_interval=tick_interval, **kw)
        self.svc = self.app.state.services
        self.client = LocalClient(self.app)
        self.data_dir = tmp_path / "data"

    def __enter__(self):
        self.client.__enter__()
        wait_for(lambda: self.svc.mqtt.connected)
        return self

    def __exit__(self, *exc):
        return self.client.__exit__(*exc)

    def call(self, fn, *args):
        """Run `fn` on the app's event loop (the services are not thread-safe)."""
        return self.client.portal.call(fn, *args)

    def feed(self, topic, payload, retained=False):
        self.call(self.svc.ingest, Message(topic, payload, retained, self.clock.t))

    def prime(self, extra=None):
        self.feed("LWT", "Online")
        for topic, payload in {**PROFILE_FEED, **(extra or {})}.items():
            self.feed(topic, payload)

    def post(self, name, value, confirm=False, **kw):
        return self.client.post("/api/command", json={"name": name, "value": value, "confirm": confirm}, **kw)


@pytest.fixture
def rig(tmp_path):
    with Rig(tmp_path) as r:
        yield r


# -------------------------------------------------------------------------- tests

STATE_KEYS = {"seq", "topics", "device_online", "last_device_message", "broker_connected",
              "listen_only_suspected"}
TOPIC_VALUE_KEYS = {"value", "raw", "kind", "unit", "decimals", "enum_label", "catalogued", "sentinel",
                    "last_change", "last_seen", "retained_only"}
COMMAND_KEYS = {"id", "name", "payload", "retained", "class", "status", "submitted_ts", "published_ts",
                "confirmed_ts", "attempts", "prev_value", "detail", "keys", "eeprom_warning"}
SYSTEM_KEYS = {"broker_connected", "device_online", "firmware", "firmware_assumed", "stats",
               "listen_only_suspected", "db_bytes", "last_flush_ts", "last_flush_ok", "last_flush_error",
               "flush_interval_s", "buffer", "dropped"}


def test_state_shape(rig):
    rig.prime()
    rig.feed("main/Outside_Temp", "7")
    rig.feed("main/Heatpump_State", "-1", retained=True)
    rig.feed("main/Uncatalogued_Thing", "abc")
    body = rig.client.get("/api/state").json()
    assert set(body) == STATE_KEYS
    assert body["seq"] > 0 and body["device_online"] == "online" and body["broker_connected"] is True
    assert body["last_device_message"] == T0 and body["listen_only_suspected"] is False
    mode = body["topics"]["main/Operating_Mode_State"]
    assert set(mode) == TOPIC_VALUE_KEYS
    assert mode["value"] == 0 and mode["kind"] == "enum" and mode["catalogued"] is True
    assert mode["enum_label"]["en"] == "Heating" and set(mode["enum_label"]) == {"en", "nl"}
    assert mode["retained_only"] is False and mode["sentinel"] is False
    outside = body["topics"]["main/Outside_Temp"]
    assert outside["unit"] is not None and outside["enum_label"] is None
    unknown = body["topics"]["main/Uncatalogued_Thing"]
    assert unknown["catalogued"] is False and unknown["kind"] == "text" and unknown["value"] == "abc"
    sentinel = body["topics"]["main/Heatpump_State"]
    assert sentinel["sentinel"] is True and sentinel["retained_only"] is True


def test_profile_shape(rig):
    rig.prime()
    body = rig.client.get("/api/profile").json()
    assert body["computed_at"] == T0
    assert body["zones"] == {"value": "both", "unknown": False, "stale": False}
    assert body["firmware"]["value"] == "v4.2.3" and body["firmware_assumed"] is False
    assert body["zone"]["z2"]["active"]["value"] is True
    assert body["has_extra"]["value"] is False


def test_history_json_and_csv_have_the_same_points(rig):
    rig.prime()
    for minute, value in enumerate(["3", "4", "5", "6"]):
        rig.clock.t = T0 + minute * 60_000
        rig.feed("LWT", "Online")
        rig.feed("main/Outside_Temp", value)
        rig.feed("main/Operating_Mode_State", str(minute % 2))
        rig.feed("main/Unlisted_Text", f"say \"hi\", {minute}")
    rig.clock.t = T0 + 5 * 60_000
    topics = "main/Outside_Temp,main/Operating_Mode_State,main/Unlisted_Text"
    query = f"topics={topics}&from={T0}&to={T0 + 6 * 60_000}&max_points=500"
    js = rig.client.get(f"/api/history?{query}").json()
    assert set(js) == {"resolution", "partial", "series"} and js["resolution"] == "raw"
    assert js["series"]["main/Outside_Temp"]["kind"] == "number"
    assert js["series"]["main/Operating_Mode_State"]["kind"] == "enum"
    assert js["series"]["main/Unlisted_Text"]["kind"] == "text"
    assert [p[1] for p in js["series"]["main/Outside_Temp"]["points"]][-4:] == [3, 4, 5, 6]

    response = rig.client.get(f"/api/history.csv?{query}")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == ["topic", "ts", "resolution", "value", "covered_seconds"]
    expected = []
    for topic in topics.split(","):
        for point in js["series"][topic]["points"]:
            expected.append([topic, str(point[0]), "raw",
                             point[1] if isinstance(point[1], str) else repr(point[1]) if isinstance(point[1], float)
                             else str(point[1]), ""])
    assert rows[1:] == expected
    assert '"say ""hi"", 0"' in response.text  # text values are always RFC 4180-quoted


def test_history_rollup_csv_has_covered_seconds(rig):
    rig.prime()
    rig.feed("main/Outside_Temp", "7")
    rig.clock.t = T0 + 2 * 86_400_000  # > 6 h: served from rollups
    rig.feed("LWT", "Online")
    query = f"topics=main/Outside_Temp&from={T0}&to={T0 + 2 * 86_400_000}&max_points=10000"
    js = rig.client.get(f"/api/history?{query}").json()
    assert js["resolution"] in ("1m", "1h")
    rows = list(csv.reader(io.StringIO(rig.client.get(f"/api/history.csv?{query}").text)))[1:]
    points = js["series"]["main/Outside_Temp"]["points"]
    assert len(rows) == len(points) > 0
    for row, point in zip(rows, points):
        assert row[2] == js["resolution"] and row[1] == str(point[0]) and row[4] == str(point[2])
        assert (row[3] == "") == (point[1] is None)


@pytest.mark.parametrize("query", [
    "",
    "topics=a",
    "topics=a&from=5&to=5",
    "topics=a&from=9&to=5",
    "topics=a&from=x&to=5",
    "topics=a&from=1&to=5&max_points=9",
    "topics=a&from=1&to=5&max_points=10001",
    "topics=" + ",".join(f"t{i}" for i in range(21)) + "&from=1&to=5",
])
def test_history_validation_422(rig, query):
    for path in ("/api/history", "/api/history.csv"):
        response = rig.client.get(f"{path}?{query}")
        assert response.status_code == 422
        assert set(response.json()) == {"error", "message", "detail"}


def test_history_accepts_twenty_topics_and_raw_topic_names(rig):
    rig.prime()
    topics = ",".join(["main/Outside_Temp"] + [f"raw/topic{i}" for i in range(19)])
    response = rig.client.get(f"/api/history?topics={topics}&from={T0 - 1000}&to={T0 + 1000}")
    assert response.status_code == 200 and len(response.json()["series"]) == 20


def test_command_success_shape_and_publish(rig):
    rig.prime()
    response = rig.post("SetDHWTemp", 55)
    assert response.status_code == 201
    body = response.json()
    assert set(body) == COMMAND_KEYS
    assert body["name"] == "SetDHWTemp" and body["payload"] == "55" and body["retained"] is False
    assert body["class"] == "setting" and body["status"] == "pending" and body["attempts"] == 1
    assert body["keys"] is None and body["submitted_ts"] == T0
    assert rig.broker.published == [(f"{BASE}/commands/SetDHWTemp", "55", 0, False)]
    assert rig.client.get(f"/api/commands/{body['id']}").json() == body
    assert [c["id"] for c in rig.client.get("/api/commands").json()["commands"]] == [body["id"]]


def test_command_noop_is_200(rig):
    rig.prime({"main/DHW_Target_Temp": "55"})
    response = rig.post("SetDHWTemp", 55)
    assert response.status_code == 200 and response.json()["status"] == "noop"
    assert rig.broker.published == []


def test_command_errors_are_422_with_error_body(rig):
    rig.prime()
    cases = [
        (("SetDHWTemp", 99), "out_of_range"),
        (("SetDHWTemp", 55.5), "bad_type"),
        (("SetDHWTemp", 55.0), "bad_type"),
        (("SetDHWTemp", True), "bad_type"),
        (("NoSuchCommand", 1), "unknown_command"),
        (("SetReset", 1), "confirm_required"),
        (("SetOperationMode", 7), "read_only_value"),
    ]
    for (name, value), code in cases:
        response = rig.post(name, value)
        assert response.status_code == 422, (name, value)
        body = response.json()
        assert body["error"] == code and set(body) == {"error", "message", "detail"}
    assert rig.broker.published == []
    kinds = [e["kind"] for e in rig.client.get("/api/events?kind=command_rejected").json()["events"]]
    assert len(kinds) == len(cases)  # every rejection is in the event log, none in the command log
    assert rig.client.get("/api/commands").json() == {"commands": []}


def test_command_503_when_broker_is_down(rig):
    rig.prime()
    rig.svc.mqtt.connected = False
    response = rig.post("SetDHWTemp", 50)
    assert response.status_code == 503 and response.json()["error"] == "broker_disconnected"


def test_command_503_storage_unavailable(rig, monkeypatch):
    rig.prime()
    monkeypatch.setattr(rig.svc.store, "protected_budget_ok", lambda: False)
    response = rig.post("SetDHWTemp", 50)
    assert response.status_code == 503 and response.json()["error"] == "storage_unavailable"


def test_command_422_for_device_offline_and_write_lock(rig):
    rig.prime()
    prefs = rig.client.get("/api/prefs").json()
    rig.client.put("/api/prefs", json={**prefs, "write_lock": True})
    assert rig.post("SetDHWTemp", 50).json()["error"] == "write_lock"
    rig.client.put("/api/prefs", json={**prefs, "write_lock": False})
    rig.clock.t += 10 * 60_000
    rig.call(rig.svc.tick)
    assert rig.client.get("/api/state").json()["device_online"] == "offline"
    response = rig.post("SetDHWTemp", 50)
    assert response.status_code == 422 and response.json()["error"] == "device_offline"


def test_command_body_validation(rig):
    rig.prime()
    assert rig.client.post("/api/command", content=b"{not json", headers=JSON).status_code == 400
    assert rig.client.post("/api/command", content=b'{"name":"SetDHWTemp","value":NaN}',
                           headers=JSON).status_code == 400
    for body in ([], {"value": 1}, {"name": "SetDHWTemp"}, {"name": 5, "value": 1},
                 {"name": "SetDHWTemp", "value": 50, "confirm": "yes"},
                 {"name": "SetDHWTemp", "value": 50, "extra": 1}):
        response = rig.client.post("/api/command", json=body)
        assert response.status_code == 422, body
        assert response.json()["error"] == "bad_type"
    assert rig.client.post("/api/command", content=b"name=SetDHWTemp",
                           headers={"content-type": "application/x-www-form-urlencoded"}).status_code == 415
    assert rig.client.post("/api/command", content=b"{}", headers={"content-type": "text/plain"}).status_code == 415


def test_no_409_for_commands_a_newer_one_supersedes(rig):
    rig.prime()
    first = rig.post("SetDHWTemp", 50)
    second = rig.post("SetDHWTemp", 52)
    assert first.status_code == 201 and second.status_code == 201
    assert rig.client.get(f"/api/commands/{first.json()['id']}").json()["status"] == "superseded"
    assert rig.client.get(f"/api/commands/{second.json()['id']}").json()["status"] == "pending"


def test_unknown_command_id_and_routes_are_404(rig):
    response = rig.client.get(f"/api/commands/{'0' * 8}-nope")
    assert response.status_code == 404 and response.json()["error"] == "not_found"
    for path in ("/api/nothing", "/api"):
        response = rig.client.get(path)
        assert response.status_code == 404 and set(response.json()) == {"error", "message", "detail"}
    assert rig.client.post("/api/nothing", json={}).status_code == 404


def test_commands_and_events_listing_params(rig):
    rig.prime()
    ids = []
    for i, value in enumerate((50, 51, 52)):
        rig.clock.t = T0 + i * 1000
        ids.append(rig.post("SetDHWTemp", value).json()["id"])
    listed = rig.client.get("/api/commands").json()["commands"]
    assert [c["id"] for c in listed] == ids[::-1]  # newest first
    assert [c["id"] for c in rig.client.get("/api/commands?limit=2").json()["commands"]] == ids[::-1][:2]
    assert [c["id"] for c in rig.client.get(f"/api/commands?since={T0 + 1000}").json()["commands"]] == ids[:0:-1]
    for bad in ("limit=0", "limit=1001", "limit=x", "since=x"):
        assert rig.client.get(f"/api/commands?{bad}").status_code == 422
        assert rig.client.get(f"/api/events?{bad}").status_code == 422
    rig.feed("main/Defrosting_State", "0")
    rig.clock.t += 1000
    rig.feed("main/Defrosting_State", "1")
    events = rig.client.get("/api/events?kind=defrost_start").json()["events"]
    assert [(e["kind"], set(e)) for e in events] == [("defrost_start", {"ts", "kind", "detail"})]
    assert rig.client.get("/api/events?limit=1").json()["events"][0]["ts"] == rig.clock.t
    assert rig.client.get(f"/api/events?since={rig.clock.t + 1}").json() == {"events": []}


def test_prefs_defaults_roundtrip_and_schema(rig):
    default = {"write_lock": False, "pcb_enabled": False, "topic_visibility": {}, "feature_overrides": {},
               "tiles": [], "chart_presets": []}
    assert rig.client.get("/api/prefs").json() == default
    new = {"write_lock": True, "pcb_enabled": True,
           "topic_visibility": {"main/Outside_Temp": "hidden", "main/Defrosting_State": "ignored"},
           "feature_overrides": {"z2": "show"}, "tiles": ["main/Outside_Temp"],
           "chart_presets": [{"name": "Water", "topics": ["main/Main_Outlet_Temp"]}]}
    response = rig.client.put("/api/prefs", json=new)
    assert response.status_code == 200 and response.json() == new
    assert rig.client.get("/api/prefs").json() == new
    assert any(o["kind"] == "ignored" and o["topic"] == "main/Defrosting_State"
               for o in rig.svc.store.outages_list())

    unknown = {**new, "language": "nl"}
    missing = {k: v for k, v in new.items() if k != "tiles"}
    bad_values = [
        {**new, "write_lock": "yes"},
        {**new, "topic_visibility": {"a": "shown"}},
        {**new, "feature_overrides": {"z2": "hide"}},
        {**new, "tiles": "main/Outside_Temp"},
        {**new, "tiles": ["not_a_tile"]},
        {**new, "tiles": ["outsideTemp", "main/Nope_Topic"]},
        {**new, "tiles": [3]},
        {**new, "chart_presets": [{"name": "x"}]},
        {**new, "chart_presets": [{"name": "x", "topics": [], "extra": 1}]},
        [], "text",
    ]
    for body in [unknown, missing, *bad_values]:
        response = rig.client.put("/api/prefs", json=body)
        assert response.status_code == 422, body
        assert set(response.json()) == {"error", "message", "detail"}
    assert rig.client.put("/api/prefs", content=b"{", headers=JSON).status_code == 400
    assert rig.client.get("/api/prefs").json() == new  # rejected writes changed nothing


def test_prefs_tiles_accept_builtin_ids_and_catalogued_keys(rig):
    prefs = rig.client.get("/api/prefs").json()
    for tiles in (["outsideTemp", "cop"], ["main/DHW_Temp"], ["dhwTemp", "main/Outside_Temp"]):
        response = rig.client.put("/api/prefs", json={**prefs, "tiles": tiles})
        assert response.status_code == 200 and response.json()["tiles"] == tiles
    response = rig.client.put("/api/prefs", json={**prefs, "tiles": ["outsideTemp", "bogus"]})
    assert response.status_code == 422 and response.json()["error"] == "bad_type"
    assert rig.client.get("/api/prefs").json()["tiles"] == ["dhwTemp", "main/Outside_Temp"]


def test_stored_invalid_tiles_are_dropped_on_load(rig):
    stored = {**rig.client.get("/api/prefs").json(), "tiles": ["outsideTemp", "gone", "main/DHW_Temp", 7]}
    rig.svc.store.prefs_put(stored)
    assert rig.client.get("/api/prefs").json()["tiles"] == ["outsideTemp", "main/DHW_Temp"]


def test_system_shape(rig):
    body = rig.client.get("/api/system").json()
    assert set(body) == SYSTEM_KEYS
    assert body["firmware"] is None and body["firmware_assumed"] is True and body["stats"] is None
    assert body["broker_connected"] is True and body["device_online"] == "unknown"
    assert body["flush_interval_s"] == 900 and body["last_flush_ts"] is None and body["last_flush_ok"] is True
    assert body["last_flush_error"] is None
    assert set(body["buffer"]) == {"samples", "sample_bytes", "protected"}
    assert body["dropped"] == {"samples": 0, "ingest": 0}
    rig.prime()
    body = rig.client.get("/api/system").json()
    assert body["firmware"] == "v4.2.3" and body["firmware_assumed"] is False
    assert body["stats"]["board"] == "test-board" and body["device_online"] == "online"
    assert body["buffer"]["samples"] > 0


def test_oversized_messages_are_counted_in_system_and_an_event(rig):
    rig.prime()
    rig.feed("x" * 300, "1")
    rig.feed("main/Big", "y" * 70_000)
    assert rig.client.get("/api/system").json()["dropped"]["ingest"] == 2
    assert rig.client.post("/api/system/flush", json={}).status_code == 202
    wait_for(lambda: rig.client.get("/api/events?kind=ingest_dropped").json()["events"])
    event = rig.client.get("/api/events?kind=ingest_dropped").json()["events"][0]
    assert event["detail"] == {"count": 2}
    assert rig.client.get("/api/system").json()["dropped"]["ingest"] == 2


def test_flush_202_then_flush_event_and_frontier(rig):
    rig.prime()
    response = rig.client.post("/api/system/flush", json={})
    assert response.status_code == 202 and set(response.json()) == {"flush_id"}
    wait_for(lambda: rig.client.get("/api/events?kind=flush").json()["events"])
    system = rig.client.get("/api/system").json()
    assert system["last_flush_ts"] == T0 and system["last_flush_ok"] is True and system["buffer"]["samples"] == 0
    # the Liveness snapshot reached the store
    assert rig.svc.store.frontier() == {"flush_ts": T0, "device_online": "online", "last_qualifying_ts": T0}


def test_flush_409_while_one_is_running(rig, monkeypatch):
    rig.prime()
    entered, release = threading.Event(), threading.Event()
    real = rig.svc.store.flush

    def slow(now, liveness):
        entered.set()
        release.wait(5)
        return real(now, liveness)

    monkeypatch.setattr(rig.svc.store, "flush", slow)
    assert rig.client.post("/api/system/flush", json={}).status_code == 202
    assert entered.wait(5)
    second = rig.client.post("/api/system/flush", json={})
    assert second.status_code == 409 and second.json()["error"] == "flush_in_progress"
    release.set()
    wait_for(lambda: not rig.svc.flushing)
    assert rig.client.post("/api/system/flush", json={}).status_code == 202


def test_timer_flushes_when_the_interval_has_passed(rig):
    rig.prime()
    rig.call(rig.svc.tick)
    assert rig.svc.store.last_flush_ts is None
    rig.clock.t += 900_000
    rig.feed("LWT", "Online")
    rig.call(rig.svc.tick)
    wait_for(lambda: rig.svc.store.last_flush_ts == rig.clock.t)


def test_shutdown_flushes_buffered_samples(tmp_path):
    with Rig(tmp_path) as rig:
        rig.prime()
        rig.feed("main/Outside_Temp", "7")
    db = next((tmp_path / "data").glob("*.db"))
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT count(*) FROM samples").fetchone()[0] > 0
        assert conn.execute("SELECT count(*) FROM frontier").fetchone()[0] == 1
    finally:
        conn.close()


def test_mqtt_messages_flow_through_the_wiring(rig):
    assert rig.broker.subscribed == [f"{BASE}/#"]
    rig.call(rig.broker.push, "LWT", "Online")
    rig.call(rig.broker.push, "main/Outside_Temp", "3")
    wait_for(lambda: rig.client.get("/api/state").json()["topics"].get("main/Outside_Temp"))
    state = rig.client.get("/api/state").json()
    assert state["device_online"] == "online" and state["topics"]["main/Outside_Temp"]["value"] == 3
    kinds = [e["kind"] for e in rig.client.get("/api/events").json()["events"]]
    assert "broker_connected" in kinds


def test_device_offline_and_online_transitions(rig):
    rig.prime()
    rig.clock.t += 60_000
    rig.call(rig.svc.tick)  # no qualifying message for > the liveness timeout
    state = rig.client.get("/api/state").json()
    assert state["device_online"] == "offline"
    assert any(o["kind"] == "offline" and o["start_ts"] == T0 for o in rig.svc.store.outages_list())
    rig.feed("LWT", "Online")
    assert rig.client.get("/api/state").json()["device_online"] == "online"
    kinds = [e["kind"] for e in rig.client.get("/api/events").json()["events"]]
    assert "device_offline" in kinds and "device_online" in kinds


def test_static_spa_serving(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>spa</title>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("secret")
    with Rig(tmp_path, static_dir=dist) as rig:
        assert "<title>spa</title>" in rig.client.get("/").text
        assert rig.client.get("/assets/app.js").text == "console.log(1)"
        assert "<title>spa</title>" in rig.client.get("/system/page").text  # client-side routes
        assert "secret" not in rig.client.get("/%2e%2e/secret.txt").text
        assert "secret" not in rig.client.get("/..%2fsecret.txt").text
        missing = rig.client.get("/api/nothing")
        assert missing.status_code == 404 and missing.json()["error"] == "not_found"


def test_placeholder_when_the_frontend_is_not_built(rig):
    response = rig.client.get("/")
    assert response.status_code == 404 and "not been built" in response.text


# ------------------------------------------------------------------ B2 to B5, T03


def test_body_too_large_413(rig):
    rig.prime()
    big = json.dumps({"name": "SetDHWTemp", "value": 50, "pad": "x" * 70_000})
    for path in ("/api/command", "/api/prefs", "/api/system/flush"):
        method = rig.client.put if path == "/api/prefs" else rig.client.post
        response = method(path, content=big, headers=JSON)
        assert response.status_code == 413 and response.json()["error"] == "body_too_large", path
    # a chunked body without Content-Length is cut off as well
    response = rig.client.post("/api/command", content=iter([b"x" * 40_000, b"x" * 40_000]), headers=JSON)
    assert response.status_code == 413 and response.json()["error"] == "body_too_large"
    assert rig.client.get("/api/commands").json() == {"commands": []}


def test_long_command_name_not_echoed(rig):
    rig.prime()
    name = "Z" * 300
    response = rig.post(name, 1)
    assert response.status_code == 422 and response.json()["error"] == "unknown_command"
    assert "ZZZ" not in response.text


def test_topic_visibility_key_validation(rig):
    prefs = rig.client.get("/api/prefs").json()
    rig.feed("main/Seen_Live", "1")
    ok = {**prefs, "topic_visibility": {"main/Outside_Temp": "hidden", "main/Seen_Live": "hidden"}}
    assert rig.client.put("/api/prefs", json=ok).status_code == 200
    for key in ["a" * 257, "main/+", "main/#", "/main/Outside_Temp", "main/Never_Seen", ""]:
        response = rig.client.put("/api/prefs", json={**prefs, "topic_visibility": {key: "hidden"}})
        assert response.status_code == 422 and response.json()["error"] == "bad_type", key
    assert rig.client.get("/api/prefs").json() == ok
    # invalid keys already stored (older versions) are dropped on load, with a warning
    rig.svc.store.prefs_put({"topic_visibility": {"main/Outside_Temp": "hidden", "bad/#": "hidden"}})
    assert rig.client.get("/api/prefs").json()["topic_visibility"] == {"main/Outside_Temp": "hidden"}


def test_csv_formula_prefix(rig):
    from heishamon_dashboard.api.history import history_csv

    series = {"kind": "text", "points": [[1, "=1+1"], [2, "+x"], [3, "-x"], [4, "@x"], [5, "\tx"], [6, "\rx"],
                                          [7, "plain"]]}
    history = {"resolution": "raw", "series": {"=topic": series}}
    text = history_csv(history, ["=topic"])
    assert "'=topic" in text
    values = [row[3] for row in list(csv.reader(io.StringIO(text)))[1:]]
    assert values == ["'=1+1", "'+x", "'-x", "'@x", "'\tx", "'\rx", "plain"]
    number = {"resolution": "raw", "series": {"t": {"kind": "number", "points": [[1, -5], [2, -1.5]]}}}
    assert [r[3] for r in list(csv.reader(io.StringIO(history_csv(number, ["t"]))))[1:]] == ["-5", "-1.5"]


def test_command_rate_env_reaches_the_service(tmp_path):
    with Rig(tmp_path, env={"COMMAND_RATE_MAX": "3", "COMMAND_RATE_WINDOW_S": "120"}) as r:
        assert r.svc.commands.rate_max == 3 and r.svc.commands.rate_window_s == 120


# ------------------------------------------------------------------ /api/energy (F2)

def _ms(year, month, day, hour=0, tz="UTC"):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return int(datetime(year, month, day, hour, tzinfo=ZoneInfo(tz)).timestamp() * 1000)


def test_energy_endpoint_periods(rig):
    from zoneinfo import ZoneInfo
    from heishamon_dashboard.api.energy import energy_range

    ams = ZoneInfo("Europe/Amsterdam")
    # a DST change (25 Oct 2026, 25-hour day) lies inside the 14 local days; ranges are local midnights
    now = _ms(2026, 10, 27, 12, "Europe/Amsterdam")
    assert energy_range("day", now, ams) == (_ms(2026, 10, 14, tz="Europe/Amsterdam"), now)
    assert energy_range("month", now, ams) == (_ms(2025, 11, 1, tz="Europe/Amsterdam"), now)
    assert energy_range("year", now, ams) == (_ms(2022, 1, 1, tz="Europe/Amsterdam"), now)
    # year boundary: 12 months ending January, and the year range still starts four years back
    now = _ms(2027, 1, 1, 0, "Europe/Amsterdam") + 60_000
    assert energy_range("day", now, ams)[0] == _ms(2026, 12, 19, tz="Europe/Amsterdam")
    assert energy_range("month", now, ams)[0] == _ms(2026, 2, 1, tz="Europe/Amsterdam")
    assert energy_range("year", now, ams)[0] == _ms(2023, 1, 1, tz="Europe/Amsterdam")

    rig.prime()
    for minute in range(0, 180, 5):
        rig.clock.t = T0 + minute * 60_000
        rig.feed("LWT", "Online")
        rig.feed("main/Heat_Power_Production", "1000")
        rig.feed("main/Heat_Power_Consumption", "500")
    rig.clock.t = T0 + 180 * 60_000
    rig.feed("LWT", "Online")
    body = rig.client.get("/api/energy?period=day").json()
    assert set(body) >= {"tz", "from", "to", "period", "estimate", "periods"}
    assert body["period"] == "day" and body["tz"] == "UTC" and body["to"] == rig.clock.t
    assert body["estimate"] is True
    assert body["from"] == _ms(2026, 9, 20)  # T0 is 2026-10-03 (UTC): 14 days ending today
    row = body["periods"]["2026-10-03"]["heat"]
    assert row["production_kwh"] > 0 and row["consumption_kwh"] > 0
    month = rig.client.get("/api/energy?period=month").json()
    assert month["from"] == _ms(2025, 11, 1) and "2026-10" in month["periods"]
    year = rig.client.get("/api/energy?period=year").json()
    assert year["from"] == _ms(2022, 1, 1) and "2026" in year["periods"]

    for query in ("period=week", "period=", ""):
        response = rig.client.get(f"/api/energy?{query}")
        assert response.status_code == 422 and response.json()["error"] == "bad_param"


def test_energy_endpoint_uses_configured_tz(tmp_path):
    with Rig(tmp_path, env={"TZ": "Pacific/Auckland"}) as r:
        body = r.client.get("/api/energy?period=day").json()
        assert body["tz"] == "Pacific/Auckland"
        assert body["from"] == _ms(2026, 9, 20, tz="Pacific/Auckland")
