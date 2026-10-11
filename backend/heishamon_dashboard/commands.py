"""Command service: validation, gates, publish, confirmation, retry (spec §6, Appendix A.2)."""
import asyncio
import json
import logging
import re
import uuid as uuidlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any, Protocol

from heishamon_dashboard.catalog import Catalog
from heishamon_dashboard.encoding import EncodingError, check_type, encode, to_decimal
from heishamon_dashboard.firmware import parse_firmware
from heishamon_dashboard.mqtt import PublishError
from heishamon_dashboard.store import StorageUnavailable
from heishamon_dashboard.types import Clock, Receipt

log = logging.getLogger(__name__)

RETRY_AFTER_MS = 10_000
TERMINAL_AFTER_MS = 20_000
NOOP_FRESH_MS = 660_000
EEPROM_WINDOW_MS = 3_600_000
EEPROM_WARN_COUNT = 3
LISTEN_ONLY_STREAK = 3
LISTEN_ONLY_WINDOW_MS = 30 * 60_000
OPERATION_MODE_READ_ONLY = (7, 8)

_REQUEST_TEMP = re.compile(r"^SetZ([12])(Heat|Cool)RequestTemperature$")
# Direct-mode ranges of the request temperatures (A.2), used when the catalog entry carries no
# conditional ranges: (water sensor, room sensor).
_DIRECT_RANGES = {"Heat": ((20, 65), (10, 30)), "Cool": ((5, 20), (18, 30))}
_CURVE_SHIFT = (-5, 5)

_CURVE_ZONES = {"zone1": "Z1", "zone2": "Z2"}
_CURVE_MODES = {"heat": "Heat", "cool": "Cool"}
_CURVE_GROUPS = {"target": "Target", "outside": "Outside"}
_CURVE_ENDS = {"high": "High", "low": "Low"}
_CURVE_LIMITS = {  # (outside, target) inclusive limits, spec §8
    "heat": ((-20, 30), (15, 75)),
    "cool": ((15, 30), (5, 20)),
}


class Scheduler(Protocol):
    def call_later(self, delay_s: float, callback: Callable[[], Awaitable[None]]) -> Any:
        """Run `callback` once after `delay_s`; the returned handle has `cancel()`."""


