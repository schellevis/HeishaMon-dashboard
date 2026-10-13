"""Publish allowlist and reconnect backoff, against a fake aiomqtt client."""
import dataclasses
from pathlib import Path

import pytest

from heishamon_dashboard.catalog import load
from heishamon_dashboard.config import Config
from heishamon_dashboard.mqtt import Mqtt, PublishError
from heishamon_dashboard.types import Message

CATALOG = load(Path(__file__).resolve().parents[1] / "heishamon_dashboard" / "catalog.json")
BASE = "panasonic_heat_pump"


def config():
    return Config(
        mqtt_host="mqtt.example.test",
        mqtt_port=1883,
        mqtt_user=None,
        mqtt_password=None,
        mqtt_tls=False,
        mqtt_base_topic=BASE,
        data_dir="/tmp",
        flush_interval_seconds=900,
        buffer_max_entries=200_000,
        buffer_max_bytes=268_435_456,
        audit_buffer_max=10_000,
        raw_retention_days=None,
        http_port=8000,
        tz="UTC",
        public_origins=(),
        allowed_origins=(),
    )


class FakeClient:
    def __init__(self):
        self.calls = []

    async def publish(self, topic, payload=None, qos=0, retain=False, **kwargs):
        self.calls.append({"topic": topic, "payload": payload, "qos": qos, "retain": retain})


def attached():
    client = FakeClient()
    mqtt = Mqtt(config(), CATALOG)
    mqtt.attach(client)
    return mqtt, client


def test_catalog_splits_retained_exceptions_and_inputs():
    retained = [i for i in CATALOG.inputs if i["retain"]]
    plain = [i for i in CATALOG.inputs if not i["retain"]]
    assert {i["path"] for i in retained} == {
        "s0/WatthourTotal/1",
        "s0/WatthourTotal/2",
        "opentherm/read/dhwSetUppBound",
        "opentherm/read/dhwSetLowBound",
        "opentherm/read/chSetUppBound",
        "opentherm/read/chSetLowBound",
    }
    assert retained and plain
    assert all(i["class"] == "retained_exception" for i in retained)
    assert all(i["class"] == "input" for i in plain)


@pytest.mark.parametrize("name", [c["name"] for c in CATALOG.commands])
async def test_every_command_publishes_non_retained_qos0(name):
    mqtt, client = attached()
    await mqtt.publish_command(name, "1")
    assert client.calls == [{
        "topic": f"{BASE}/commands/{name}",
        "payload": "1",
        "qos": 0,
        "retain": False,
    }]
    client.calls.clear()
    with pytest.raises(PublishError):
        await mqtt.publish_retained_exception(f"commands/{name}", "1")
    with pytest.raises(PublishError):
        await mqtt.publish_input(f"commands/{name}", "1")
    with pytest.raises(PublishError):
        await mqtt.publish_input(name, "1")
    with pytest.raises(PublishError):
        await mqtt.publish_retained_exception(name, "1")
    assert client.calls == []


@pytest.mark.parametrize("path", [i["path"] for i in CATALOG.inputs if i["retain"]])
async def test_every_retained_exception_publishes_retained(path):
    mqtt, client = attached()
    await mqtt.publish_retained_exception(path, "10")
    assert client.calls == [{
        "topic": f"{BASE}/{path}",
        "payload": "10",
        "qos": 0,
        "retain": True,
    }]
    client.calls.clear()
    with pytest.raises(PublishError):
        await mqtt.publish_command(path, "10")
    with pytest.raises(PublishError):
        await mqtt.publish_input(path, "10")
    assert client.calls == []


@pytest.mark.parametrize("path", [i["path"] for i in CATALOG.inputs if not i["retain"]])
async def test_every_input_publishes_non_retained(path):
    mqtt, client = attached()
    await mqtt.publish_input(path, "7.5")
    assert client.calls == [{
        "topic": f"{BASE}/{path}",
        "payload": "7.5",
        "qos": 0,
        "retain": False,
    }]
    client.calls.clear()
    with pytest.raises(PublishError):
        await mqtt.publish_command(path, "7.5")
    with pytest.raises(PublishError):
        await mqtt.publish_retained_exception(path, "7.5")
    assert client.calls == []


