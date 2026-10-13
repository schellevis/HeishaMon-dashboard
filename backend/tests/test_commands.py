import copy
import json
from pathlib import Path

import pytest

from heishamon_dashboard import catalog as catalog_mod
from heishamon_dashboard.commands import CommandService, values_match
from heishamon_dashboard.firmware import parse_firmware
from heishamon_dashboard.mqtt import PublishError
from heishamon_dashboard.state import State
from heishamon_dashboard.store import StorageUnavailable, Store
from heishamon_dashboard.types import Message

T0 = 1_791_000_000_000
CATALOG_PATH = Path(__file__).parent.parent / "heishamon_dashboard" / "catalog.json"
RAW = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
CAT = catalog_mod.parse(RAW)

DHW = "main/DHW_Target_Temp"
Z1_HEAT_REQ = "main/Z1_Heat_Request_Temp"
OUTSIDE = "main/Outside_Temp"
CURVE = "main/Z1_Heat_Curve_Target_High_Temp"


def F(v, unknown=False, stale=False):
    return {"value": v, "unknown": unknown, "stale": stale}


def make_profile(**over):
    p = {
        "operating_mode": F(0), "heating_control": F("curve"), "cooling_control": F("curve"),
        "zone": {"z1": {"active": F(True), "sensor": F("water")},
                 "z2": {"active": F(True), "sensor": F("water")}},
        "buffer_installed": F(True), "bivalent": F(True),
        "dhw_installed": F(True), "pcb_emulation_active": F(False),
        "firmware": F("4.2.3"), "firmware_assumed": False,
    }
    p.update(over)
    return p


class FakeClock:
    def __init__(self):
        self.t = T0

    def now_ms(self):
        return self.t


class Handle:
    def __init__(self, due, cb):
        self.due, self.cb, self.cancelled = due, cb, False

    def cancel(self):
        self.cancelled = True


class FakeScheduler:
    def __init__(self, clock):
        self.clock, self.items = clock, []

    def call_later(self, delay_s, cb):
        h = Handle(self.clock.t + round(delay_s * 1000), cb)
        self.items.append(h)
        return h

    async def advance(self, seconds):
        target = self.clock.t + round(seconds * 1000)
        while True:
            due = sorted((h for h in self.items if not h.cancelled and h.due <= target), key=lambda h: h.due)
            if not due:
                break
            h = due[0]
            h.cancelled = True
            self.clock.t = max(self.clock.t, h.due)
            await h.cb()
        self.clock.t = target


class FakeMqtt:
    def __init__(self):
        self.connected = True
        self.published = []  # (route, name, payload)
        self.fail = False

    async def _pub(self, route, name, payload):
        if self.fail:
            raise PublishError("broker disconnected")
        self.published.append((route, name, payload))

    async def publish_command(self, name, payload):
        await self._pub("command", name, payload)

    async def publish_retained_exception(self, path, payload):
        await self._pub("retained", path, payload)

    async def publish_input(self, path, payload):
        await self._pub("input", path, payload)


class Rig:
    def __init__(self, tmp_path, catalog=CAT, profile=None):
        self.clock = FakeClock()
        self.sched = FakeScheduler(self.clock)
        self.mqtt = FakeMqtt()
        self.state = State(catalog)
        self.store = Store(str(tmp_path / "t.db"))
        self.profile = profile or make_profile()
        self.statuses = []
        self.listen = []
        self.svc = CommandService(
            catalog, self.mqtt, self.state, self.store, self.clock, self.sched, lambda: self.profile,
            on_status=lambda rec: self.statuses.append((rec["name"], rec["status"])),
            on_listen_only=self.listen.append,
        )
        self.feed("LWT", "Online")
        self.feed(DHW, "45")

    def feed(self, topic, payload, retained=False):
        r = self.state.ingest(Message(topic, payload, retained, self.clock.now_ms()))
        self.svc.on_receipt(r)
        return r

    def rec(self, body):
        return self.store.get_command(body["id"])

    async def go(self, name, value, confirm=False):
        return await self.svc.submit(name, value, confirm)

    def events(self, kind):
        return self.store.events_list(kinds=[kind])


@pytest.fixture
def rig(tmp_path):
    r = Rig(tmp_path)
    yield r
    r.store.close()


def mutated(fn):
    raw = copy.deepcopy(RAW)
    fn(raw)
    return catalog_mod.parse(raw)


def cmd_of(raw, name):
    return next(c for c in raw["commands"] if c["name"] == name)


# ------------------------------------------------------------------ error codes


async def test_unknown_command(rig):
    st, body = await rig.go("SetNothing", 1)
    assert (st, body["error"]) == (422, "unknown_command")
    assert rig.events("command_rejected")[0]["detail"] == {"name": "SetNothing", "error": "unknown_command"}
    assert rig.store.list_commands() == []  # a rejection creates no record


@pytest.mark.parametrize("name,value,code", [
    ("SetDHWTemp", 2.0, "bad_type"),
    ("SetDHWTemp", True, "bad_type"),
    ("SetDHWTemp", "50", "bad_type"),
    ("SetDHWTemp", 39, "out_of_range"),
    ("SetDHWTemp", 76, "out_of_range"),
    ("SetSterilizationMaxTime", 7, "bad_step"),
    ("SetHeatpump", 2, "not_allowed_value"),
    ("SetForceDefrost", 0, "not_allowed_value"),
    ("SetCurves", [1], "bad_type"),
    ("SetCurves", {}, "bad_type"),
    ("SetCurves", {"zone3": {}}, "bad_type"),
    ("SetCurves", {"zone1": {"heat": {"target": {"high": 40.0}}}}, "bad_type"),
    ("s0/WatthourTotal/1", -1, "out_of_range"),
    ("s0/WatthourTotal/1", 1.2345, "bad_type"),
    ("opentherm/read/outsideTemp", 7.25, "bad_type"),
    ("opentherm/read/outsideTemp", 7.3, "bad_step"),
])
async def test_validation_codes(rig, name, value, code):
    st, body = await rig.go(name, value, confirm=True)
    assert (st, body["error"]) == (422, code)


async def test_write_lock_and_pcb_and_firmware_codes(rig):
    rig.store.prefs_put({"write_lock": True})
    assert (await rig.go("SetDHWTemp", 50))[1]["error"] == "write_lock"
    rig.store.prefs_put({"write_lock": False})
    assert (await rig.go("SetPoolTemp", 20.5, True))[1]["error"] == "pcb_disabled"
    rig.store.prefs_put({"pcb_enabled": True})
    assert (await rig.go("SetPoolTemp", 20.5, True))[1]["error"] == "pcb_emulation_inactive"
    rig.profile["pcb_emulation_active"] = F(True)
    assert (await rig.go("SetPoolTemp", 20.5, True))[0] == 201
    rig.profile["firmware"] = F("3.9")
    st, body = await rig.go("SetHeatingControl", 1)
    assert (st, body["error"]) == (422, "firmware_too_old")
    assert body["detail"]["min_firmware"] == "4.0"


