"""tools/capture.py drives a fake aiomqtt client: read-only, and everything identifying is removed (A12)."""
import asyncio
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import capture  # noqa: E402

BASE = "hp_test_base"
ADDR_A, ADDR_B = "28aa001122334455", "28bb009988776655"


class FakeClient:
    """Stands in for aiomqtt.Client; any publish is a test failure."""

    def __init__(self, messages, stall=False):
        self._messages = messages
        self._stall = stall
        self.subscribed = []
        self.published = []

    async def subscribe(self, topic):
        self.subscribed.append(topic)

    async def publish(self, *args, **kwargs):
        self.published.append((args, kwargs))
        raise AssertionError("capture must never publish")

    @property
    def messages(self):
        return self._iterate()

    async def _iterate(self):
        for topic, payload, retain in self._messages:
            yield SimpleNamespace(topic=f"{BASE}/{topic}" if not topic.startswith("!") else topic[1:],
                                  payload=payload.encode(), retain=retain)
        if self._stall:
            await asyncio.sleep(3600)  # the duration limit ends the capture


MESSAGES = [
    ("ip", "192.0.2.50", True),
    ("log", "connected to 198.51.100.7", False),
    ("stats", json.dumps({"uptime": 99, "version": "v4.2.3", "heap": 123, "board": "x", "rules": 3}), False),
    ("LWT", "Online", False),
    ("main/Outside_Temp", "7", True),
    ("main/Error", "contact admin@example.org", True),
    (f"1wire/{ADDR_A}", '{"Temperature": 21.5}', True),
    (f"1wire/{ADDR_A}/alias", "Living room radiator", True),
    (f"1wire/{ADDR_B}", '{"Temperature": 40}', True),
    (f"1wire/{ADDR_A}", '{"Temperature": 22}', False),
    ("s0/Watt/1", "120", True),
    ("commands/SetDHWTemp", "50", False),
    ("other_app/sensor", "{}", False),
    ("!other_base/main/Outside_Temp", "1", False),
    ("main/Note", "gateway 203.0.113.1 timeout", False),
    ("main/Mac", "aa:bb:cc:dd:ee:ff", False),
]


def run(messages=MESSAGES, **kw):
    client = FakeClient(messages, **kw)
    ticks = iter(range(10_000))
    document = asyncio.run(capture.capture(client, BASE, 60, clock=lambda: next(ticks) / 10))
    return client, document


def test_never_publishes_and_subscribes_only_under_the_base():
    client, _ = run()
    assert client.published == []
    assert client.subscribed == [f"{BASE}/#"]


def test_source_has_no_publish_call():
    source = (ROOT / "tools" / "capture.py").read_text()
    assert ".publish(" not in source and "retain=True" not in source


def test_ip_log_and_foreign_topics_are_dropped():
    _, document = run()
    topics = [m["topic"] for m in document["messages"]]
    assert "ip" not in topics and "log" not in topics
    assert not any(t.startswith(("commands/", "other_app/")) for t in topics)
    assert document["dropped"] == {"identifying_payload": 3, "ip": 1, "log": 1, "other": 2}
    assert BASE not in json.dumps(document)


def test_stats_is_reduced_to_the_version():
    _, document = run()
    stats = [m for m in document["messages"] if m["topic"] == "stats"]
    assert [json.loads(m["payload"]) for m in stats] == [{"version": "4.2.3"}]


def test_one_wire_addresses_become_stable_pseudonyms():
    _, document = run()
    text = json.dumps(document)
    assert ADDR_A not in text and ADDR_B not in text and "Living room" not in text
    wire = [(m["topic"], m["payload"]) for m in document["messages"] if m["topic"].startswith("1wire/")]
    assert wire == [
        ("1wire/pseudo-01", '{"Temperature": 21.5}'),
        ("1wire/pseudo-01/alias", "pseudo-01"),
        ("1wire/pseudo-02", '{"Temperature": 40}'),
        ("1wire/pseudo-01", '{"Temperature": 22}'),
    ]


