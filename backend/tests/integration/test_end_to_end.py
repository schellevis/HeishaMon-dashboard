"""End to end through a real MQTT broker: ingest → state → store → API/WebSocket, commands, liveness."""
import json

import pytest

from heishamon_dashboard import catalog as catalog_mod
from heishamon_dashboard.app import CATALOG_PATH

from .rig import BASE, FakeClock, hms, load_sim_modules, wait_for

simulator, presets = load_sim_modules()
CATALOG = catalog_mod.load(CATALOG_PATH)
POWER = "main/Heat_Power_Production"


def start_device(broker, preset, clock, **faults):
    """A simulated HeishaMon: retained snapshot now (before the app connects), command echoes later."""
    sim = simulator.Simulator(preset, faults, lambda t, p, r: broker.publish(t, p, r), clock)
    broker.on_command = sim.command
    sim.start()
    broker.drain()
    return sim


def as_version(text):
    return tuple(int(x) for x in text.split("."))


def seed_installation(broker, **overrides):
    """Retained configuration topics the sparse presets leave out, so every setting is applicable."""
    values = {
        "main/DHW_Installed": "1", "main/Buffer_Installed": "1", "main/Bivalent_Control": "1",
        "main/Solar_Mode": "0", "main/Liquid_Type": "0", "main/Optional_PCB": "0",
        "stats": json.dumps({"version": "v4.2.3", "board": "test-board"}),
    }
    values.update(overrides)
    for topic, payload in values.items():
        broker.publish(topic, payload, True)
    broker.drain()


def ws_messages(ws, until, limit=400):
    """Collect WebSocket messages until `until(message)` is true; returns them all."""
    seen = []
    for _ in range(limit):
        message = ws.receive_json()
        seen.append(message)
        if until(message):
            return seen
    raise AssertionError(f"expected message not received; got types {[m['type'] for m in seen][-10:]}")


def go_online(app, at):
    app.feed("LWT", "Online", at=at)
    assert app.state()["device_online"] == "online"


def test_ingest_state_store_api_ws(broker, make_app):
    clock = FakeClock(hms(4))
    app = make_app(clock=clock)
    with app:
        with app.client.websocket_connect("/api/ws") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello" and hello["state"]["broker_connected"] is True
            app.feed("LWT", "Online", at=hms(4))
            app.feed(POWER, "1000", at=hms(4, 0, 5))
            seq = hello["seq"]
            got = ws_messages(ws, lambda m: m["type"] == "value" and m["topic"] == POWER)
            value = got[-1]
            assert (value["value"], value["raw"], value["ts"], value["retained"]) == (1000, "1000", hms(4, 0, 5), False)
            assert value["seq"] > seq
            assert all(m["seq"] > seq for m in got)

        state = app.state()
        assert state["topics"][POWER]["value"] == 1000
        assert state["topics"][POWER]["retained_only"] is False
        assert state["device_online"] == "online" and state["broker_connected"] is True

        app.feed(POWER, "2000", at=hms(4, 0, 30))
        app.flush(at=hms(4, 1, 30))
        with app.db() as conn:
            rows = conn.execute("SELECT s.ts, s.num FROM samples s JOIN topics t ON t.id = s.topic_id "
                                "WHERE t.key = ? ORDER BY s.ts", (POWER,)).fetchall()
        assert [tuple(r) for r in rows] == [(hms(4, 0, 5), 1000.0), (hms(4, 0, 30), 2000.0)]

        history = app.client.get("/api/history", params={
            "topics": POWER, "from": hms(4), "to": hms(4, 1, 30), "max_points": 100}).json()
        assert history["resolution"] == "raw"
        assert [p[1] for p in history["series"][POWER]["points"]] == [1000, 2000]
        events = app.client.get("/api/events", params={"kind": "flush"}).json()["events"]
        assert events and events[0]["detail"]["samples"] >= 2