async def test_broker_and_device_offline_codes(rig):
    rig.mqtt.connected = False
    st, body = await rig.go("SetDHWTemp", 50)
    assert (st, body["error"]) == (503, "broker_disconnected")
    rig.mqtt.connected = True
    rig.state.device_online = "offline"
    st, body = await rig.go("SetDHWTemp", 50)
    assert (st, body["error"]) == (422, "device_offline")
    rig.state.device_online = "unknown"
    assert (await rig.go("SetDHWTemp", 50))[1]["error"] == "device_offline"


async def test_read_only_and_confirm_codes(rig):
    for mode in (7, 8):
        st, body = await rig.go("SetOperationMode", mode)
        assert (st, body["error"]) == (422, "read_only_value")
    assert (await rig.go("SetOperationMode", 9))[1]["error"] == "out_of_range"
    st, body = await rig.go("SetOperationMode", 6)
    assert st == 201 and body["payload"] == "6"
    for name, value in (("SetHeatpump", 0), ("SetForceDefrost", 1), ("SetReset", 1),
                        ("s0/WatthourTotal/1", 100), ("opentherm/read/dhwSetUppBound", 60)):
        st, body = await rig.go(name, value)
        assert (st, body["error"]) == (422, "confirm_required"), name
    assert (await rig.go("SetHeatpump", 1))[0] == 201  # turning on is not risky


async def test_storage_unavailable_gate_and_append(rig, monkeypatch):
    monkeypatch.setattr(rig.store, "protected_budget_ok", lambda: False)
    st, body = await rig.go("SetDHWTemp", 50)
    assert (st, body["error"]) == (503, "storage_unavailable")
    monkeypatch.undo()
    from heishamon_dashboard.store import StorageUnavailable

    def boom(rec):
        raise StorageUnavailable("full")
    monkeypatch.setattr(rig.store, "append_command", boom)
    st, body = await rig.go("SetDHWTemp", 50)
    assert (st, body["error"]) == (503, "storage_unavailable")
    assert rig.mqtt.published == []


async def test_profile_unknown_from_applicability(tmp_path):
    cat = mutated(lambda raw: cmd_of(raw, "SetDHWTemp").update(applicability={"requires": ["profile.dhw_installed"]}))
    rig = Rig(tmp_path, cat)
    rig.profile["dhw_installed"] = F(None, unknown=True)
    st, body = await rig.go("SetDHWTemp", 50)
    assert (st, body["error"], body["detail"]) == (422, "profile_unknown", {"field": "profile.dhw_installed"})
    rig.profile["dhw_installed"] = F(True, stale=True)
    assert (await rig.go("SetDHWTemp", 50))[1]["error"] == "profile_unknown"
    rig.profile["dhw_installed"] = F(False)  # known and absent: not this gate's business
    assert (await rig.go("SetDHWTemp", 50))[0] == 201
    rig.store.close()


async def test_safe_under_unknown_skips_the_profile_gate(tmp_path):
    cat = mutated(lambda raw: cmd_of(raw, "SetDHWTemp").update(
        applicability={"requires": ["profile.dhw_installed"]}, safe_under_unknown=True))
    rig = Rig(tmp_path, cat)
    rig.profile["dhw_installed"] = F(None, unknown=True)
    assert (await rig.go("SetDHWTemp", 50))[0] == 201
    rig.store.close()


async def test_profile_unknown_for_request_temperature(rig):
    rig.profile["heating_control"] = F(None, unknown=True)
    st, body = await rig.go("SetZ1HeatRequestTemperature", 3)
    assert (st, body["error"], body["detail"]) == (422, "profile_unknown", {"field": "profile.heating_control"})
    rig.profile["heating_control"] = F("direct")
    rig.profile["zone"]["z1"]["sensor"] = F(None, stale=True)
    st, body = await rig.go("SetZ1HeatRequestTemperature", 40)
    assert body["error"] == "profile_unknown" and body["detail"]["field"] == "profile.zone.z1.sensor"


@pytest.mark.parametrize("control,sensor,value,ok", [
    ("curve", "water", 5, True), ("curve", "water", 6, False), ("curve", "water", 40, False),
    ("direct", "water", 40, True), ("direct", "water", 19, False), ("direct", "water", 66, False),
    ("direct", "ext_thermostat", 22, True), ("direct", "int_thermostat", 31, False),
    ("direct", "thermistor", 9, False),
])
async def test_request_temperature_conditional_ranges(rig, control, sensor, value, ok):
    rig.profile["heating_control"] = F(control)
    rig.profile["zone"]["z1"]["sensor"] = F(sensor)
    st, body = await rig.go("SetZ1HeatRequestTemperature", value)
    assert (st == 201) is ok
    if not ok:
        assert body["error"] == "out_of_range"


async def test_cool_request_temperature_direct_ranges(rig):
    rig.profile["cooling_control"] = F("direct")
    assert (await rig.go("SetZ2CoolRequestTemperature", 20))[0] == 201  # water 5..20
    assert (await rig.go("SetZ2CoolRequestTemperature", 21))[1]["error"] == "out_of_range"
    rig.profile["zone"]["z2"]["sensor"] = F("int_thermostat")
    assert (await rig.go("SetZ2CoolRequestTemperature", 25))[0] == 201  # room 18..30


async def test_catalog_conditional_ranges_are_honoured(tmp_path):
    def edit(raw):
        cmd_of(raw, "SetDHWTemp").update(conditional_ranges=[
            {"when": {"profile.operating_mode": 3}, "min": 40, "max": 50, "step": 1}])
    rig = Rig(tmp_path, mutated(edit))
    rig.profile["operating_mode"] = F(3)
    assert (await rig.go("SetDHWTemp", 60))[1]["error"] == "out_of_range"
    assert (await rig.go("SetDHWTemp", 50))[0] == 201
    rig.profile["operating_mode"] = F(0)  # no condition matches: the base range applies
    assert (await rig.go("SetDHWTemp", 60))[0] == 201
    rig.profile["operating_mode"] = F(None, unknown=True)
    assert (await rig.go("SetDHWTemp", 61))[1]["error"] == "profile_unknown"
    rig.store.close()


# ------------------------------------------------------------------ gate order