def test_identifying_payloads_are_dropped_and_the_rest_kept_in_order():
    _, document = run()
    kept = [(m["topic"], m["retained"]) for m in document["messages"]]
    assert kept[:2] == [("stats", False), ("LWT", False)]
    assert ("main/Outside_Temp", True) in kept and ("s0/Watt/1", True) in kept
    text = json.dumps(document)
    assert not re.search(r"\d+\.\d+\.\d+\.\d+|@|aa:bb", text)
    offsets = [m["t"] for m in document["messages"]]
    assert offsets == sorted(offsets)
    assert document["format"] == capture.FORMAT and document["synthetic"] is False


def test_duration_ends_the_capture():
    document = asyncio.run(capture.capture(FakeClient(MESSAGES[3:5], stall=True), BASE, 0.05))
    assert [m["topic"] for m in document["messages"]] == ["LWT", "main/Outside_Temp"]


def test_write_fixture_refuses_to_overwrite(tmp_path):
    out = tmp_path / "x.json"
    capture.write_fixture({"a": 1}, out)
    with pytest.raises(FileExistsError):
        capture.write_fixture({"a": 2}, out)
    capture.write_fixture({"a": 2}, out, force=True)
    assert json.loads(out.read_text()) == {"a": 2}


def test_main_reports_a_missing_host_without_connecting(capsys, tmp_path):
    assert capture.main(["--out", str(tmp_path / "o.json")], env={}) == 2
    assert "MQTT_HOST" in capsys.readouterr().err
    assert not (tmp_path / "o.json").exists()


def test_client_uses_the_ca_file(monkeypatch):
    import aiomqtt

    seen = {}
    monkeypatch.setattr(aiomqtt, "TLSParameters", lambda **kw: seen.update(kw) or "tls")
    monkeypatch.setattr(aiomqtt, "Client", lambda host, **kw: seen.update(client=kw))
    config = SimpleNamespace(mqtt_user=None, mqtt_password=None, mqtt_tls=True, mqtt_ca_file="/etc/ca.pem",
                             mqtt_host="h", mqtt_port=8883)
    capture._client(config)
    assert seen["ca_certs"] == "/etc/ca.pem" and seen["client"]["tls_params"] == "tls"


def _clean(topic, payload):
    return capture.Sanitizer().clean(topic, payload)


def _stats(**fields):
    return json.dumps(fields)


@pytest.mark.parametrize("raw,kept", [
    ("v4.2.3", "4.2.3"), ("4.2.3", "4.2.3"), ("3.5", "3.5"), ("3.2.4-beta-2", "3.2.4-beta-2"),
    ("v3.2.4-beta-2", "3.2.4-beta-2"),
])
def test_version_forms(raw, kept):
    topic, payload = _clean("stats", _stats(version=raw, uptime=5))
    assert json.loads(payload) == {"version": kept}


@pytest.mark.parametrize("raw", ["Local build", "Alpha-1a2b3c4d", "Nightly-abcdef0", "v4.2.3-deadbeef01"])
def test_version_dropped_forms(raw):
    topic, payload = _clean("stats", _stats(version=raw))
    assert json.loads(payload) == {}


def test_ipv6_message_dropped():
    sanitizer = capture.Sanitizer()
    assert sanitizer.clean("main/Note", "via 2001:db8::1 ok") is None
    assert sanitizer.clean("main/Note", "fe80::1ff:fe23:4567:890a") is None
    assert sanitizer.dropped == {"identifying_payload": 2}


def test_hostname_message_dropped():
    assert _clean("main/Note", "connected to broker.example.org") is None
    assert _clean("main/Note", "host my-pump.local.nl") is None
    assert _clean("main/Note", "plain text") == ("main/Note", "plain text")


def test_numeric_not_matched():
    for value in ("21.5", "-3.25", "1.2.3", "0", "123456"):
        assert _clean("main/Outside_Temp", value) == ("main/Outside_Temp", value)


def test_stats_checked_after_reduction():
    sanitizer = capture.Sanitizer()
    # identifying data outside the version never leaves; the reduced document is checked as well
    assert sanitizer.clean("stats", _stats(version="v4.2.3", ip="192.0.2.5", host="a.example.org")) == (
        "stats", '{"version":"4.2.3"}')
    # a non-version string is removed from the reduced document, never passed through
    assert sanitizer.clean("stats", _stats(version="host.example.org")) == ("stats", "{}")
    assert sanitizer.dropped == {}