async def test_unknown_topics_rejected_on_every_path():
    mqtt, client = attached()
    for topic in ("s0/Watt/1", "main/Outside_Temp", "opentherm/write/roomTemp", "not-a-command"):
        with pytest.raises(PublishError):
            await mqtt.publish_command(topic, "1")
        with pytest.raises(PublishError):
            await mqtt.publish_retained_exception(topic, "1")
        with pytest.raises(PublishError):
            await mqtt.publish_input(topic, "1")
    assert client.calls == []


async def test_publish_rejected_while_disconnected():
    client = FakeClient()
    mqtt = Mqtt(config(), CATALOG)
    mqtt.attach(client)
    mqtt.connected = False
    with pytest.raises(PublishError, match="disconnected"):
        await mqtt.publish_command("SetDHWTemp", "45")
    assert client.calls == []


class _Messages:
    def __init__(self, items):
        self.items = items

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for item in self.items:
            yield item


class Raw:
    def __init__(self, topic, payload, retain):
        self.topic = topic
        self.payload = payload
        self.retain = retain


class FlakyFactory:
    """Async context manager factory: the first `failures` entries raise."""

    def __init__(self, failures, items):
        self.failures = failures
        self._items = items
        self.attempts = 0
        self.subscribed = []

    def __call__(self):
        return self

    async def __aenter__(self):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise ConnectionError("broker down")
        return self

    async def __aexit__(self, *exc):
        return False

    async def subscribe(self, topic, **kwargs):
        self.subscribed.append(topic)

    @property
    def messages(self):
        return _Messages(self._items)


def factory(failures, items):
    return FlakyFactory(failures, items)


class Clock:
    def __init__(self, now):
        self.now = now

    def now_ms(self):
        return self.now


async def test_reconnect_backoff_doubles_from_1s_to_60s():
    mqtt = Mqtt(config(), CATALOG, client_factory=factory(8, []))
    delays = []

    async def sleep(seconds):
        delays.append(seconds)
        if len(delays) == 8:
            mqtt.stop()

    mqtt._sleep = sleep
    await mqtt.run()
    assert delays == [1, 2, 4, 8, 16, 32, 60, 60]
    assert mqtt.connected is False


async def test_successful_connect_resets_backoff_and_dispatches():
    raw = Raw(f"{BASE}/main/Outside_Temp", b"21", False)
    other = Raw("other_app/temp", b"1", False)
    fac = factory(2, [raw, other])
    clock = Clock(1_700_000_000_000)
    mqtt = Mqtt(config(), CATALOG, client_factory=fac, clock=clock)
    seen = []
    connects = []
    mqtt.on_message(seen.append)
    mqtt.on_broker_connect(lambda: connects.append("up"))
    mqtt.on_broker_disconnect(lambda: connects.append("down"))
    delays = []

    async def sleep(seconds):
        delays.append(seconds)
        if len(delays) == 3:
            mqtt.stop()

    mqtt._sleep = sleep
    await mqtt.run()
    assert delays == [1, 2, 1]
    assert fac.subscribed == [f"{BASE}/#"]
    assert seen == [Message("main/Outside_Temp", "21", False, 1_700_000_000_000)]
    assert connects == ["up", "down"]
    assert mqtt.connected is False


async def test_publish_translates_mqtt_error():
    import aiomqtt

    class Broken(FakeClient):
        async def publish(self, *a, **k):
            raise aiomqtt.MqttError("connection lost")

    mqtt = Mqtt(config(), CATALOG)
    mqtt.attach(Broken())
    with pytest.raises(PublishError):
        await mqtt.publish_command("SetDHWTemp", "50")


def test_default_factory_passes_the_ca_file(monkeypatch):
    import aiomqtt

    from heishamon_dashboard.mqtt import Mqtt

    seen = {}
    monkeypatch.setattr(aiomqtt, "TLSParameters", lambda **kw: seen.update(kw) or "tls")
    monkeypatch.setattr(aiomqtt, "Client", lambda host, **kw: seen.update(client=kw))
    cfg = dataclasses.replace(config(), mqtt_tls=True, mqtt_ca_file="/etc/ca.pem")
    Mqtt(cfg, CATALOG)._default_factory()
    assert seen["ca_certs"] == "/etc/ca.pem" and seen["client"]["tls_params"] == "tls"