async def test_validation_precedes_gates(rig):
    rig.mqtt.connected = False
    st, body = await rig.go("SetDHWTemp", 2.0)
    assert (st, body["error"]) == (422, "bad_type")


async def test_gate_order_with_simultaneous_failures(tmp_path):
    def edit(raw):
        c = cmd_of(raw, "SetOperationMode")
        c.update(pcb=True, risky=True, min_firmware="4.2.3",
                 applicability={"requires": ["profile.dhw_installed"]})
    rig = Rig(tmp_path, mutated(edit))
    rig.mqtt.connected = False
    rig.state.device_online = "offline"
    rig.store.prefs_put({"write_lock": True, "pcb_enabled": False})
    rig.profile["firmware"] = F(None, unknown=True)
    rig.profile["dhw_installed"] = F(None, unknown=True)
    rig.store.protected_budget_ok = lambda: False
    chain = []
    fixes = [
        lambda: setattr(rig.mqtt, "connected", True),
        lambda: setattr(rig.state, "device_online", "online"),
        lambda: rig.store.prefs_put({"write_lock": False}),
        lambda: rig.store.prefs_put({"pcb_enabled": True}),
        lambda: rig.profile.update(pcb_emulation_active=F(True)),
        lambda: rig.profile.update(firmware=F("4.2.3")),
        lambda: rig.profile.update(dhw_installed=F(True)),
    ]
    for fix in fixes:
        st, body = await rig.go("SetOperationMode", 7)
        chain.append(body["error"])
        fix()
    chain.append((await rig.go("SetOperationMode", 7))[1]["error"])
    assert chain == ["broker_disconnected", "device_offline", "write_lock", "pcb_disabled",
                     "pcb_emulation_inactive", "firmware_too_old", "profile_unknown", "read_only_value"]
    # writable value: confirm_required precedes the budget
    assert (await rig.go("SetOperationMode", 6))[1]["error"] == "confirm_required"
    assert (await rig.go("SetOperationMode", 6, True))[1]["error"] == "storage_unavailable"
    rig.store.close()


# ------------------------------------------------------------------ no-op


async def test_noop_for_live_equal_value(rig):
    st, body = await rig.go("SetDHWTemp", 45)
    assert st == 200 and body["status"] == "noop"
    assert rig.mqtt.published == []
    assert rig.rec(body)["status"] == "noop"
    assert rig.sched.items == []


async def test_noop_only_when_live_and_within_660_seconds(rig):
    await rig.sched.advance(661)
    rig.feed("LWT", "Online")
    st, body = await rig.go("SetDHWTemp", 45)  # last seen 661 s ago
    assert st == 201 and body["status"] == "pending"
    assert rig.mqtt.published == [("command", "SetDHWTemp", "45")]


async def test_retained_cached_value_is_not_a_noop(tmp_path):
    rig = Rig(tmp_path)
    rig.feed(Z1_HEAT_REQ, "2", retained=True)
    st, body = await rig.go("SetZ1HeatRequestTemperature", 2)
    assert st == 201
    rig.store.close()


async def test_holiday_compare_rules():
    assert values_match("holiday", 1, 2) and values_match("holiday", 1, 1)
    assert not values_match("holiday", 1, 0)
    assert values_match("holiday", 0, 0) and not values_match("holiday", 0, 2)
    assert values_match("equal", 50, 50.0) and not values_match("equal", 50, 51)
    assert not values_match("equal", 50, "50") and not values_match("equal", 50, None)


async def test_holiday_noop_and_confirmation(rig):
    rig.feed("main/Holiday_Mode_State", "2")
    st, body = await rig.go("SetHolidayMode", 1)
    assert (st, body["status"]) == (200, "noop")
    rig.feed("main/Holiday_Mode_State", "0")
    st, body = await rig.go("SetHolidayMode", 1)
    assert st == 201
    rig.feed("main/Holiday_Mode_State", "2")
    assert rig.rec(body)["status"] == "confirmed"


# ------------------------------------------------------------------ confirm / retry / terminal


async def test_echo_confirms(rig):
    st, body = await rig.go("SetDHWTemp", 50)
    assert st == 201 and body["status"] == "pending" and body["attempts"] == 1
    assert body["published_ts"] == T0 and body["prev_value"] == "45" and body["retained"] is False
    assert rig.mqtt.published == [("command", "SetDHWTemp", "50")]
    await rig.sched.advance(2)
    rig.feed(DHW, "50")
    r = rig.rec(body)
    assert r["status"] == "confirmed" and r["confirmed_ts"] == T0 + 2000
    await rig.sched.advance(60)
    assert len(rig.mqtt.published) == 1  # timers cancelled, no retry
    assert ("SetDHWTemp", "confirmed") in rig.statuses


async def test_drop_first_is_retried_then_confirmed(rig):
    st, body = await rig.go("SetDHWTemp", 50)
    await rig.sched.advance(9.999)
    assert len(rig.mqtt.published) == 1
    await rig.sched.advance(0.001)
    assert rig.mqtt.published[1:] == [("command", "SetDHWTemp", "50")]
    r = rig.rec(body)
    assert r["status"] == "retried" and r["attempts"] == 2
    await rig.sched.advance(3)
    rig.feed(DHW, "50")
    assert rig.rec(body)["status"] == "confirmed"
    await rig.sched.advance(30)
    assert len(rig.mqtt.published) == 2


async def test_drop_fails_at_exactly_20_seconds(rig):
    st, body = await rig.go("SetDHWTemp", 50)
    await rig.sched.advance(19.999)
    assert rig.rec(body)["status"] == "retried"
    await rig.sched.advance(0.001)
    r = rig.rec(body)
    assert r["status"] == "failed" and rig.clock.now_ms() == T0 + 20_000
    assert json.loads(r["detail"]) == {DHW: "45"}
    assert len(rig.mqtt.published) == 2
    assert ("SetDHWTemp", "failed") in rig.statuses


async def test_stale_and_retained_receipts_never_confirm(rig):
    st, body = await rig.go("SetDHWTemp", 50)
    await rig.sched.advance(1)
    rig.feed(DHW, "50", retained=True)  # retained delivery
    assert rig.rec(body)["status"] == "pending"
    # a live message that predates the publish (late delivery of an old receipt)
    from heishamon_dashboard.types import Receipt
    rig.svc.on_receipt(Receipt(DHW, "50", 50.0, True, False, T0 - 1, False, True))
    assert rig.rec(body)["status"] == "pending"
    rig.svc.on_receipt(Receipt(DHW, "50", 50.0, False, False, T0 + 5, False, True))  # invalid sample
    assert rig.rec(body)["status"] == "pending"
    rig.feed(DHW, "50")  # live and equal, after publish: confirms even though the cache already held 50
    assert rig.rec(body)["status"] == "confirmed"


