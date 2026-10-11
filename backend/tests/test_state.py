"""Live state: §4.1 rule list, A8, change detection, ingest limits (fake clock)."""
from pathlib import Path

from heishamon_dashboard.catalog import load
from heishamon_dashboard.state import (
    PAYLOAD_MAX_BYTES,
    PRESENCE_HOLD_MS,
    TOPIC_MAX_BYTES,
    State,
)
from heishamon_dashboard.types import Message

CATALOG = load(Path(__file__).resolve().parents[1] / "heishamon_dashboard" / "catalog.json")


def msg(topic, payload, retained, ts):
    return Message(topic=topic, payload=payload, retained=retained, ts=ts)


def test_heartbeat_only_keeps_online_for_10_minutes():
    st = State(CATALOG)
    # Default waitTime is 5 s. Heartbeats alone, no value topics, for 10 minutes.
    for t in range(0, 600_000 + 1, 5_000):
        receipt = st.ingest(msg("LWT", "Online", False, t))
        assert receipt.qualifying is True
        assert st.device_online == "online"
        assert st.liveness().last_qualifying_ts == t
        assert st.liveness().offline_since is None
    assert "main/Outside_Temp" not in st.values
    # Floor timeout is 30 s (3 × 5 s median is below the floor).
    assert st.liveness_timeout_ms == 30_000
    st.tick(600_000 + 29_999)
    assert st.device_online == "online"
    st.tick(600_000 + 30_000)
    assert st.device_online == "offline"
    assert st.liveness().offline_since == 600_000


def test_retained_snapshot_never_makes_unknown_online():
    st = State(CATALOG)
    receipt = st.ingest(msg("main/Outside_Temp", "5", True, 1_000))
    assert st.device_online == "unknown"
    assert receipt.qualifying is False
    assert receipt.retained is True
    assert st.values["main/Outside_Temp"].retained_only is True
    st.ingest(msg("main/DHW_Temp", "40", True, 1_001))
    st.ingest(msg("LWT", "Offline", True, 1_002))  # broker will, retained
    st.tick(1_002 + 3600_000)
    assert st.device_online == "unknown"
    assert st.liveness().last_qualifying_ts is None


def test_echoes_never_make_offline_online():
    st = State(CATALOG)
    st.ingest(msg("LWT", "Online", False, 1_000))
    st.ingest(msg("LWT", "Offline", False, 2_000))
    assert st.device_online == "offline"
    for topic, payload in (
        ("commands/SetDHWTemp", "45"),
        ("s0/WatthourTotal/1", "10"),
        ("opentherm/read/outsideTemp", "7.5"),
    ):
        receipt = st.ingest(msg(topic, payload, False, 3_000))
        assert receipt.qualifying is False
        assert st.device_online == "offline"
        assert st.liveness().offline_since == 2_000
        assert st.liveness().last_qualifying_ts == 1_000


def test_live_offline_starts_at_message_ts():
    st = State(CATALOG)
    offs = []
    st.on_offline(offs.append)
    st.ingest(msg("LWT", "Online", False, 1_000))
    st.ingest(msg("LWT", "Offline", False, 4_000))
    assert st.device_online == "offline"
    assert st.liveness().offline_since == 4_000
    assert offs == [4_000]
    # A second Offline does not start a new outage.
    st.ingest(msg("LWT", "Offline", False, 5_000))
    assert offs == [4_000]
    assert st.liveness().offline_since == 4_000


def test_timeout_backdated_to_last_qualifying_message():
    st = State(CATALOG)
    offs = []
    st.on_offline(offs.append)
    # One qualifying message and no heartbeat samples → 30 s floor.
    receipt = st.ingest(msg("stats", '{"version":"v4.2.3"}', False, 100_000))
    assert receipt.qualifying is True
    assert st.device_online == "online"
    assert st.liveness_timeout_ms == 30_000
    st.tick(129_999)
    assert st.device_online == "online"
    st.tick(130_000)
    assert st.device_online == "offline"
    assert st.liveness().offline_since == 100_000
    assert st.liveness().last_qualifying_ts == 100_000
    assert offs == [100_000]
    st.tick(200_000)
    assert offs == [100_000]


