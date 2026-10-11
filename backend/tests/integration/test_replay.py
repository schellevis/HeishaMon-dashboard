"""Replay fixtures through the embedded broker into the app (spec §10), plus the A12 privacy checks."""
import contextlib
import json
import re

import pytest

from . import replay
from .rig import FIXTURES, FakeClock, hms

START = hms(10)
FIXTURE_FILES = sorted(FIXTURES.glob("replay_*.json"))


def expected_rows(document):
    """Stored samples per topic: one per change in the topic's value sequence (seed snapshot first)."""
    ordered = [m for m in document["messages"] if replay.is_seed(m)] + \
              [m for m in document["messages"] if not replay.is_seed(m)]
    last, rows = {}, {}
    for message in ordered:
        topic = message["topic"]
        if last.get(topic) != message["payload"]:
            rows[topic] = rows.get(topic, 0) + 1
            last[topic] = message["payload"]
    return rows


@contextlib.contextmanager
def run_replay(broker, make_app, document):
    replay.seed(broker, document)
    app = make_app(clock=FakeClock(START - 1000))
    with app:
        end = replay.play(app, document, start=START)
        app.tick(at=end)
        app.flush(at=end + 1000)
        topics = app.state()["topics"]
        with app.db() as conn:
            rows = dict(conn.execute("SELECT t.key, COUNT(*) FROM samples s JOIN topics t ON t.id = s.topic_id "
                                     "GROUP BY t.key").fetchall())
        yield app, topics, rows, app.system(), app.client.get("/api/profile").json()


def test_synthetic_fixture_is_current_and_labelled():
    document = replay.load(replay.SYNTHETIC)
    assert document == replay.generate_synthetic()
    assert document["synthetic"] is True and "synthetic" in document["note"]
    assert len(document["messages"]) > 300


def test_synthetic_replay_end_to_end(broker, make_app):
    document = replay.load(replay.SYNTHETIC)
    with run_replay(broker, make_app, document) as (app, topics, rows, system, profile):
        sent = {m["topic"] for m in document["messages"]}
        assert sent <= set(topics)  # everything published is visible
        assert system["device_online"] == "online" and system["last_flush_ok"] is True
        assert system["firmware"] == "v4.2.3"
        assert profile["operating_mode"]["value"] == 4  # the heat_dhw preset
        # only real changes are stored: constant topics have one row despite the 300 s full re-publish
        assert rows == expected_rows(document)
        assert rows["main/Heat_Power_Production"] == 1
        assert rows["main/DHW_Target_Temp"] == 4  # preset default, then 50 → 52 → 50
        history = app.client.get("/api/history", params={
            "topics": "main/DHW_Target_Temp", "from": START, "to": START + 330_000, "max_points": 100}).json()
        assert [p[1] for p in history["series"]["main/DHW_Target_Temp"]["points"]][-3:] == [50, 52, 50]


@pytest.mark.skipif(not replay.REAL.exists(), reason="real capture pending (decision-006); run tools/capture.py")
def test_real_capture_replay(broker, make_app):
    document = replay.load(replay.REAL)
    with run_replay(broker, make_app, document) as (_app, topics, rows, system, _profile):
        assert {m["topic"] for m in document["messages"]} <= set(topics)
        assert system["last_flush_ok"] is True
        assert "ip" not in topics
        assert rows and sum(rows.values()) <= len(document["messages"])


# ---------------------------------------------------------------- A12: privacy of every fixture

IPV4 = re.compile(r"(?<![\d.])\d{1,3}(?:\.\d{1,3}){3}(?![\d.])")
MAC = re.compile(r"\b[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}\b")
EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
ONE_WIRE_ADDRESS = re.compile(r"\b[0-9A-Fa-f]{16}\b")
ALLOWED = ("main/", "extra/", "optional/", "1wire/", "s0/", "opentherm/")


def test_there_is_at_least_the_synthetic_fixture():
    assert replay.SYNTHETIC in FIXTURE_FILES


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: p.name)
def test_replay_fixtures_carry_no_identifying_data(path):
    document = replay.load(path)
    assert document["format"] == "heishamon-replay/1"
    assert isinstance(document["synthetic"], bool)
    for message in document["messages"]:
        topic, payload = message["topic"], message["payload"]
        assert topic != "ip" and not topic.startswith(("ip/", "log")), topic
        assert topic in ("stats", "LWT") or topic.startswith(ALLOWED), topic
        assert not (IPV4.search(payload) or MAC.search(payload) or EMAIL.search(payload)), (topic, payload)
        assert not ONE_WIRE_ADDRESS.search(topic), topic
        if topic == "stats":
            assert set(json.loads(payload)) <= {"version"}, payload
        if topic.startswith("1wire/"):
            assert topic.split("/")[1].startswith("pseudo-"), topic
    text = json.dumps(document)
    assert "panasonic_heat_pump" not in text  # the base topic is not recorded either