async def test_live_equal_after_retained_equal_confirms(tmp_path):
    rig = Rig(tmp_path)
    rig.feed(Z1_HEAT_REQ, "2", retained=True)
    st, body = await rig.go("SetZ1HeatRequestTemperature", 2)
    assert st == 201
    rig.feed(Z1_HEAT_REQ, "2")  # same value as cached: not a change, still a fresh receipt
    assert rig.rec(body)["status"] == "confirmed"
    rig.store.close()


async def test_device_offline_before_retry_fails_without_publish(rig):
    st, body = await rig.go("SetDHWTemp", 50)
    rig.state.device_online = "offline"
    await rig.sched.advance(10)
    r = rig.rec(body)
    assert (r["status"], r["detail"]) == ("failed", "device_offline")
    assert len(rig.mqtt.published) == 1
    await rig.sched.advance(30)
    assert rig.rec(body)["detail"] == "device_offline"  # terminal timer was cancelled


@pytest.mark.parametrize("gate,code", [
    (lambda r: r.store.prefs_put({"write_lock": True}), "write_lock"),
    (lambda r: setattr(r.mqtt, "connected", False), "broker_disconnected"),
    (lambda r: r.profile.update(firmware=F("3.2.3")), "firmware_too_old"),
    (lambda r: r.store.prefs_put({"pcb_enabled": False}) or r.profile.update(
        heating_control=F("direct")), None),
])
async def test_retry_reruns_gates(rig, gate, code):
    rig.profile["firmware"] = F("4.2.3")
    st, body = await rig.go("SetSterilizationTemp", 60)
    gate(rig)
    await rig.sched.advance(10)
    r = rig.rec(body)
    if code:
        assert (r["status"], r["detail"]) == ("failed", code)
        assert len(rig.mqtt.published) == 1
    else:  # a change this command does not depend on does not stop the retry
        assert r["status"] == "retried" and len(rig.mqtt.published) == 2


async def test_mode_change_before_retry_fails_meaning_changed(rig):
    st, body = await rig.go("SetZ1HeatRequestTemperature", 3)  # shift in curve mode
    assert st == 201
    rig.profile["heating_control"] = F("direct")
    await rig.sched.advance(10)
    r = rig.rec(body)
    assert (r["status"], r["detail"]) == ("failed", "meaning_changed")
    assert len(rig.mqtt.published) == 1


async def test_sensor_change_before_retry_is_also_a_meaning_change(rig):
    rig.profile["heating_control"] = F("direct")
    st, body = await rig.go("SetZ1HeatRequestTemperature", 25)
    assert st == 201
    rig.profile["zone"]["z1"]["sensor"] = F("ext_thermostat")
    await rig.sched.advance(10)
    assert rig.rec(body)["detail"] == "meaning_changed"


async def test_unchanged_meaning_retries(rig):
    rig.profile["heating_control"] = F("direct")
    st, body = await rig.go("SetZ1HeatRequestTemperature", 30)
    await rig.sched.advance(10)
    assert rig.rec(body)["status"] == "retried"
    assert len(rig.mqtt.published) == 2


async def test_publish_failure_at_retry(rig):
    st, body = await rig.go("SetDHWTemp", 50)
    rig.mqtt.fail = True
    await rig.sched.advance(10)
    assert rig.rec(body)["detail"] == "broker_disconnected"


async def test_publish_failure_on_submit(rig):
    rig.mqtt.fail = True
    st, body = await rig.go("SetDHWTemp", 50)
    assert (st, body["error"]) == (503, "broker_disconnected")
    rec = rig.store.list_commands()[0]
    assert rec["status"] == "failed" and rig.sched.items == []


# ------------------------------------------------------------------ supersede


async def test_supersede_marks_old_and_publishes_no_stale_retry(rig):
    st1, first = await rig.go("SetDHWTemp", 50)
    await rig.sched.advance(4)
    st2, second = await rig.go("SetDHWTemp", 55)
    assert st2 == 201
    assert rig.rec(first)["status"] == "superseded"
    assert ("SetDHWTemp", "superseded") in rig.statuses
    await rig.sched.advance(6)  # the old record's +10 s would be here
    assert [p[2] for p in rig.mqtt.published] == ["50", "55"]
    await rig.sched.advance(4)  # the new record's retry
    assert [p[2] for p in rig.mqtt.published] == ["50", "55", "55"]
    assert rig.rec(first)["status"] == "superseded"
    rig.feed(DHW, "55")
    assert rig.rec(second)["status"] == "confirmed" and rig.rec(first)["status"] == "superseded"
    await rig.sched.advance(60)
    assert rig.rec(first)["status"] == "superseded"


async def test_unrelated_commands_do_not_supersede(rig):
    _, a = await rig.go("SetDHWTemp", 50)
    _, b = await rig.go("SetQuietMode", 1)
    assert rig.rec(a)["status"] == "pending" and rig.rec(b)["status"] == "pending"


# ------------------------------------------------------------------ SetCurves

HEAT = {"zone1": {"heat": {"target": {"high": 38, "low": 28}, "outside": {"high": 15, "low": -5}}}}


def leaf(topic_suffix, zone="Z1", mode="Heat"):
    return f"main/{zone}_{mode}_Curve_{topic_suffix}_Temp"


async def test_setcurves_payload_and_confirmation(rig):
    st, body = await rig.go("SetCurves", HEAT)
    assert st == 201
    assert body["payload"] == '{"zone1":{"heat":{"target":{"high":38,"low":28},"outside":{"high":15,"low":-5}}}}'
    assert rig.mqtt.published == [("command", "SetCurves", body["payload"])]
    assert set(body["keys"]) == {leaf("Target_High"), leaf("Target_Low"), leaf("Outside_High"), leaf("Outside_Low")}
    assert body["keys"][leaf("Target_High")] == {"expected": 38, "status": "pending"}
    assert body["keys"][leaf("Outside_Low")]["expected"] == -5
    for suffix, v in (("Target_High", 38), ("Target_Low", 28), ("Outside_High", 15)):
        rig.feed(leaf(suffix), str(v))
    assert rig.rec(body)["status"] == "pending"
    rig.feed(leaf("Outside_Low"), "-5")
    r = rig.rec(body)
    assert r["status"] == "confirmed" and all(k["status"] == "confirmed" for k in r["keys"].values())