def test_adaptive_timeout_ten_online_messages_20s_apart_is_60s():
    st = State(CATALOG)
    for i in range(10):
        st.ingest(msg("LWT", "Online", False, i * 20_000))
    assert st.liveness_timeout_ms == 60_000
    assert st.heartbeat_intervals == [20_000] * 9
    last = 9 * 20_000
    st.tick(last + 30_000)  # the 30 s floor would already have fired
    assert st.device_online == "online"
    st.tick(last + 59_999)
    assert st.device_online == "online"
    st.tick(last + 60_000)
    assert st.device_online == "offline"
    assert st.liveness().offline_since == last


def test_broker_reconnect_stays_unknown_until_qualifying():
    st = State(CATALOG)
    ons = []
    st.on_online(ons.append)
    st.ingest(msg("main/Outside_Temp", "5", False, 1_000))
    assert st.device_online == "online"
    assert ons == [1_000]
    st.broker_reconnect(2_000)
    assert st.device_online == "unknown"
    assert st.liveness().offline_since is None
    st.ingest(msg("main/Outside_Temp", "5", True, 2_100))
    st.ingest(msg("commands/SetDHWTemp", "45", False, 2_200))
    st.tick(2_000 + 3600_000)
    assert st.device_online == "unknown"
    st.ingest(msg("LWT", "Online", False, 2_000 + 3600_000))
    assert st.device_online == "online"
    assert ons == [1_000, 2_000 + 3600_000]


def test_change_detection_sentinel_and_retained_then_live():
    st = State(CATALOG)
    first = st.ingest(msg("main/Outside_Temp", "21", False, 1_000))
    assert first.changed is True
    assert first.valid is True
    assert first.value == 21
    again = st.ingest(msg("main/Outside_Temp", "21", False, 1_500))
    assert again.changed is False
    assert again.valid is True
    stored = st.values["main/Outside_Temp"]
    assert stored.last_seen == 1_500
    assert stored.last_change == 1_000
    assert st.seq == 2

    sentinel = st.ingest(msg("main/Outside_Temp", "-128", False, 1_600))
    assert sentinel.valid is False
    assert sentinel.changed is True
    assert sentinel.value == -128
    assert st.values["main/Outside_Temp"].valid is False

    enum_sentinel = st.ingest(msg("main/Heatpump_State", "-1", False, 1_700))
    assert enum_sentinel.valid is False
    assert enum_sentinel.value == -1

    fresh = State(CATALOG)
    retained = fresh.ingest(msg("main/Outside_Temp", "21", True, 2_000))
    live = fresh.ingest(msg("main/Outside_Temp", "21", False, 2_500))
    assert retained.retained is True and retained.changed is True
    assert live.retained is False and live.changed is False
    assert fresh.values["main/Outside_Temp"].retained_only is False
    assert fresh.values["main/Outside_Temp"].last_change == 2_000
    assert fresh.values["main/Outside_Temp"].last_seen == 2_500


def test_unparseable_payload_is_stored_invalid():
    st = State(CATALOG)
    receipt = st.ingest(msg("main/Outside_Temp", "cold", False, 1_000))
    assert receipt is not None
    assert receipt.valid is False
    assert receipt.value == "cold"
    assert receipt.raw == "cold"
    assert st.values["main/Outside_Temp"].valid is False
    assert st.device_online == "online"  # live main/ still qualifies


def test_ingest_limits_drop_and_count():
    assert TOPIC_MAX_BYTES == 256
    assert PAYLOAD_MAX_BYTES == 64 * 1024
    st = State(CATALOG)
    oversized_topic = "t" * (TOPIC_MAX_BYTES + 1)
    assert st.ingest(msg(oversized_topic, "1", False, 1)) is None
    assert oversized_topic not in st.values
    huge = "x" * (PAYLOAD_MAX_BYTES + 1)
    assert st.ingest(msg("main/Outside_Temp", huge, False, 2)) is None
    assert "main/Outside_Temp" not in st.values
    assert st.ingest_dropped == 2
    assert st.seq == 0
    assert st.device_online == "unknown"

    assert st.ingest(msg("u" * TOPIC_MAX_BYTES, "1", False, 3)) is not None
    assert st.ingest(msg("main/Outside_Temp", "1" * PAYLOAD_MAX_BYTES, False, 4)) is not None
    assert st.ingest_dropped == 2
    assert st.consume_ingest_dropped() == 2
    assert st.ingest_dropped == 0


