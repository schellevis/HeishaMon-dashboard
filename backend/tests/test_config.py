import pytest

from heishamon_dashboard.config import ConfigError, load

BASE = {"MQTT_HOST": "mqtt.example.invalid"}


def env(**kw):
    return {**BASE, **kw}


def test_defaults():
    c = load(BASE)
    assert c.mqtt_host == "mqtt.example.invalid"
    assert c.mqtt_port == 1883
    assert c.mqtt_user is None and c.mqtt_password is None
    assert c.mqtt_tls is False
    assert c.mqtt_base_topic == "panasonic_heat_pump"
    assert c.data_dir == "/data"
    assert c.flush_interval_seconds == 900
    assert c.buffer_max_entries == 200000
    assert c.buffer_max_bytes == 268435456
    assert c.audit_buffer_max == 10000
    assert c.raw_retention_days is None
    assert c.http_port == 8000
    assert c.tz == "UTC"
    assert c.public_origins == () and c.allowed_origins == ()
    assert (c.command_rate_max, c.command_rate_window_s) == (6, 3600)


def test_command_rate_values_parsed():
    c = load(env(COMMAND_RATE_MAX="3", COMMAND_RATE_WINDOW_S="600"))
    assert (c.command_rate_max, c.command_rate_window_s) == (3, 600)


def test_host_required():
    with pytest.raises(ConfigError, match="MQTT_HOST"):
        load({})
    with pytest.raises(ConfigError, match="MQTT_HOST"):
        load({"MQTT_HOST": "  "})


def test_host_invalid():
    with pytest.raises(ConfigError, match="MQTT_HOST"):
        load({"MQTT_HOST": "bad host!"})


@pytest.mark.parametrize("name,good,bad", [
    ("MQTT_PORT", ["1", "65535"], ["0", "65536", "x"]),
    ("HTTP_PORT", ["1", "65535"], ["0", "65536", "x"]),
    ("FLUSH_INTERVAL_SECONDS", ["10", "86400"], ["9", "86401"]),
    ("BUFFER_MAX_ENTRIES", ["1000", "5000000"], ["999"]),
    ("BUFFER_MAX_BYTES", ["16777216"], ["1000", "16777215"]),
    ("AUDIT_BUFFER_MAX", ["100", "100000"], ["99", "100001"]),
    ("RAW_RETENTION_DAYS", ["1", "365"], ["0", "-1", "x"]),
    ("COMMAND_RATE_MAX", ["1", "100"], ["0", "-1", "x"]),
    ("COMMAND_RATE_WINDOW_S", ["1", "86400"], ["0", "-1", "x"]),
])
def test_int_bounds(name, good, bad):
    for v in good:
        load(env(**{name: v}))
    for v in bad:
        with pytest.raises(ConfigError, match=name):
            load(env(**{name: v}))


def test_int_values_parsed():
    c = load(env(MQTT_PORT="8883", FLUSH_INTERVAL_SECONDS="60", AUDIT_BUFFER_MAX="500", RAW_RETENTION_DAYS="30"))
    assert (c.mqtt_port, c.flush_interval_seconds, c.audit_buffer_max, c.raw_retention_days) == (8883, 60, 500, 30)


def test_retention_empty_means_forever():
    assert load(env(RAW_RETENTION_DAYS="")).raw_retention_days is None


@pytest.mark.parametrize("v,expected", [
    ("1", True), ("true", True), ("TRUE", True), ("Yes", True),
    ("0", False), ("no", False), ("on", False), ("", False),
])
def test_tls(v, expected):
    assert load(env(MQTT_TLS=v)).mqtt_tls is expected


def test_user_password():
    c = load(env(MQTT_USER="u", MQTT_PASSWORD="p"))
    assert (c.mqtt_user, c.mqtt_password) == ("u", "p")


@pytest.mark.parametrize("topic", ["a/+/b", "#", "/x", "x/", "$SYS", "a//b", "a" * 129, "a\x00b", "a/#"])
def test_base_topic_rejected(topic):
    with pytest.raises(ConfigError, match="MQTT_BASE_TOPIC"):
        load(env(MQTT_BASE_TOPIC=topic))


@pytest.mark.parametrize("topic", ["x", "a/b", "a" * 128, "heat/pump_1"])
def test_base_topic_accepted(topic):
    assert load(env(MQTT_BASE_TOPIC=topic)).mqtt_base_topic == topic


def test_base_topic_bytes_not_chars():
    with pytest.raises(ConfigError, match="MQTT_BASE_TOPIC"):
        load(env(MQTT_BASE_TOPIC="é" * 65))


def test_tz():
    assert load(env(TZ="Europe/Amsterdam")).tz == "Europe/Amsterdam"
    with pytest.raises(ConfigError, match="TZ"):
        load(env(TZ="Mars/Olympus"))


def test_data_dir():
    assert load(env(DATA_DIR="/tmp/x")).data_dir == "/tmp/x"


def test_origins():
    c = load(env(PUBLIC_ORIGINS="https://a.example.invalid, http://b.example.invalid:8000,",
                 ALLOWED_ORIGINS="https://c.example.invalid"))
    assert c.public_origins == ("https://a.example.invalid", "http://b.example.invalid:8000")
    assert c.allowed_origins == ("https://c.example.invalid",)


@pytest.mark.parametrize("name", ["PUBLIC_ORIGINS", "ALLOWED_ORIGINS"])
@pytest.mark.parametrize("bad", ["example.invalid", "https://a.example.invalid/path", "*"])
def test_origins_invalid(name, bad):
    with pytest.raises(ConfigError, match=name):
        load(env(**{name: bad}))


def test_mqtt_ca_file(tmp_path):
    assert load(BASE).mqtt_ca_file is None
    assert load(env(MQTT_CA_FILE="  ")).mqtt_ca_file is None
    ca = tmp_path / "ca.pem"
    ca.write_text("pem")
    assert load(env(MQTT_CA_FILE=str(ca), MQTT_TLS="true")).mqtt_ca_file == str(ca)
    with pytest.raises(ConfigError, match="MQTT_CA_FILE"):
        load(env(MQTT_CA_FILE=str(tmp_path / "missing.pem")))