async def test_setcurves_partial_failure_reports_per_key(rig):
    st, body = await rig.go("SetCurves", HEAT)
    rig.feed(leaf("Target_High"), "38")
    rig.feed(leaf("Target_Low"), "28")
    await rig.sched.advance(10)
    assert len(rig.mqtt.published) == 2
    # the retry only re-sends the keys that are still pending
    assert json.loads(rig.mqtt.published[1][2]) == {"zone1": {"heat": {"outside": {"high": 15, "low": -5}}}}
    rig.feed(leaf("Target_High"), "30")  # a later difference does not undo a confirmed key
    await rig.sched.advance(10)
    r = rig.rec(body)
    assert r["status"] == "failed"
    assert {k: v["status"] for k, v in r["keys"].items()} == {
        leaf("Target_High"): "confirmed", leaf("Target_Low"): "confirmed",
        leaf("Outside_High"): "failed", leaf("Outside_Low"): "failed"}
    assert set(json.loads(r["detail"])) == {leaf("Outside_High"), leaf("Outside_Low")}


async def test_setcurves_removes_matching_keys_and_noops(rig):
    rig.feed(leaf("Target_High"), "38")
    rig.feed(leaf("Target_Low"), "28")
    rig.feed(leaf("Outside_High"), "15")
    st, body = await rig.go("SetCurves", HEAT)
    assert st == 201
    assert body["payload"] == '{"zone1":{"heat":{"outside":{"low":-5}}}}'
    assert list(body["keys"]) == [leaf("Outside_Low")]
    rig.feed(leaf("Outside_Low"), "-5")
    assert rig.rec(body)["status"] == "confirmed"
    st, body = await rig.go("SetCurves", HEAT)  # everything matches now (live)
    assert (st, body["status"]) == (200, "noop")
    assert len(rig.mqtt.published) == 1


async def test_setcurves_supersede_stops_all_keys_of_the_old_record(rig):
    rig.feed(leaf("Target_Low"), "28")
    st, old = await rig.go("SetCurves", HEAT)
    st, new = await rig.go("SetCurves", {"zone1": {"heat": {"target": {"high": 40}}}})
    assert st == 201
    assert rig.rec(old)["status"] == "superseded"
    await rig.sched.advance(30)
    # only the new record retried/failed; the old keys not repeated are not retried
    assert [json.loads(p[2]) for p in rig.mqtt.published[2:]] == [{"zone1": {"heat": {"target": {"high": 40}}}}]
    assert rig.rec(old)["status"] == "superseded"
    assert rig.rec(new)["status"] == "failed"


async def test_setcurves_other_zone_does_not_supersede(rig):
    rig.feed(leaf("Target_Low", zone="Z2"), "28")
    _, a = await rig.go("SetCurves", HEAT)
    _, b = await rig.go("SetCurves", {"zone2": {"heat": {"target": {"high": 40}}}})
    assert rig.rec(a)["status"] == "pending" and rig.rec(b)["status"] == "pending"


@pytest.mark.parametrize("value,code", [
    ({"zone1": {"heat": {"target": {"high": 76}}}}, "out_of_range"),
    ({"zone1": {"heat": {"target": {"low": 14}}}}, "out_of_range"),
    ({"zone1": {"heat": {"outside": {"low": -21}}}}, "out_of_range"),
    ({"zone1": {"heat": {"outside": {"high": 31}}}}, "out_of_range"),
    ({"zone1": {"cool": {"target": {"high": 21}}}}, "out_of_range"),
    ({"zone1": {"cool": {"target": {"low": 4}}}}, "out_of_range"),
    ({"zone1": {"cool": {"outside": {"low": 14}}}}, "out_of_range"),
    ({"zone2": {"heat": {"target": {"high": 30, "low": 31}}}}, "out_of_range"),
    ({"zone2": {"heat": {"outside": {"high": 5, "low": 5}}}}, "out_of_range"),
    ({"zone1": {"heat": {"tgt": {"high": 30}}}}, "bad_type"),
    ({"zone1": {"warm": {"target": {"high": 30}}}}, "bad_type"),
    ({"zone1": {"heat": {"target": {"mid": 30}}}}, "bad_type"),
    ({"zone1": {"heat": {"target": {"high": True}}}}, "bad_type"),
])
async def test_setcurves_validation(rig, value, code):
    st, body = await rig.go("SetCurves", value)
    assert (st, body["error"]) == (422, code)


async def test_setcurves_limits_accept_edges_and_equal_targets(rig):
    ok = {"zone1": {"heat": {"target": {"high": 75, "low": 75}, "outside": {"high": 30, "low": 29}}},
          "zone2": {"cool": {"target": {"high": 20, "low": 5}, "outside": {"high": 30, "low": 15}}}}
    assert (await rig.go("SetCurves", ok))[0] == 201


async def test_setcurves_ordering_uses_merged_state(rig):
    rig.feed(leaf("Target_Low"), "30")
    rig.feed(leaf("Outside_High"), "10")
    assert (await rig.go("SetCurves", {"zone1": {"heat": {"target": {"high": 29}}}}))[0] == 422
    assert (await rig.go("SetCurves", {"zone1": {"heat": {"outside": {"low": 10}}}}))[0] == 422
    assert (await rig.go("SetCurves", {"zone1": {"heat": {"outside": {"low": 9}}}}))[0] == 201


def coupled_profile(zone="z1", sensor="ext_thermostat", heat="direct", cool="curve"):
    p = make_profile(heating_control=F(heat), cooling_control=F(cool))
    p["zone"][zone]["sensor"] = F(sensor)
    return p


@pytest.mark.parametrize("sensor", ["ext_thermostat", "int_thermostat", "thermistor"])
async def test_setcurves_coupled_mode_skips_target_ordering(rig, sensor):
    # direct control + room sensor: the cold-end target is the setpoint, the warm-end target is unused
    rig.profile = coupled_profile(sensor=sensor)
    rig.feed(leaf("Target_Low"), "30")
    rig.feed(leaf("Outside_High"), "10")
    st, body = await rig.go("SetCurves", {"zone1": {"heat": {"target": {"high": 20}}}})
    assert st == 201 and body["payload"] == '{"zone1":{"heat":{"target":{"high":20}}}}'
    assert (await rig.go("SetCurves", {"zone1": {"heat": {"target": {"high": 18, "low": 40}}}}))[0] == 201
    # limits and the outside ordering still apply
    assert (await rig.go("SetCurves", {"zone1": {"heat": {"target": {"high": 14}}}}))[1]["error"] == "out_of_range"
    assert (await rig.go("SetCurves", {"zone1": {"heat": {"outside": {"low": 10}}}}))[0] == 422


