"""T07: energy over spec §5.4 timelines T2/T3, event detection."""
from datetime import datetime, timezone

import pytest

from heishamon_dashboard.derived import EventDetector, energy, energy_joules
from heishamon_dashboard.store import Store
from heishamon_dashboard.types import Liveness, Receipt, TopicValue

PROD = "main/Heat_Power_Production"
CONS = "main/Heat_Power_Consumption"
XPROD = "extra/Heat_Power_Production_Extra"
XCONS = "extra/Heat_Power_Consumption_Extra"
DAY0 = int(datetime(2026, 10, 11, tzinfo=timezone.utc).timestamp() * 1000)


def t(hms):
    h, m, s = (int(x) for x in hms.split(":"))
    return DAY0 + ((h * 60 + m) * 60 + s) * 1000


def tv(key, value, valid=True):
    return TopicValue(key, value, str(value), "number", valid, 0, 0, False)


def rcpt(topic, value, ts, retained=False, valid=True):
    return Receipt(topic, str(value), value, valid, retained, ts, False, True)


def live(ts):
    return Receipt("LWT", "Online", "Online", True, False, ts, True, False)


EXTRA = {"has_extra": {"value": True, "unknown": False}}
NO_EXTRA = {"has_extra": {"value": False, "unknown": False}}


# --- energy ------------------------------------------------------------------

def test_energy_t2_one_kwh(tmp_path):
    s = Store(tmp_path / "a.db")
    s.observe(rcpt(PROD, 500, t("01:00:00")))
    s.observe(live(t("03:00:00")))
    assert s.flush(t("03:00:00"), Liveness("online", t("03:00:00"), None)).ok
    r = energy(s, t("01:00:00"), t("03:00:00"), "day", t("03:00:00"), NO_EXTRA)
    assert r["estimate"] is True
    assert r["periods"]["2026-10-11"]["heat"]["production_kwh"] == pytest.approx(1.0)
    assert "cool" not in r["periods"]["2026-10-11"]


def test_energy_t3_190000_joules(tmp_path):
    s = Store(tmp_path / "b.db")
    s.observe(rcpt(PROD, 1000, t("04:00:00")))
    s.observe(live(t("04:02:10")))
    s.open_outage("offline", t("04:02:10"))
    s.observe(live(t("04:04:00")))
    lv = Liveness("online", t("04:04:55"), None)
    assert s.flush(t("04:05:00"), lv).ok
    j = energy_joules(s, t("04:00:00"), t("04:05:00"), "day", t("04:05:00"), NO_EXTRA, lv)
    assert j["2026-10-11"]["heat"]["production_j"] == pytest.approx(190_000)
    kwh = energy(s, t("04:00:00"), t("04:05:00"), "day", t("04:05:00"), NO_EXTRA, lv)
    assert kwh["periods"]["2026-10-11"]["heat"]["production_kwh"] == pytest.approx(190_000 / 3_600_000)


def test_energy_uses_extra_topics_and_periods(tmp_path):
    s = Store(tmp_path / "c.db")
    s.observe(rcpt(XCONS, 600, t("00:00:00")))
    s.observe(live(t("02:00:00")))
    lv = Liveness("online", t("02:00:00"), None)
    assert s.flush(t("02:00:00"), lv).ok
    r = energy(s, t("00:00:00"), t("02:00:00"), "month", t("02:00:00"), EXTRA, lv)
    assert r["estimate"] is False
    assert r["periods"]["2026-10"]["heat"]["consumption_kwh"] == pytest.approx(1.2)
    with pytest.raises(ValueError):
        energy(s, 0, 1, "week", 1)


def test_energy_long_range_uses_hour_rollups(tmp_path):
    s = Store(tmp_path / "d.db")
    s.observe(rcpt(PROD, 500, t("01:00:00")))
    s.observe(live(t("03:00:00")))
    lv = Liveness("online", t("03:00:00"), None)
    assert s.flush(t("03:00:00"), lv).ok
    r = energy(s, t("00:00:00") - 20 * 86_400_000, t("03:00:00"), "year", t("03:00:00"), NO_EXTRA, lv)
    assert r["periods"]["2026"]["heat"]["production_kwh"] == pytest.approx(1.0)


# --- events ------------------------------------------------------------------

@pytest.fixture
def ev():
    log = []
    return EventDetector(lambda ts, kind, detail=None: log.append((ts, kind, detail))), log


def test_defrost_start_end_once(ev):
    d, log = ev
    d.on_receipt(rcpt("main/Defrosting_State", 0, 1))
    d.on_receipt(rcpt("main/Defrosting_State", 1, 2))
    d.on_receipt(rcpt("main/Defrosting_State", 1, 3))  # repeat: no event
    d.on_receipt(rcpt("main/Defrosting_State", 0, 4))
    d.on_receipt(rcpt("main/Defrosting_State", 0, 5))
    assert [(a, b) for a, b, _ in log] == [(2, "defrost_start"), (4, "defrost_end")]


def test_baseline_and_retained_are_silent(ev):
    d, log = ev
    d.on_receipt(rcpt("main/Operating_Mode_State", 0, 1, retained=True))
    d.on_receipt(rcpt("main/Operating_Mode_State", 4, 2, retained=True))
    d.on_receipt(rcpt("main/Error", "H00", 3))
    assert log == []


def test_error_mode_valve_changes(ev):
    d, log = ev
    for topic, a, b, kind in (("main/Error", "H00", "H12", "error_change"),
                              ("main/Operating_Mode_State", 0, 4, "mode_change"),
                              ("main/ThreeWay_Valve_State", 0, 1, "valve_change")):
        d.on_receipt(rcpt(topic, a, 1))
        d.on_receipt(rcpt(topic, b, 2))
        d.on_receipt(rcpt(topic, b, 3))
        assert log[-1] == (2, kind, {"from": a, "to": b})
    assert len(log) == 3


def test_invalid_values_ignored(ev):
    d, log = ev
    d.on_receipt(rcpt("main/ThreeWay_Valve_State", 0, 1))
    d.on_receipt(rcpt("main/ThreeWay_Valve_State", -1, 2, valid=False))
    d.on_receipt(rcpt("main/ThreeWay_Valve_State", 0, 3))
    assert log == []


def test_device_and_broker_transitions_once(ev):
    d, log = ev
    d.on_device_online(1)          # first online: baseline
    d.on_device_online(2)
    d.on_device_offline(3)
    d.on_device_offline(4)
    d.on_device_online(5)
    d.on_broker_disconnected(6)    # never connected: nothing
    d.on_broker_connected(7)
    d.on_broker_connected(8)
    d.on_broker_disconnected(9)
    d.on_broker_disconnected(10)
    assert [(a, b) for a, b, _ in log] == [
        (3, "device_offline"), (5, "device_online"), (7, "broker_connected"), (9, "broker_disconnected")]


def test_events_reach_store(tmp_path):
    s = Store(tmp_path / "e.db")
    d = EventDetector(s.append_event)
    d.on_receipt(rcpt("main/Defrosting_State", 0, 1))
    d.on_receipt(rcpt("main/Defrosting_State", 1, 2))
    assert [e["kind"] for e in s.events_list()] == ["defrost_start"]
