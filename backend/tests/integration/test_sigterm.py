"""A11 (automated part): SIGTERM flushes, the child exits within 60 s, the data survives a restart."""
import signal
import sqlite3
import time

from .rig import SubprocessApp, wait_for

POWER = "main/Heat_Power_Production"


def stored_samples(tmp_path, topic):
    conn = sqlite3.connect(f"file:{tmp_path / 'data' / 'heishamon.db'}?mode=ro", uri=True)
    try:
        return conn.execute("SELECT s.ts, s.num FROM samples s JOIN topics t ON t.id = s.topic_id "
                            "WHERE t.key = ? ORDER BY s.ts", (topic,)).fetchall()
    finally:
        conn.close()


def wait_value(app, topic, value):
    def seen():
        topics = app.get("/api/state").json()["topics"]
        return topics.get(topic, {}).get("value") == value

    wait_for(seen, 10, step=0.1, what=f"{topic}={value} in the app state")


def test_sigterm_flushes_and_data_survives_a_restart(broker, subprocess_app, tmp_path):
    first = subprocess_app().start()
    wait_for(lambda: first.get("/api/system").json()["broker_connected"], 10, step=0.1, what="broker connection")
    assert first.get("/api/system").json()["last_flush_ts"] is None  # nothing has been flushed yet

    broker.live = True
    broker.publish("LWT", "Online")
    broker.publish(POWER, "1000")
    broker.drain()
    wait_value(first, POWER, 1000)
    time.sleep(1.1)
    broker.publish(POWER, "2000")
    broker.drain()
    wait_value(first, POWER, 2000)
    assert stored_samples(tmp_path, POWER) == []  # still only in RAM before the shutdown flush

    code, seconds = first.terminate()
    assert seconds < 60, f"shutdown took {seconds:.1f} s"
    assert code in (0, -signal.SIGTERM), (code, first.log.read_text()[-2000:])

    rows = stored_samples(tmp_path, POWER)
    assert [value for _ts, value in rows] == [1000.0, 2000.0]

    second = subprocess_app().start()  # a fresh port, same DATA_DIR
    try:
        now = int(time.time() * 1000)
        body = second.get("/api/history", topics=POWER, **{"from": now - 3_600_000, "to": now + 60_000,
                                                          "max_points": 1000}).json()
        assert [p[1] for p in body["series"][POWER]["points"]] == [1000, 2000]
        kinds = [e["kind"] for e in second.get("/api/events", limit=50).json()["events"]]
        assert "flush" in kinds
    finally:
        code, seconds = second.terminate()
    assert seconds < 60 and code in (0, -signal.SIGTERM)