@pytest.mark.parametrize("profile", [
    coupled_profile(sensor="water"),  # direct + water sensor
    coupled_profile(heat="curve"),  # curve mode
    coupled_profile(zone="z2"),  # the other zone is coupled, not this one
    coupled_profile(heat="curve", cool="direct"),  # only cooling is coupled
    make_profile(heating_control=F("direct", unknown=True),
                 zone={"z1": {"active": F(True), "sensor": F("ext_thermostat")},
                       "z2": {"active": F(True), "sensor": F("water")}}),  # unknown: keep the rule
])
async def test_setcurves_target_ordering_kept_when_not_coupled(rig, profile):
    rig.profile = profile
    rig.feed(leaf("Target_Low"), "30")
    st, body = await rig.go("SetCurves", {"zone1": {"heat": {"target": {"high": 29}}}})
    assert (st, body["error"], body["detail"]["rule"]) == (422, "out_of_range", "ordering")


async def test_setcurves_coupled_cool_skips_cool_ordering_only(rig):
    rig.profile = coupled_profile(heat="curve", cool="direct", sensor="thermistor")
    rig.feed(leaf("Target_Low", mode="Cool"), "15")
    rig.feed(leaf("Target_Low"), "30")
    assert (await rig.go("SetCurves", {"zone1": {"cool": {"target": {"high": 10}}}}))[0] == 201
    assert (await rig.go("SetCurves", {"zone1": {"heat": {"target": {"high": 29}}}}))[0] == 422


# ------------------------------------------------------------------ classes


async def test_trigger_is_sent_without_retry(rig):
    st, body = await rig.go("SetForceDefrost", 1, True)
    assert (st, body["status"], body["class"]) == (201, "sent", "trigger")
    assert rig.mqtt.published == [("command", "SetForceDefrost", "1")]
    assert body["retained"] is False and rig.sched.items == []
    await rig.sched.advance(60)
    assert rig.rec(body)["status"] == "sent" and len(rig.mqtt.published) == 1


async def test_unverifiable_pcb_command_is_sent_without_retry(rig):
    rig.store.prefs_put({"pcb_enabled": True})
    rig.profile["pcb_emulation_active"] = F(True)
    st, body = await rig.go("SetPoolTemp", 20, True)
    assert (st, body["status"], body["class"], body["payload"]) == (201, "sent", "unverifiable", "20.0")
    st, body = await rig.go("SetSmartGridMode", 2, True)
    assert body["status"] == "sent"
    await rig.sched.advance(60)
    assert len(rig.mqtt.published) == 2


async def test_unverifiable_non_pcb_command(rig):
    st, body = await rig.go("SetPump", 1)
    assert (st, body["status"], body["class"]) == (201, "sent", "unverifiable")
    await rig.sched.advance(60)
    assert len(rig.mqtt.published) == 1


async def test_retained_exception_path(rig):
    st, body = await rig.go("s0/WatthourTotal/1", 123456.789, True)
    assert (st, body["status"], body["class"], body["retained"]) == (201, "sent", "retained_exception", True)
    assert rig.mqtt.published == [("retained", "s0/WatthourTotal/1", "123456.789")]
    rig.profile["firmware"] = F("3.5")
    st, body = await rig.go("opentherm/read/dhwSetUppBound", 60, True)
    assert rig.mqtt.published[-1] == ("retained", "opentherm/read/dhwSetUppBound", "60")
    assert body["retained"] is True
    # an echo on the retained topic is not a confirmation
    rig.feed("s0/WatthourTotal/1", "123456.789")
    assert rig.rec(body)["status"] == "sent"
    await rig.sched.advance(60)
    assert len(rig.mqtt.published) == 2


async def test_input_path(rig):
    rig.profile["firmware"] = F("3.5")
    st, body = await rig.go("opentherm/read/outsideTemp", 7.5)
    assert (st, body["status"], body["class"], body["retained"]) == (201, "sent", "input", False)
    assert rig.mqtt.published == [("input", "opentherm/read/outsideTemp", "7.5")]
    st, body = await rig.go("opentherm/read/flameState", 1)
    assert rig.mqtt.published[-1] == ("input", "opentherm/read/flameState", "1")
    await rig.sched.advance(60)
    assert len(rig.mqtt.published) == 2


# ------------------------------------------------------------------ firmware


def sample_value(entry):
    if entry.get("allowed"):
        return entry["allowed"][-1]
    rng = entry.get("range") or {}
    if entry["type"] == "json":
        return HEAT
    if entry["type"] == "dec3":
        return 5000
    lo = rng.get("min", 0)
    return float(lo) if entry["type"] == "dec1" else int(lo)


@pytest.mark.parametrize("firmware", [None, "3.2.3", "Local build", "Nightly-abc"])
async def test_old_or_unknown_firmware_blocks_exactly_the_newer_entries(tmp_path, firmware):
    rig = Rig(tmp_path)
    rig.store.prefs_put({"pcb_enabled": True})
    rig.profile["pcb_emulation_active"] = F(True)
    rig.profile["firmware"] = F(firmware, unknown=firmware is None)
    rig.profile["firmware_assumed"] = True
    too_old = set()
    for c in CAT.commands:
        st, body = await rig.go(c["name"], sample_value(c), True)
        if st != 201 and st != 200:
            assert body["error"] != "profile_unknown", c["name"]
        if st == 422 and body["error"] == "firmware_too_old":
            too_old.add(c["name"])
    expect = {c["name"] for c in CAT.commands if parse_firmware(c["min_firmware"])[0] > (3, 2, 3)}
    assert len(expect) == 20
    assert too_old == expect
    old_inputs = set()
    for i in CAT.inputs:
        st, body = await rig.go(i["path"], sample_value(i), True)
        if st == 422 and body["error"] == "firmware_too_old":
            old_inputs.add(i["path"])
    assert old_inputs == {i["path"] for i in CAT.inputs if i["path"].startswith("opentherm/")}
    assert len(old_inputs) == 16
    rig.store.close()


async def test_supported_firmware_opens_the_gate(tmp_path):
    rig = Rig(tmp_path)
    rig.profile["firmware"] = F("4.2.3")
    assert (await rig.go("SetSterilizationTemp", 60))[0] == 201
    rig.profile["firmware"] = F("4.1.2")
    assert (await rig.go("SetSterilizationMaxTime", 10))[1]["error"] == "firmware_too_old"
    assert (await rig.go("SetHeaterOnOutdoorTemp", 5))[0] == 201
    rig.store.close()


# ------------------------------------------------------------------ listen-only