def test_command_echo_confirms_through_the_broker(broker, make_app):
    clock = FakeClock(hms(9), step=1)
    start_device(broker, "heat_dhw", clock)
    # a retained value that already equals the target (the snapshot value is replaced for the test)
    seed_installation(broker)
    broker.publish("main/DHW_Target_Temp", "48", True)
    broker.drain()
    app = make_app(clock=clock)
    with app:
        with app.client.websocket_connect("/api/ws") as ws:
            ws.receive_json()
            app.feed("LWT", "Online")
            state = app.state()
            assert state["topics"]["main/DHW_Target_Temp"]["retained_only"] is True
            assert state["topics"]["main/DHW_Target_Temp"]["value"] == 48

            response = app.client.post("/api/command", json={"name": "SetDHWTemp", "value": 48, "confirm": False})
            # a retained-only cache is never a no-op, and the retained value never confirms
            assert response.status_code == 201, response.text
            record = response.json()
            assert record["status"] == "pending" and record["retained"] is False and record["attempts"] == 1

            seen = ws_messages(ws, lambda m: m["type"] == "command" and m["command"]["status"] == "confirmed")
            assert [m["command"]["id"] for m in seen if m["type"] == "command"][-1] == record["id"]
            final = app.client.get(f"/api/commands/{record['id']}").json()
            assert final["status"] == "confirmed" and final["confirmed_ts"] > final["published_ts"]
            assert app.state()["topics"]["main/DHW_Target_Temp"]["retained_only"] is False

            # the device saw one non-retained command; the broker kept nothing retained under commands/
            assert broker.commands == [("SetDHWTemp", "48")]
            assert broker.retained_topics("commands/") == []

            # equal and now live: the same value is a no-op and publishes nothing
            again = app.client.post("/api/command", json={"name": "SetDHWTemp", "value": 48, "confirm": False})
            assert again.status_code == 200 and again.json()["status"] == "noop"
            assert len(broker.commands) == 1

        audit = app.client.get("/api/commands").json()["commands"]
        assert [c["status"] for c in audit] == ["noop", "confirmed"]


def test_command_without_echo_is_not_confirmed_by_the_retained_value(broker, make_app):
    clock = FakeClock(hms(9), step=1)
    start_device(broker, "heat_dhw", clock, SetDHWTemp="drop")
    seed_installation(broker)
    broker.publish("main/DHW_Target_Temp", "48", True)
    broker.drain()
    app = make_app(clock=clock)
    with app:
        app.feed("LWT", "Online")
        record = app.client.post("/api/command", json={"name": "SetDHWTemp", "value": 48, "confirm": False}).json()
        assert record["status"] == "pending"
        wait_for(lambda: broker.commands, what="command at the broker")
        app.feed("LWT", "Online")
        assert app.client.get(f"/api/commands/{record['id']}").json()["status"] == "pending"


def test_offline_and_online_through_the_broker(broker, make_app):
    app = make_app(clock=FakeClock(hms(4)))
    with app:
        with app.client.websocket_connect("/api/ws") as ws:
            ws.receive_json()
            app.feed("LWT", "Online", at=hms(4))
            app.feed(POWER, "1000", at=hms(4, 0, 1))
            for second in range(5, 131, 5):
                app.feed("LWT", "Online", at=hms(4, 0, second))
            last = hms(4, 2, 10)
            assert app.state()["device_online"] == "online"
            app.tick(at=hms(4, 2, 39))
            assert app.state()["device_online"] == "online"  # 29 s of silence: inside the 30 s floor
            app.tick(at=hms(4, 2, 40))
            assert app.state()["device_online"] == "offline"
            offline = ws_messages(ws, lambda m: m["type"] == "online" and m["device"] == "offline")[-1]
            assert offline["ts"] == last  # backdated to the last qualifying message

            # a retained snapshot value does not bring the device back; a heartbeat does
            app.feed("LWT", "Online", at=hms(4, 4, 0))
            assert app.state()["device_online"] == "online"
            ws_messages(ws, lambda m: m["type"] == "online" and m["device"] == "online")
        kinds = [e["kind"] for e in app.client.get("/api/events").json()["events"]]
        assert "device_offline" in kinds and "device_online" in kinds
        app.flush(at=hms(4, 5, 0))
        assert app.outages(kind="offline") == [(last, hms(4, 4, 0), "offline", None)]