def test_rule_list_qualifying_prefixes_and_writable_exclusion():
    st = State(CATALOG)
    cases = (
        ("main/Outside_Temp", "1", True),
        ("extra/XTOP0", "1", True),
        ("optional/OPT0", "1", True),
        ("1wire/abc", "20", True),
        ("s0/Watt/1", "10", True),
        ("s0/Watthour/1", "10", True),
        ("opentherm/write/roomTemp", "21", True),
        ("stats", "{}", True),
        ("s0/WatthourTotal/2", "10", False),
        ("log", "hello", False),
        ("ip", "redacted", False),
        ("opentherm/RoomTemp", "19", False),  # pre-3.5 namespace, rule 6
    )
    for topic, payload, qualifying in cases:
        receipt = st.ingest(msg(topic, payload, False, 10_000))
        assert receipt.qualifying is qualifying, topic
    assert st.device_online == "online"


def test_after_offline_only_qualifying_returns_online():
    st = State(CATALOG)
    ons = []
    st.on_online(ons.append)
    st.ingest(msg("LWT", "Offline", False, 1_000))
    assert st.device_online == "offline"
    assert ons == []
    st.ingest(msg("commands/SetDHWTemp", "40", False, 2_000))
    assert st.device_online == "offline"
    st.ingest(msg("s0/Watt/1", "3", False, 3_000))
    assert st.device_online == "online"
    assert ons == [3_000]
    assert st.liveness().offline_since is None
    assert st.liveness().last_qualifying_ts == 3_000


def test_presence_rules_and_last_live_ts():
    st = State(CATALOG)
    assert st.presence() == {
        "extra": False,
        "optional": False,
        "1wire": False,
        "s0": False,
        "opentherm": False,
    }
    st.ingest(msg("extra/XTOP0", "1", True, 1_000))  # retained still counts
    st.ingest(msg("optional/OPT0", "1", True, 1_100))
    st.ingest(msg("1wire/abc", "18", False, 1_200))
    st.ingest(msg("s0/WatthourTotal/1", "5", False, 1_300))
    # Dashboard-writable OpenTherm reads never count as presence.
    st.ingest(msg("opentherm/read/outsideTemp", "7", False, 1_400))
    assert st.presence()["opentherm"] is False
    st.ingest(msg("opentherm/write/outsideTemp", "7", False, 1_500))
    assert st.presence() == {
        "extra": True,
        "optional": True,
        "1wire": True,
        "s0": True,
        "opentherm": True,
    }
    assert st.last_live_ts("optional/") is None  # only a retained optional/ message
    st.ingest(msg("optional/OPT1", "2", False, 1_600))
    assert st.last_live_ts("optional/") == 1_600
    st.ingest(msg("optional/OPT1", "3", False, 1_500))  # older ts does not move it back
    assert st.last_live_ts("optional/") == 1_600
    assert st.last_live_ts("extra/") is None

    st.broker_reconnect(2_000)
    assert st.presence()["extra"] is True
    st.tick(2_000 + PRESENCE_HOLD_MS - 1)
    assert st.presence()["extra"] is True
    st.tick(2_000 + PRESENCE_HOLD_MS)
    assert st.presence() == {
        "extra": False,
        "optional": False,
        "1wire": False,
        "s0": False,
        "opentherm": False,
    }
    assert PRESENCE_HOLD_MS == 360_000

    # A message after reconnect keeps that subtree until the next reconnect ages out.
    renewed = 2_000 + PRESENCE_HOLD_MS + 1_000
    st.ingest(msg("opentherm/legacyRoom", "19", False, renewed))  # pre-3.5 namespace
    assert st.presence()["opentherm"] is True
    assert st.presence()["extra"] is False
    st.tick(renewed + 10_000)
    assert st.presence()["opentherm"] is True
    st.broker_reconnect(renewed + 20_000)
    st.tick(renewed + 20_000 + PRESENCE_HOLD_MS - 1)
    assert st.presence()["opentherm"] is True
    st.tick(renewed + 20_000 + PRESENCE_HOLD_MS)
    assert st.presence()["opentherm"] is False


def test_heartbeat_intervals_keep_last_10():
    st = State(CATALOG)
    for i in range(15):
        st.ingest(msg("LWT", "Online", False, i * 5_000))
    assert st.heartbeat_intervals == [5_000] * 10
    # Retained Online does not extend the interval list or the recency clock.
    st.ingest(msg("LWT", "Online", True, 15 * 5_000))
    assert st.heartbeat_intervals == [5_000] * 10
    assert st.last_qualifying_ts == 14 * 5_000
