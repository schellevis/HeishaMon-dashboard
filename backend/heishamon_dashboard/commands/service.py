"""Command service facade: validation, gates, publish, confirmation, retry (spec §6, Appendix A.2)."""
import json
import uuid as uuidlib
from collections.abc import Callable

from heishamon_dashboard.catalog import Catalog
from heishamon_dashboard.commands.gates import (
    DEFAULT_RATE_MAX, DEFAULT_RATE_WINDOW_S, check_gates,
)
from heishamon_dashboard.commands.lifecycle import Flight, Lifecycle, Scheduler
from heishamon_dashboard.commands.planner import (
    Plan, Reject, drop_matching, error_body, plan_command, values_match,
)
from heishamon_dashboard.commands.transport import PublishError, Transport
from heishamon_dashboard.profile import STALE_MS
from heishamon_dashboard.store import StorageUnavailable
from heishamon_dashboard.types import Clock, Receipt

NOOP_FRESH_MS = 660_000


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
        rate_max: int = DEFAULT_RATE_MAX,
        rate_window_s: int = DEFAULT_RATE_WINDOW_S,
    ):
        self._catalog = catalog
        self._mqtt = mqtt
        self._state = state
        self._store = store
        self._clock = clock
        self._profile_fn = profile_fn
        self._life = Lifecycle(
            store, state, clock, scheduler, Transport(mqtt), profile_fn,
            replan=self._plan, regate=self._gates,
            on_status=on_status, on_listen_only=on_listen_only,
            rate_max=rate_max, rate_window_s=rate_window_s,
        )

    # ------------------------------------------------------- state owned by the lifecycle

    @property
    def _flights(self) -> dict[str, Flight]:
        return self._life.flights

    @property
    def _on_status(self):
        return self._life.on_status

    @_on_status.setter
    def _on_status(self, fn) -> None:
        self._life.on_status = fn

    @property
    def rate_max(self) -> int:
        return self._life.rate_max

    @rate_max.setter
    def rate_max(self, n: int) -> None:
        self._life.rate_max = n

    @property
    def rate_window_s(self) -> int:
        return self._life.rate_window_s

    @rate_window_s.setter
    def rate_window_s(self, n: int) -> None:
        self._life.rate_window_s = n

    @property
    def listen_only_suspected(self) -> bool:
        return self._life.listen_only_suspected

    # ------------------------------------------------------------------ public

    async def submit(self, name: str, value, confirm: bool) -> tuple[int, dict]:
        """Steps 1–10 of spec §6. Returns `(http_status, Command | Error)`."""
        life = self._life
        now = self._clock.now_ms()
        try:
            plan = self._plan(name, value)  # step 1
            self._gates(plan, confirm)  # step 2
        except Reject as r:
            return self._rejected(name, r, now)

        if (same := life.identical_flight(plan)) is not None:  # C4a: nothing to publish
            return 200, life.to_api(same.rec)
        conflicts = life.conflicting_flights(plan)  # step 3: flights whose value may still land
        sent_keys: dict[str, int] = {}
        if plan.cls == "setting":  # step 4: no-op check
            # a value equal to the read-back still publishes while a conflicting flight may land
            force = {t for f in conflicts for t in f.topics} & set(plan.expected)
            plan, sent_keys = drop_matching(
                plan, lambda p, t, v: self._live_match(p, t, v, now), force)
            if not plan.expected:
                return self._noop(plan, now)
        try:
            life.rate_check(plan.name, now)
        except Reject as r:
            return self._rejected(plan.name, r, now)

        record = self._record(plan, now, sent_keys)  # step 5: persist, then supersede
        try:
            self._store.append_command(dict(record))
        except StorageUnavailable:
            return self._rejected(name, Reject("storage_unavailable", "protected-record budget is full",
                                               status=503), now)
        for old in conflicts:
            life.finish(old, "superseded", None, now)
        flight = Flight(rec=record, plan=plan, confirm=confirm, payload_keys=sent_keys)
        life.register(flight)
        try:  # step 6: publish
            await life.publish(plan, plan.payload, flight)
        except PublishError as e:
            life.finish(flight, "failed", "broker_disconnected", self._clock.now_ms())
            return 503, error_body("broker_disconnected", str(e))
        life.arm(flight)
        life.push(record)
        return 201, life.to_api(record)

    def on_receipt(self, receipt: Receipt) -> None:
        self._life.on_receipt(receipt)

    def recent_change_count(self, name: str, now: int | None = None) -> int:
        return self._life.recent_change_count(name, now)

    def eeprom_warning(self, name: str, now: int | None = None) -> bool:
        return self._life.eeprom_warning(name, now)

    def to_api(self, record: dict) -> dict:
        return self._life.to_api(record)

    # ------------------------------------------------------------------ steps 1–2

    def _plan(self, name: str, value) -> Plan:
        return plan_command(self._catalog, name, value, self._profile_fn(), self._current_int,
                            self._life.inflight_curve_leaves())

    def _current_int(self, topic: str) -> int | None:
        tv = self._state.values.get(topic)
        if (tv is None or not tv.valid or isinstance(tv.value, (str, type(None)))
                or self._clock.now_ms() - tv.last_seen > STALE_MS):
            return None
        return int(tv.value)

    def _gates(self, plan: Plan, confirm: bool) -> None:
        check_gates(
            plan, confirm,
            connected=self._mqtt.connected, device_online=self._state.device_online,
            prefs=self._store.prefs_get(), profile=self._profile_fn(),
            budget_ok=self._store.protected_budget_ok(),
        )

    def _rejected(self, name: str, r: Reject, now: int) -> tuple[int, dict]:
        self._store.append_event(now, "command_rejected", {"name": name, "error": r.code})
        return r.status, error_body(r.code, r.message, r.detail)

    # ------------------------------------------------------------------ steps 3–5

    def _live_match(self, plan: Plan, topic: str, expected, now: int) -> bool:
        tv = self._state.values.get(topic)
        return bool(
            tv is not None and tv.valid and not tv.retained_only
            and now - tv.last_seen <= NOOP_FRESH_MS
            and values_match(plan.compare, expected, tv.value)
        )

    def _noop(self, plan: Plan, now: int) -> tuple[int, dict]:
        rec = self._record(plan, now, {})
        rec.update(status="noop", published_ts=None, attempts=0)
        try:
            self._store.append_command(dict(rec))
        except StorageUnavailable:
            return self._rejected(plan.name, Reject("storage_unavailable", "protected-record budget is full",
                                                    status=503), now)
        self._life.push(rec)
        return 200, self.to_api(rec)

    def _record(self, plan: Plan, now: int, sent_keys: dict[str, int]) -> dict:
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
