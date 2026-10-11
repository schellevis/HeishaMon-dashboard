"""WebSocket /api/ws: hello/seq ordering and the push messages of spec §4.4."""
import threading

from heishamon_dashboard.types import Message

from .test_api import T0, Rig, wait_for


def take(ws, n):
    return [ws.receive_json() for _ in range(n)]


def test_hello_first_then_values_with_greater_seq(tmp_path):
    with Rig(tmp_path) as rig:
        rig.prime()
        with rig.client.websocket_connect("/api/ws") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello" and set(hello) == {"type", "seq", "state", "profile"}
            assert hello["seq"] == hello["state"]["seq"] == rig.svc.state.seq
            assert hello["profile"]["firmware"]["value"] == "v4.2.3"
            rig.feed("main/Outside_Temp", "4")
            rig.feed("main/Outside_Temp", "4")  # an unchanged value is still a value message
            first, second = take(ws, 2)
            assert first == {"type": "value", "seq": hello["seq"] + 1, "topic": "main/Outside_Temp",
                             "value": 4, "raw": "4", "ts": T0, "retained": False}
            assert second["seq"] == hello["seq"] + 2


def test_no_gap_or_duplicate_across_a_snapshot_taken_during_concurrent_values(tmp_path):
    with Rig(tmp_path) as rig:
        rig.prime()
        fed = []

        def feeder():
            for i in range(400):
                rig.call(rig.svc.ingest, Message("main/Outside_Temp", str(i % 40), False, T0))
                fed.append(i)

        thread = threading.Thread(target=feeder)
        thread.start()
        wait_for(lambda: len(fed) >= 20)
        with rig.client.websocket_connect("/api/ws") as ws:
            hello = ws.receive_json()
            thread.join()
            final = rig.svc.state.seq
            seqs = []
            while not seqs or seqs[-1] < final:
                seqs.append(ws.receive_json()["seq"])
        assert len(fed) == 400 and hello["type"] == "hello"
        assert hello["seq"] < final, "the snapshot must have been taken mid-stream"
        # exactly hello.seq+1 .. final, each once, in order
        assert seqs == list(range(hello["seq"] + 1, final + 1))
        # and the snapshot itself is consistent with its seq
        assert hello["state"]["seq"] == hello["seq"]


def test_every_client_gets_its_own_gap_free_stream(tmp_path):
    with Rig(tmp_path) as rig:
        rig.prime()
        with rig.client.websocket_connect("/api/ws") as a, rig.client.websocket_connect("/api/ws") as b:
            ha, hb = a.receive_json(), b.receive_json()
            rig.feed("main/Outside_Temp", "1")
            rig.feed("main/Outside_Temp", "2")
            assert [m["seq"] for m in take(a, 2)] == [ha["seq"] + 1, ha["seq"] + 2]
            assert [m["seq"] for m in take(b, 2)] == [hb["seq"] + 1, hb["seq"] + 2]
        wait_for(lambda: not rig.svc.hub.clients)


def test_profile_command_event_and_online_messages(tmp_path):
    with Rig(tmp_path) as rig:
        rig.prime()
        with rig.client.websocket_connect("/api/ws") as ws:
            hello = ws.receive_json()
            assert hello["profile"]["heating_control"]["value"] == "curve"

            rig.feed("main/Heating_Mode", "1")  # a profile input changes
            value, profile = take(ws, 2)
            assert value["type"] == "value" and profile["type"] == "profile"
            assert profile["profile"]["heating_control"]["value"] == "direct"
            assert profile["seq"] == value["seq"] + 1

            rig.feed("main/Outside_Temp", "5")  # not a profile input: no profile message
            assert ws.receive_json()["type"] == "value"

            response = rig.post("SetDHWTemp", 52)
            assert response.status_code == 201
            command = ws.receive_json()
            assert command["type"] == "command" and command["command"] == response.json()

            rig.feed("main/Defrosting_State", "0")
            rig.feed("main/Defrosting_State", "1")
            kinds = [m["type"] for m in take(ws, 3)]
            assert kinds == ["value", "value", "event"]

            rig.feed("LWT", "Offline")
            msgs = take(ws, 3)
            assert sorted(m["type"] for m in msgs) == ["event", "online", "value"]
            online = next(m for m in msgs if m["type"] == "online")
            assert online["device"] == "offline" and online["broker"] is True and set(online) == {
                "type", "seq", "device", "broker", "ts"}
            seqs = [m["seq"] for m in msgs]
            assert seqs == sorted(seqs) and len(set(seqs)) == 3


def test_flush_result_arrives_as_an_event_message(tmp_path):
    with Rig(tmp_path) as rig:
        rig.prime()
        with rig.client.websocket_connect("/api/ws") as ws:
            ws.receive_json()
            flush_id = rig.client.post("/api/system/flush", json={}).json()["flush_id"]
            message = ws.receive_json()
            assert message["type"] == "event" and message["event"]["kind"] == "flush"
            assert message["event"]["detail"]["flush_id"] == flush_id


def test_slow_client_is_dropped_and_can_resync(tmp_path):
    with Rig(tmp_path) as rig:
        rig.prime()
        client = rig.call(rig.svc.hub.register)
        for i in range(2100):
            rig.feed("main/Outside_Temp", str(i % 9))
        assert client not in rig.svc.hub.clients  # overflowed: removed and told to close
        assert rig.call(lambda: client.queue.get_nowait()) is None