async def fail_one(rig, value, change_other=True, change_readback=False, gap=20):
    rig.svc.rate_max = 1000  # these tests are about the listen-only streak, not the rate limit
    st, body = await rig.go("SetDHWTemp", value)
    assert st == 201, body
    await rig.sched.advance(2)
    if change_other:
        rig.feed(OUTSIDE, str(value))
    if change_readback:
        rig.feed(DHW, "41")
    await rig.sched.advance(gap - 2)
    return body


async def test_three_consecutive_no_change_failures_flag_listen_only(rig):
    for v in (50, 51):
        body = await fail_one(rig, v)
        assert rig.rec(body)["status"] == "failed"
        assert not rig.svc.listen_only_suspected
    await fail_one(rig, 52)
    assert rig.svc.listen_only_suspected is True and rig.listen == [True]
    assert len(rig.events("listen_only_suspected")) == 1
    # commands are still sent and failed stays failed
    body = await fail_one(rig, 53)
    assert rig.rec(body)["status"] == "failed" and rig.svc.listen_only_suspected
    st, ok = await rig.go("SetDHWTemp", 54)
    assert st == 201
    rig.feed(DHW, "54")
    assert rig.rec(ok)["status"] == "confirmed"
    assert rig.svc.listen_only_suspected is False and rig.listen == [True, False]
    assert len(rig.events("listen_only_cleared")) == 1


async def test_failures_with_change_or_quiet_device_do_not_count(rig):
    await fail_one(rig, 50)
    await fail_one(rig, 51)
    await fail_one(rig, 52, change_readback=True)  # the read-back topic changed: not "no change"
    await fail_one(rig, 53)
    assert not rig.svc.listen_only_suspected
    await fail_one(rig, 54)
    await fail_one(rig, 55)
    assert rig.svc.listen_only_suspected  # 53, 54, 55 consecutive
    # a confirmation clears the flag; a device that stays silent afterwards never re-flags it
    st, ok = await rig.go("SetDHWTemp", 60)
    rig.feed(DHW, "60")
    assert not rig.svc.listen_only_suspected
    for v in (61, 62, 63):
        await fail_one(rig, v, change_other=False)
    assert not rig.svc.listen_only_suspected


async def test_confirmation_between_failures_resets_the_streak(rig):
    await fail_one(rig, 50)
    await fail_one(rig, 51)
    st, body = await rig.go("SetDHWTemp", 70)
    rig.feed(DHW, "70")
    await fail_one(rig, 52)
    await fail_one(rig, 53)
    assert not rig.svc.listen_only_suspected


async def test_failures_spread_over_more_than_30_minutes_do_not_flag(rig):
    await fail_one(rig, 50)
    await rig.sched.advance(20 * 60)
    await fail_one(rig, 51)
    await rig.sched.advance(20 * 60)
    await fail_one(rig, 52)
    assert not rig.svc.listen_only_suspected


async def test_failure_with_device_offline_at_the_end_does_not_count(rig):
    await fail_one(rig, 50)
    await fail_one(rig, 51)
    st, body = await rig.go("SetDHWTemp", 52)
    await rig.sched.advance(2)
    rig.feed(OUTSIDE, "9")
    rig.state.device_online = "offline"
    await rig.sched.advance(18)
    rig.state.device_online = "online"
    assert not rig.svc.listen_only_suspected


# ------------------------------------------------------------------ audit, EEPROM, events


async def test_every_record_lands_in_the_store_and_is_pushed(rig):
    _, a = await rig.go("SetDHWTemp", 50)
    rig.feed(DHW, "50")
    _, b = await rig.go("SetDHWTemp", 50)  # noop
    _, c = await rig.go("SetForceDefrost", 1, True)
    got = {r["uuid"]: r["status"] for r in rig.store.list_commands()}
    assert got == {a["id"]: "confirmed", b["id"]: "noop", c["id"]: "sent"}
    assert rig.statuses == [("SetDHWTemp", "pending"), ("SetDHWTemp", "confirmed"),
                            ("SetDHWTemp", "noop"), ("SetForceDefrost", "sent")]
    assert "id" in a and "uuid" not in a


async def test_status_callback_errors_do_not_break_commands(tmp_path):
    rig = Rig(tmp_path)
    rig.svc._on_status = lambda rec: 1 / 0
    assert (await rig.go("SetDHWTemp", 50))[0] == 201
    rig.store.close()


async def test_eeprom_warning_counts_publish_attempts_in_the_last_hour(rig):
    assert rig.svc.recent_change_count("SetDHWTemp") == 0
    for v in (50, 51, 52):
        st, body = await rig.go("SetDHWTemp", v)
        rig.feed(DHW, str(v))
        assert rig.rec(body)["status"] == "confirmed"
        await rig.sched.advance(60)
    assert rig.svc.recent_change_count("SetDHWTemp") == 3
    assert rig.svc.eeprom_warning("SetDHWTemp") is True
    assert rig.svc.eeprom_warning("SetQuietMode") is False
    assert rig.svc.to_api(rig.rec(body))["eeprom_warning"] is True
    await rig.sched.advance(60 * 60)
    assert rig.svc.recent_change_count("SetDHWTemp") == 0
    assert rig.svc.to_api(rig.rec(body))["eeprom_warning"] is False


async def test_eeprom_warning_counts_superseded(rig):
    bodies = [(await rig.go("SetDHWTemp", v))[1] for v in (50, 51, 52)]  # two are superseded
    assert [rig.rec(b)["status"] for b in bodies] == ["superseded", "superseded", "pending"]
    assert bodies[0]["eeprom_warning"] is False and bodies[2]["eeprom_warning"] is True
    await rig.go("SetDHWTemp", 45)  # equals the read-back but publishes while 52 is in flight
    assert rig.svc.recent_change_count("SetDHWTemp") == 4
    st, other = await rig.go("SetQuietMode", 1)
    assert other["eeprom_warning"] is False


async def test_noop_does_not_count_as_publish_attempt(rig):
    await rig.go("SetDHWTemp", 45)  # noop
    assert rig.svc.recent_change_count("SetDHWTemp") == 0


# ------------------------------------------------------------------ review fixes (C1–C6)


async def test_revert_before_readback_publishes_and_kills_retry(rig):
    _, a = await rig.go("SetDHWTemp", 55)
    await rig.sched.advance(1)
    st, b = await rig.go("SetDHWTemp", 45)  # equals the live read-back, but 55 may still land
    assert st == 201 and b["status"] == "pending"
    assert [p[2] for p in rig.mqtt.published] == ["55", "45"]
    assert rig.rec(a)["status"] == "superseded"
    await rig.sched.advance(10)  # the 55 retry would be here; only the 45 retry may publish
    assert [p[2] for p in rig.mqtt.published] == ["55", "45", "45"]
    assert rig.rec(a)["status"] == "superseded"