class AsyncioScheduler:
    """Production scheduler on the running asyncio loop."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()

    def call_later(self, delay_s: float, callback: Callable[[], Awaitable[None]]):
        loop = asyncio.get_running_loop()

        def fire() -> None:
            task = loop.create_task(callback())
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        return loop.call_later(delay_s, fire)


class _Reject(Exception):
    def __init__(self, code: str, message: str, detail: dict | None = None, status: int = 422):
        super().__init__(message)
        self.code, self.message, self.detail, self.status = code, message, detail, status


def error_body(code: str, message: str, detail: dict | None = None) -> dict:
    return {"error": code, "message": message, "detail": detail}


@dataclass
class _Plan:
    name: str
    entry: dict
    kind: str  # "command" | "input"
    cls: str  # setting | trigger | unverifiable | retained_exception | input
    type_: str
    value: Any
    payload: str
    retained: bool
    risky: bool
    pcb: bool
    readback: list[str] = field(default_factory=list)
    expected: dict[str, Any] = field(default_factory=dict)  # read-back topic -> expected value
    compare: str = "equal"
    meaning: dict[str, Any] = field(default_factory=dict)
    unknown_fields: list[str] = field(default_factory=list)  # profile fields gate 7 names
    read_only: bool = False


@dataclass
class _Flight:
    rec: dict  # store-form record
    plan: _Plan
    confirm: bool
    payload_keys: dict[str, int]  # SetCurves: sent key -> expected; empty otherwise
    retry_handle: Any = None
    terminal_handle: Any = None
    changed_seen: bool = False
    other_changed: bool = False
    done: bool = False

    @property
    def topics(self) -> set[str]:
        return set(self.plan.expected)


def _num_equal(expected, actual) -> bool:
    try:
        return Decimal(repr(float(actual))) == Decimal(repr(float(expected)))
    except (TypeError, ValueError, ArithmeticError):
        return False


def values_match(compare: str, expected, actual) -> bool:
    """A.2 comparison rules: `equal`, `holiday` and `curve_leaf` (a plain per-leaf equality)."""
    if actual is None or isinstance(actual, str):
        return False
    if compare == "holiday":
        if _num_equal(expected, 1):
            return _num_equal(actual, 1) or _num_equal(actual, 2)
        return _num_equal(actual, expected)
    return _num_equal(expected, actual)


def _field(profile: dict, path: str) -> dict | None:
    node: Any = profile
    parts = path.split(".")
    if parts[0] == "profile":
        parts = parts[1:]
    for p in parts:
        if not isinstance(node, dict) or p not in node:
            return None
        node = node[p]
    return node if isinstance(node, dict) and "value" in node else None


def _usable(f: dict | None) -> bool:
    return f is not None and not f.get("unknown") and not f.get("stale")


class CommandService:
    def __init__(
        self,
        catalog: Catalog,
        mqtt,
        state,
        store,
        clock: Clock,
        scheduler: Scheduler,
        profile_fn: Callable[[], dict],
        on_status: Callable[[dict], None] | None = None,
        on_listen_only: Callable[[bool], None] | None = None,
    ):
        self._catalog = catalog
        self._mqtt = mqtt
        self._state = state
        self._store = store
        self._clock = clock
        self._scheduler = scheduler
        self._profile_fn = profile_fn
        self._on_status = on_status
        self._on_listen_only = on_listen_only
        self._flights: dict[str, _Flight] = {}
        self._fail_streak: list[int] = []
        self.listen_only_suspected = False

    # ------------------------------------------------------------------ public

    async def submit(self, name: str, value, confirm: bool) -> tuple[int, dict]:
        """Steps 1–10 of spec §6. Returns `(http_status, Command | Error)`."""
        now = self._clock.now_ms()
        try:
            plan = self._plan(name, value)  # step 1
            self._gates(plan, confirm)  # step 2
        except _Reject as r:
            return self._rejected(name, r, now)

        sent_keys: dict[str, int] = {}
        if plan.cls == "setting":  # step 3: no-op check
            plan, sent_keys = self._drop_matching(plan, now)
            if not plan.expected:
                return self._noop(plan, now)

        # step 4: supersede, atomically (no await between selection and marking)
        for old in [f for f in self._flights.values() if f.topics & set(plan.expected)]:
            self._finish(old, "superseded", None, now)

        record = self._record(plan, now, sent_keys)
        try:
            self._store.append_command(dict(record))
        except StorageUnavailable:
            return self._rejected(name, _Reject("storage_unavailable", "protected-record budget is full",
                                                status=503), now)
        flight = _Flight(rec=record, plan=plan, confirm=confirm, payload_keys=sent_keys)
        if plan.cls == "setting":
            self._flights[record["uuid"]] = flight
        try:  # step 5: publish
            await self._publish(plan, plan.payload)
        except PublishError as e:
            self._finish(flight, "failed", "broker_disconnected", self._clock.now_ms())
            return 503, error_body("broker_disconnected", str(e))
        if plan.cls == "setting":
            flight.retry_handle = self._scheduler.call_later(
                RETRY_AFTER_MS / 1000, lambda f=flight: self._retry(f))
            flight.terminal_handle = self._scheduler.call_later(
                TERMINAL_AFTER_MS / 1000, lambda f=flight: self._terminal(f))
        self._push(record)
        return 201, self.to_api(record)

    def on_receipt(self, receipt: Receipt) -> None:
        """Feed every receipt (not only changes). Only live ones with ts ≥ published_ts confirm."""
        if receipt.retained:
            return
        for f in list(self._flights.values()):
            if f.done or receipt.ts < (f.rec["published_ts"] or 0):
                continue
            if receipt.topic in f.topics:
                if receipt.changed:
                    f.changed_seen = True
                self._try_confirm(f, receipt)
            elif receipt.changed and receipt.qualifying:
                f.other_changed = True

    def recent_change_count(self, name: str, now: int | None = None) -> int:
        """Changes of one setting in the last 60 minutes (confirmed, retried, failed records)."""
        now = self._clock.now_ms() if now is None else now
        recs = self._store.list_commands(limit=1000)
        return sum(
            1 for r in recs
            if r["name"] == name and r["status"] in ("confirmed", "retried", "failed")
            and (r.get("submitted_ts") or 0) >= now - EEPROM_WINDOW_MS
        )

    def eeprom_warning(self, name: str, now: int | None = None) -> bool:
        return self.recent_change_count(name, now) >= EEPROM_WARN_COUNT

    @staticmethod
    def to_api(record: dict) -> dict:
        out = dict(record)
        out["id"] = out.pop("uuid")
        return out

    # ------------------------------------------------------------- step 1

    def _plan(self, name: str, value) -> _Plan:
        cmd = self._catalog.command(name)
        inp = None if cmd else self._catalog.input(name)
        if cmd is None and inp is None:
            raise _Reject("unknown_command", f"unknown command or input {name!r}")
        entry = cmd or inp
        type_ = entry["type"]
        cls = entry["class"]
        profile = self._profile_fn()

        try:
            checked = check_type(type_, value)
        except EncodingError as e:
            raise _Reject(e.code, e.message) from None

        plan = _Plan(
            name=name, entry=entry, kind="command" if cmd else "input", cls=cls, type_=type_, value=value,
            payload="", retained=bool(inp and inp.get("retain")), risky=False,
            pcb=bool(cmd and cmd.get("pcb")),
        )
        if cmd:
            plan.readback = list(cmd.get("readback") or [])
            plan.compare = cmd.get("compare", "equal")

        if type_ == "json":
            self._plan_curves(plan, checked)
        else:
            rng = self._resolve_range(plan, profile)
            if name == "SetOperationMode" and checked in OPERATION_MODE_READ_ONLY:
                plan.read_only = True
            else:
                self._check_value(plan, checked, rng)
            plan.payload = encode(type_, value)
            if cls == "setting" and plan.readback:
                plan.expected = {plan.readback[0]: _plain_number(checked)}

        plan.risky = self._is_risky(plan)
        return plan

    def _is_risky(self, plan: _Plan) -> bool:
        if plan.cls in ("trigger", "retained_exception") or plan.pcb:
            return True
        if plan.name == "SetHeatpump":
            return plan.value == 0
        return bool(plan.entry.get("risky"))

    def _resolve_range(self, plan: _Plan, profile: dict) -> dict | None:
        """The effective range; records the profile fields it depends on (meaning, unknowns)."""
        entry = plan.entry
        base = entry.get("range")
        cond = entry.get("conditional_ranges") or []
        m = _REQUEST_TEMP.match(plan.name)
        if cond:
            for item in cond:
                results = []
                for path, expected in item["when"].items():
                    f = _field(profile, path)
                    if not _usable(f):
                        plan.unknown_fields.append(path)
                        results.append(None)
                    else:
                        plan.meaning[path] = f["value"]
                        results.append(f["value"] == expected)
                if all(r is True for r in results):
                    return {k: v for k, v in item.items() if k != "when"}
            return None if plan.unknown_fields else base
        if m and plan.cls == "setting":
            zone, kind = m.group(1), m.group(2)
            ctl_path = "profile." + ("heating_control" if kind == "Heat" else "cooling_control")
            ctl = _field(profile, ctl_path)
            if not _usable(ctl):
                plan.unknown_fields.append(ctl_path)
                return None
            plan.meaning[ctl_path] = ctl["value"]
            if ctl["value"] == "curve":
                lo, hi = _CURVE_SHIFT
            else:
                sensor_path = f"profile.zone.z{zone}.sensor"
                sensor = _field(profile, sensor_path)
                if not _usable(sensor):
                    plan.unknown_fields.append(sensor_path)
                    return None
                plan.meaning[sensor_path] = sensor["value"]
                water, room = _DIRECT_RANGES[kind]
                lo, hi = water if sensor["value"] == "water" else room
            return {"min": lo, "max": hi, "step": 1}
        return base

    def _check_value(self, plan: _Plan, checked: Decimal, rng: dict | None) -> None:
        entry = plan.entry
        allowed = entry.get("allowed")
        if allowed is None and plan.type_ == "bool":
            allowed = [0, 1]
        if allowed is not None:
            if checked not in [Decimal(repr(a)) for a in allowed]:
                raise _Reject("not_allowed_value", f"{plan.value} is not one of {allowed}",
                              {"allowed": allowed})
            return
        if rng is None:
            return  # range depends on an unknown profile field; gate 7 reports it
        lo, hi, step = rng.get("min"), rng.get("max"), rng.get("step")
        if (lo is not None and checked < to_decimal(lo)) or (hi is not None and checked > to_decimal(hi)):
            raise _Reject("out_of_range", f"{plan.value} is outside {lo}..{hi}", {"min": lo, "max": hi})
        if step:
            base = to_decimal(lo if lo is not None else 0)
            if (checked - base) % to_decimal(step) != 0:
                raise _Reject("bad_step", f"{plan.value} is not on the step grid of {step}",
                              {"step": step, "min": lo})

    def _plan_curves(self, plan: _Plan, value: dict) -> None:
        leaves: dict[str, int] = {}
        meta: dict[str, tuple[str, str, str]] = {}  # topic -> (mode, group, end)
        for zk, zv in value.items():
            if zk not in _CURVE_ZONES or not isinstance(zv, dict):
                raise _Reject("bad_type", f"unknown or malformed zone key {zk!r}")
            for mk, mv in zv.items():
                if mk not in _CURVE_MODES or not isinstance(mv, dict):
                    raise _Reject("bad_type", f"unknown or malformed mode key {mk!r}")
                for gk, gv in mv.items():
                    if gk not in _CURVE_GROUPS or not isinstance(gv, dict):
                        raise _Reject("bad_type", f"unknown or malformed curve group {gk!r}")
                    for ek, ev in gv.items():
                        if ek not in _CURVE_ENDS:
                            raise _Reject("bad_type", f"unknown curve end {ek!r}")
                        if isinstance(ev, bool) or not isinstance(ev, int):
                            raise _Reject("bad_type", "curve values must be integer literals")
                        topic = _curve_topic(zk, mk, gk, ek)
                        leaves[topic] = ev
                        meta[topic] = (mk, gk, ek)
        if not leaves:
            raise _Reject("bad_type", "SetCurves needs at least one value")
        for topic, v in leaves.items():
            mode, group, _ = meta[topic]
            lo, hi = _CURVE_LIMITS[mode][0 if group == "outside" else 1]
            if not lo <= v <= hi:
                raise _Reject("out_of_range", f"{topic} {v} is outside {lo}..{hi}",
                              {"key": topic, "min": lo, "max": hi})
        for topic, (mode, group, end) in meta.items():  # ordering on the merged final state
            if end != "high":
                continue
            low_topic = topic.replace("_High_", "_Low_")
            high = leaves[topic]
            low = leaves.get(low_topic, self._current_int(low_topic))
            if low is None:
                continue
            ok = low + 1 <= high if group == "outside" else high >= low
            if not ok:
                raise _Reject("out_of_range", f"curve ordering violated for {topic}",
                              {"rule": "ordering", "key": topic})
        # a low leaf whose high leaf is omitted
        for topic, (mode, group, end) in meta.items():
            if end != "low":
                continue
            high_topic = topic.replace("_Low_", "_High_")
            if high_topic in leaves:
                continue
            high = self._current_int(high_topic)
            if high is None:
                continue
            low = leaves[topic]
            ok = low + 1 <= high if group == "outside" else high >= low
            if not ok:
                raise _Reject("out_of_range", f"curve ordering violated for {topic}",
                              {"rule": "ordering", "key": topic})
        plan.readback = list(plan.entry.get("readback") or [])
        plan.compare = "curve_leaf"
        plan.expected = dict(leaves)
        plan.payload = encode("json", value)

    def _current_int(self, topic: str) -> int | None:
        tv = self._state.values.get(topic)
        if tv is None or not tv.valid or isinstance(tv.value, (str, type(None))):
            return None
        return int(tv.value)

    # ------------------------------------------------------------- step 2

    def _gates(self, plan: _Plan, confirm: bool) -> None:
        if not self._mqtt.connected:
            raise _Reject("broker_disconnected", "the MQTT broker is not connected", status=503)
        if self._state.device_online != "online":
            raise _Reject("device_offline", "the heat pump is not online")
        prefs = self._store.prefs_get()
        if prefs.get("write_lock"):
            raise _Reject("write_lock", "write lock is on")
        profile = self._profile_fn()
        if plan.pcb:
            if not prefs.get("pcb_enabled"):
                raise _Reject("pcb_disabled", "optional-PCB commands are disabled in the preferences")
            pcb = _field(profile, "pcb_emulation_active")
            if not (_usable(pcb) and pcb["value"] is True):
                raise _Reject("pcb_emulation_inactive", "optional-PCB emulation is not active")
        fw = _field(profile, "firmware")
        version, assumed = parse_firmware(fw["value"] if fw else None)
        need, _ = parse_firmware(plan.entry["min_firmware"])
        if need > version:
            raise _Reject("firmware_too_old",
                          f"needs HeishaMon {plan.entry['min_firmware']}",
                          {"min_firmware": plan.entry["min_firmware"], "assumed": assumed})
        unknown = list(plan.unknown_fields)
        for path in (plan.entry.get("applicability") or {}).get("requires", []):
            if not _usable(_field(profile, path)):
                unknown.append(path)
        if unknown and not plan.entry.get("safe_under_unknown"):
            raise _Reject("profile_unknown", f"profile field {unknown[0]} is unknown or stale",
                          {"field": unknown[0]})
        if plan.read_only:
            raise _Reject("read_only_value", f"{plan.value} cannot be written")
        if plan.risky and not confirm:
            raise _Reject("confirm_required", "this command needs confirm: true")
        if not self._store.protected_budget_ok():
            raise _Reject("storage_unavailable", "protected-record budget is full", status=503)

    def _rejected(self, name: str, r: _Reject, now: int) -> tuple[int, dict]:
        self._store.append_event(now, "command_rejected", {"name": name, "error": r.code})
        return r.status, error_body(r.code, r.message, r.detail)

    # ------------------------------------------------------------- step 3

    def _live_match(self, plan: _Plan, topic: str, expected, now: int) -> bool:
        tv = self._state.values.get(topic)
        return bool(
            tv is not None and tv.valid and not tv.retained_only
            and now - tv.last_seen <= NOOP_FRESH_MS
            and values_match(plan.compare, expected, tv.value)
        )

    def _drop_matching(self, plan: _Plan, now: int) -> tuple[_Plan, dict[str, int]]:
        if plan.name == "SetCurves":
            keep = {t: v for t, v in plan.expected.items() if not self._live_match(plan, t, v, now)}
            plan.expected = keep
            if keep:
                plan.payload = encode("json", _nest_curve_leaves(keep))
            return plan, dict(keep)
        for topic, exp in plan.expected.items():
            if self._live_match(plan, topic, exp, now):
                plan.expected = {}
        return plan, {}

    def _noop(self, plan: _Plan, now: int) -> tuple[int, dict]:
        rec = self._record(plan, now, {})
        rec.update(status="noop", published_ts=None, attempts=0)
        try:
            self._store.append_command(dict(rec))
        except StorageUnavailable:
            return self._rejected(plan.name, _Reject("storage_unavailable", "protected-record budget is full",
                                                     status=503), now)
        self._push(rec)
        return 200, self.to_api(rec)

    # ------------------------------------------------------------- step 5

    def _record(self, plan: _Plan, now: int, sent_keys: dict[str, int]) -> dict:
        prev = None
        if plan.name == "SetCurves":
            prev = json.dumps({t: self._raw(t) for t in sent_keys}, separators=(",", ":")) if sent_keys else None
        elif plan.readback:
            prev = self._raw(plan.readback[0])
        return {
            "uuid": str(uuidlib.uuid4()), "name": plan.name, "payload": plan.payload,
            "retained": plan.retained, "class": plan.cls,
            "status": "pending" if plan.cls == "setting" else "sent",
            "submitted_ts": now, "published_ts": now, "confirmed_ts": None, "attempts": 1,
            "prev_value": prev, "detail": None,
            "keys": {t: {"expected": v, "status": "pending"} for t, v in sent_keys.items()} or None,
        }

    def _raw(self, topic: str) -> str | None:
        tv = self._state.values.get(topic)
        return tv.raw if tv is not None else None

    async def _publish(self, plan: _Plan, payload: str) -> None:
        if plan.kind == "input":
            if plan.cls == "retained_exception":
                await self._mqtt.publish_retained_exception(plan.name, payload)
            else:
                await self._mqtt.publish_input(plan.name, payload)
        else:
            await self._mqtt.publish_command(plan.name, payload)

    # ------------------------------------------------------------- step 6

    def _try_confirm(self, f: _Flight, receipt: Receipt) -> None:
        if not receipt.valid:
            return
        keys = f.rec["keys"]
        if keys is not None:
            slot = keys.get(receipt.topic)
            if slot is None or slot["status"] == "confirmed":
                return
            if not values_match("curve_leaf", slot["expected"], receipt.value):
                return
            slot["status"] = "confirmed"
            if all(s["status"] == "confirmed" for s in keys.values()):
                self._finish(f, "confirmed", None, receipt.ts)
            else:
                self._update(f, keys=keys)
            return
        expected = f.plan.expected.get(receipt.topic)
        if expected is not None and values_match(f.plan.compare, expected, receipt.value):
            self._finish(f, "confirmed", None, receipt.ts)

    # ------------------------------------------------------------- steps 7–8

    async def _retry(self, f: _Flight) -> None:
        f.retry_handle = None
        if f.done:
            return
        now = self._clock.now_ms()
        try:
            # the meaning check comes first: a changed control mode would otherwise surface as a
            # misleading range error on the old value
            probe = replace(f.plan, meaning={}, unknown_fields=[])
            self._resolve_range(probe, self._profile_fn())
            if not probe.unknown_fields and probe.meaning != f.plan.meaning:
                raise _Reject("meaning_changed", "the control mode changed since submission",
                              {"was": f.plan.meaning, "now": probe.meaning})
            plan = self._plan(f.plan.name, f.plan.value)  # steps 1 and 2 again, in full
            self._gates(plan, f.confirm)
        except _Reject as r:
            self._fail_streak.clear()  # failed for a reason other than "no change"
            self._finish(f, "failed", r.code, now, fail_keys=True)
            return
        payload = f.plan.payload
        keys = f.rec["keys"]
        if keys is not None:
            pending = {t: s["expected"] for t, s in keys.items() if s["status"] == "pending"}
            payload = encode("json", _nest_curve_leaves(pending))
        try:
            await self._publish(f.plan, payload)
        except PublishError:
            self._fail_streak.clear()
            self._finish(f, "failed", "broker_disconnected", self._clock.now_ms(), fail_keys=True)
            return
        if f.done:  # confirmed while the retry was being published
            return
        self._update(f, status="retried", attempts=2)

    async def _terminal(self, f: _Flight) -> None:
        f.terminal_handle = None
        if f.done:
            return
        now = self._clock.now_ms()
        failed = [t for t, e in f.plan.expected.items()
                  if f.rec["keys"] is None or f.rec["keys"][t]["status"] == "pending"]
        detail = json.dumps({t: self._raw(t) for t in failed}, separators=(",", ":"))
        self._finish(f, "failed", detail, now, fail_keys=True)
        online = self._state.device_online == "online"
        if online and not f.changed_seen and f.other_changed:
            self._note_no_change_failure(now)
        else:
            self._fail_streak.clear()

    # ------------------------------------------------------------- bookkeeping

    def _update(self, f: _Flight, **fields) -> None:
        f.rec.update(fields)
        self._store.update_command(f.rec["uuid"], dict(fields))
        self._push(f.rec)

    def _finish(self, f: _Flight, status: str, detail: str | None, ts: int, fail_keys: bool = False) -> None:
        if f.done:
            return
        f.done = True
        self._flights.pop(f.rec["uuid"], None)
        for h in (f.retry_handle, f.terminal_handle):
            if h is not None:
                h.cancel()
        f.retry_handle = f.terminal_handle = None
        fields: dict[str, Any] = {"status": status}
        if detail is not None:
            fields["detail"] = detail
        if status == "confirmed":
            fields["confirmed_ts"] = ts
        keys = f.rec["keys"]
        if keys is not None:
            if status == "failed" and fail_keys:
                for s in keys.values():
                    if s["status"] == "pending":
                        s["status"] = "failed"
            fields["keys"] = keys
        self._update(f, **fields)
        if status == "confirmed":
            self._fail_streak.clear()
            self._set_listen_only(False, ts)

    def _push(self, rec: dict) -> None:
        if self._on_status is None:
            return
        try:
            self._on_status(self.to_api(rec))
        except Exception:  # a broken subscriber must not break the command flow
            log.exception("command status callback failed")

    # ------------------------------------------------------------- listen-only

    def _note_no_change_failure(self, ts: int) -> None:
        self._fail_streak.append(ts)
        del self._fail_streak[:-LISTEN_ONLY_STREAK]
        if (len(self._fail_streak) == LISTEN_ONLY_STREAK
                and self._fail_streak[-1] - self._fail_streak[0] <= LISTEN_ONLY_WINDOW_MS):
            self._set_listen_only(True, ts)

    def _set_listen_only(self, on: bool, ts: int) -> None:
        if self.listen_only_suspected == on:
            return
        self.listen_only_suspected = on
        self._store.append_event(ts, "listen_only_suspected" if on else "listen_only_cleared", None)
        if self._on_listen_only is not None:
            try:
                self._on_listen_only(on)
            except Exception:
                log.exception("listen-only callback failed")


def _plain_number(d: Decimal):
    return int(d) if d == d.to_integral_value() else float(d)


def _curve_topic(zone: str, mode: str, group: str, end: str) -> str:
    return (f"main/{_CURVE_ZONES[zone]}_{_CURVE_MODES[mode]}_Curve_"
            f"{_CURVE_GROUPS[group]}_{_CURVE_ENDS[end]}_Temp")


_CURVE_TOPIC = re.compile(r"^main/Z([12])_(Heat|Cool)_Curve_(Target|Outside)_(High|Low)_Temp$")


def _nest_curve_leaves(leaves: dict[str, int]) -> dict:
    out: dict = {}
    for topic, v in leaves.items():
        z, m, g, e = _CURVE_TOPIC.match(topic).groups()
        out.setdefault(f"zone{z}", {}).setdefault(m.lower(), {}).setdefault(g.lower(), {})[e.lower()] = v
    return out