def test_heartbeat_only_flush_then_timeout_reproduces_t7(broker, make_app):
    """Spec §5.4 T7 through MQTT → State → Store: a flush before the backdated timeout."""
    app = make_app(clock=FakeClock(hms(3, 59, 30)))
    with app:
        app.feed(POWER, "1000", at=hms(4))
        # heartbeat-only ingestion from 04:00:05 to 04:02:10 (LWT=Online every 5 s)
        for second in range(5, 131, 5):
            app.feed("LWT", "Online", at=hms(4, 0, second))
        assert app.state()["last_device_message"] == hms(4, 2, 10)

        app.flush(at=hms(4, 2, 30))  # device still online: H = 04:02:10, bucket 04:02 provisional
        provisional = {b: c for b, c, _ in app.rollups(POWER)}
        assert provisional[hms(4, 2) // 60_000] == 30

        app.tick(at=hms(4, 2, 40))  # 30 s timeout opens `offline` [04:02:10, open]
        assert app.state()["device_online"] == "offline"
        app.flush(at=hms(4, 5, 0))

        rows = {b: (c, a) for b, c, a in app.rollups(POWER)}
        minute = lambda m: hms(4, m) // 60_000  # noqa: E731
        assert rows[minute(0)][0] == 60 and rows[minute(1)][0] == 60
        assert rows[minute(2)] == (10, 1000.0)  # replaced the provisional 30 s
        assert rows[minute(3)][0] == 0 and rows[minute(4)][0] == 0
        energy = sum(c * a for m in range(5) for c, a in [rows[minute(m)]] if a is not None)
        assert energy == 130_000
        assert app.outages(kind="offline") == [(hms(4, 2, 10), None, "offline", None)]


def test_fw_3_2_3_preset_end_to_end(broker, make_app):
    clock = FakeClock(hms(9), step=1)
    start_device(broker, "fw-3.2.3", clock)
    app = make_app(clock=clock)
    with app:
        app.feed("LWT", "Online")
        system = app.system()
        assert system["firmware"] == "3.2.3" and system["firmware_assumed"] is False
        assert app.client.get("/api/profile").json()["firmware"]["value"] == "3.2.3"
        # no topic newer than the oldest firmware was published
        published = [CATALOG.topic(k) for k, tv in app.state()["topics"].items() if tv["catalogued"]]
        published = [t for t in published if t is not None and t["key"].startswith("main/")]
        assert len(published) > 50
        assert all(as_version(t["min_firmware"]) <= (3, 2, 3) for t in published)
        tested = {"too_old": 0, "allowed": 0}
        for command in CATALOG.commands:
            rng = command.get("range")
            if command.get("pcb") or command.get("type") != "int" or not rng or command.get("class") != "setting":
                continue
            response = app.client.post("/api/command", json={"name": command["name"], "value": rng["min"],
                                                            "confirm": True})
            code = response.json().get("error")
            if code in ("out_of_range", "bad_step", "not_allowed_value", "bad_type"):
                continue  # conditional ranges: the firmware gate is not reached for this value
            newer = as_version(command["min_firmware"]) > (3, 2, 3)
            assert (code == "firmware_too_old") == newer, (command["name"], command["min_firmware"], code)
            tested["too_old" if newer else "allowed"] += 1
        assert tested["too_old"] >= 1 and tested["allowed"] >= 1


def test_profile_change_preset_updates_the_profile_over_the_ws(broker, make_app):
    clock = FakeClock(hms(9))
    sim = start_device(broker, "profile-change", clock)
    app = make_app(clock=clock)
    with app:
        wait_for(lambda: all(k in app.svc.state.values for k in sim.values if k != "LWT"),
                 what="retained snapshot")
        with app.client.websocket_connect("/api/ws") as ws:
            hello = ws.receive_json()
            app.feed("LWT", "Online")
            before = hello["profile"]
            assert before["operating_mode"]["value"] == 0
            assert before["heating_control"]["value"] == "curve"

            clock.t = hms(9) + presets.PROFILE_CHANGE_MS + 1
            sim.tick()
            broker.drain()
            app.sync()
            changed = ws_messages(ws, lambda m: m["type"] == "profile" and
                                  m["profile"]["heating_control"]["value"] == "direct")[-1]["profile"]
            assert changed["operating_mode"]["value"] == 1
        assert app.client.get("/api/profile").json()["heating_control"]["value"] == "direct"