async def test_revert_after_retry_publishes(rig):
    _, a = await rig.go("SetDHWTemp", 55)
    await rig.sched.advance(10)  # the retry publishes 55; the live read-back stays 45
    assert [p[2] for p in rig.mqtt.published] == ["55", "55"]
    await rig.sched.advance(1)
    st, b = await rig.go("SetDHWTemp", 45)
    assert st == 201 and b["status"] == "pending"
    assert [p[2] for p in rig.mqtt.published][-1] == "45"
    assert rig.rec(a)["status"] == "superseded"
    assert rig.svc._flights[b["id"]].last_publish_ts == rig.clock.now_ms()


async def test_setcurves_partial_ordering_against_readback(rig):
    rig.feed(leaf("Outside_Low"), "-15")
    st, body = await rig.go("SetCurves", {"zone1": {"heat": {"outside": {"high": -20}}}})
    assert (st, body["error"], body["detail"]["rule"]) == (422, "out_of_range", "ordering")


async def test_setcurves_missing_counterpart_profile_unknown(rig):
    st, body = await rig.go("SetCurves", {"zone1": {"heat": {"outside": {"high": -20}}}})
    assert (st, body["error"], body["detail"]) == (422, "profile_unknown", {"field": leaf("Outside_Low")})
    rig.feed(leaf("Outside_Low"), "-15")
    rig.clock.t += 700_000  # a stale read-back counts as missing
    st, body = await rig.go("SetCurves", {"zone1": {"heat": {"outside": {"high": 10}}}})
    assert (st, body["error"]) == (422, "profile_unknown")


async def test_setcurves_retained_snapshot_counts_as_known(rig):
    rig.feed(leaf("Outside_Low"), "-15", retained=True)  # fresh dashboard: only the retained snapshot
    st, body = await rig.go("SetCurves", {"zone1": {"heat": {"outside": {"high": -20}}}})
    assert (st, body["error"], body["detail"]["rule"]) == (422, "out_of_range", "ordering")


async def test_setcurves_two_partials_conflict(rig):
    rig.feed(leaf("Outside_Low"), "-15")
    rig.feed(leaf("Outside_High"), "15")
    st, a = await rig.go("SetCurves", {"zone1": {"heat": {"outside": {"low": -10}}}})
    assert st == 201
    st, body = await rig.go("SetCurves", {"zone1": {"heat": {"outside": {"high": -12}}}})
    assert (st, body["error"], body["detail"]["rule"]) == (422, "out_of_range", "ordering")
    assert rig.rec(a)["status"] == "pending"
    # a disjoint leaf of the same zone/mode stays in flight
    st, c = await rig.go("SetCurves", {"zone1": {"heat": {"outside": {"high": 12}}}})
    assert st == 201 and rig.rec(a)["status"] == "pending"


async def test_setcurves_retry_meaning_changed(rig):
    st, body = await rig.go("SetCurves", HEAT)
    assert st == 201
    rig.profile = coupled_profile(sensor="ext_thermostat", heat="direct")
    await rig.sched.advance(10)
    r = rig.rec(body)
    assert r["status"] == "failed" and r["detail"] == "meaning_changed"
    assert len(rig.mqtt.published) == 1


async def test_identical_inflight_returns_record(rig):
    st, a = await rig.go("SetDHWTemp", 50)
    st, b = await rig.go("SetDHWTemp", 50)
    assert st == 200 and b["id"] == a["id"] and b["status"] == "pending"
    assert len(rig.mqtt.published) == 1
    st, c = await rig.go("SetCurves", HEAT)
    st, d = await rig.go("SetCurves", {"zone1": {"heat": {"target": {"high": 38}}}})
    assert st == 200 and d["id"] == c["id"]
    assert len(rig.mqtt.published) == 2


async def test_rate_limit_429(rig):
    rig.svc.rate_max = 3
    for v in (50, 51, 52):
        assert (await rig.go("SetDHWTemp", v))[0] == 201
    await rig.sched.advance(100)
    st, body = await rig.go("SetDHWTemp", 53)
    assert (st, body["error"]) == (429, "rate_limited")
    assert body["detail"] == {"retry_after_s": 3600 - 100}
    assert len(rig.mqtt.published) == 3
    assert (await rig.go("SetQuietMode", 1))[0] == 201  # per command name
    await rig.sched.advance(3500)
    assert (await rig.go("SetDHWTemp", 53))[0] == 201


async def test_retry_over_cap_fails_rate_limited(rig):
    rig.svc.rate_max = 1
    st, body = await rig.go("SetDHWTemp", 50)
    await rig.sched.advance(10)
    r = rig.rec(body)
    assert r["status"] == "failed" and r["detail"] == "rate_limited"
    assert len(rig.mqtt.published) == 1


async def test_storage_unavailable_keeps_old_flight(rig):
    st, old = await rig.go("SetDHWTemp", 50)

    def boom(rec):
        raise StorageUnavailable("full")

    rig.store.append_command = boom
    st, body = await rig.go("SetDHWTemp", 55)
    assert (st, body["error"]) == (503, "storage_unavailable")
    assert rig.rec(old)["status"] == "pending"
    await rig.sched.advance(10)
    assert rig.rec(old)["status"] == "retried"
    assert [p[2] for p in rig.mqtt.published] == ["50", "50"]


# ------------------------------------------------------------------ K1, K4
async def test_opentherm_bound_128_is_out_of_range(rig):
    st, body = await rig.go("opentherm/read/chSetUppBound", 128, True)
    assert (st, body["error"]) == (422, "out_of_range")
    assert (await rig.go("opentherm/read/chSetUppBound", 127, True))[0] == 201


async def test_heater_j_only_known_series(rig):
    rig.profile["series"] = F("K")
    st, body = await rig.go("SetHeaterDelayTime", 10, True)
    assert (st, body["error"], body["detail"]) == (422, "not_applicable", {"series": "K"})
    rig.profile["series"] = F("K", stale=True)  # stale but known: its value still decides
    assert (await rig.go("SetHeaterDelayTime", 10, True))[1]["error"] == "not_applicable"
    rig.profile["series"] = F("J", stale=True)
    assert (await rig.go("SetHeaterDelayTime", 10))[0] == 201


async def test_heater_unknown_series_needs_confirm(rig):
    for series in (F(None, unknown=True), F(None), None):
        if series is None:
            rig.profile.pop("series", None)
        else:
            rig.profile["series"] = series
        st, body = await rig.go("SetHeaterStartDelta", 5)
        assert (st, body["error"]) == (422, "confirm_required")
    assert (await rig.go("SetHeaterStartDelta", 5, True))[0] == 201
