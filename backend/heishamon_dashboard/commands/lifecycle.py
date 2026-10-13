"""Flight lifecycle: the only owner of flights, timers, supersede, retry, confirm and terminal status
(spec §6 steps 5–10)."""
import asyncio
import json
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Any, Protocol

from heishamon_dashboard.commands.gates import DEFAULT_RATE_MAX, DEFAULT_RATE_WINDOW_S, check_rate
from heishamon_dashboard.commands.planner import (
    Plan, Reject, curve_meaning, curve_zone_mode, encode_pending, num_equal, resolve_range, values_match,
)
from heishamon_dashboard.commands.transport import PublishError, Transport
from heishamon_dashboard.types import Clock, Receipt

log = logging.getLogger(__name__)

RETRY_AFTER_MS = 10_000
TERMINAL_AFTER_MS = 20_000
EEPROM_WINDOW_MS = 3_600_000
EEPROM_WARN_COUNT = 3
LISTEN_ONLY_STREAK = 3
LISTEN_ONLY_WINDOW_MS = 30 * 60_000


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


@dataclass
class Flight:
    rec: dict  # store-form record
    plan: Plan
    confirm: bool
    payload_keys: dict[str, int]  # SetCurves: sent key -> expected; empty otherwise
    retry_handle: Any = None
    terminal_handle: Any = None
    last_publish_ts: int = 0  # refreshed on every publish attempt, retries included
    changed_seen: bool = False
    other_changed: bool = False
    done: bool = False

    @property
    def topics(self) -> set[str]:
        return set(self.plan.expected)


class Lifecycle:
    def __init__(
        self,
        store,
        state,
        clock: Clock,
        scheduler: Scheduler,
        transport: Transport,
        profile_fn: Callable[[], dict],
        replan: Callable[[str, Any], Plan],
        regate: Callable[[Plan, bool], None],
        on_status: Callable[[dict], None] | None = None,
        on_listen_only: Callable[[bool], None] | None = None,
        rate_max: int = DEFAULT_RATE_MAX,
        rate_window_s: int = DEFAULT_RATE_WINDOW_S,
    ):
        self._store = store
        self._state = state
        self._clock = clock
        self._scheduler = scheduler
        self._transport = transport
        self._profile_fn = profile_fn
        self._replan = replan
        self._regate = regate
        self.on_status = on_status
        self._on_listen_only = on_listen_only
        self.flights: dict[str, Flight] = {}
        self.rate_max = rate_max
        self.rate_window_s = rate_window_s
        self._publishes: dict[str, deque[int]] = {}  # command name -> publish-attempt timestamps
        self._fail_streak: list[int] = []
        self.listen_only_suspected = False

    # ------------------------------------------------------------------ queries

    def recent_change_count(self, name: str, now: int | None = None) -> int:
        """Real publish attempts of one command in the last 60 minutes (retries and superseded included)."""
        now = self._clock.now_ms() if now is None else now
        return sum(1 for ts in self._publishes.get(name, ()) if ts > now - EEPROM_WINDOW_MS)

    def eeprom_warning(self, name: str, now: int | None = None) -> bool:
        return self.recent_change_count(name, now) >= EEPROM_WARN_COUNT

    def to_api(self, record: dict) -> dict:
        out = dict(record)
        out["id"] = out.pop("uuid")
        out["eeprom_warning"] = self.eeprom_warning(record["name"])
        return out

    def rate_check(self, name: str, now: int) -> None:
        check_rate(name, self._publishes.get(name, ()), now, self.rate_max, self.rate_window_s)

    def identical_flight(self, plan: Plan) -> Flight | None:
        """C4a: a non-terminal flight already carries exactly these values."""
        if plan.cls != "setting" or not plan.expected:
            return None
        for f in self.flights.values():
            if f.plan.name == plan.name and not f.done and all(
                    t in f.plan.expected and num_equal(v, f.plan.expected[t])
                    for t, v in plan.expected.items()):
                return f
        return None

    def conflicting_flights(self, plan: Plan) -> list[Flight]:
        """In-flight commands whose expected keys intersect this plan's with a different value."""
        return [f for f in self.flights.values()
                if not f.done and any(t in f.plan.expected and not num_equal(v, f.plan.expected[t])
                                      for t, v in plan.expected.items())]

    def inflight_curve_leaves(self) -> dict[str, int]:
        """Unconfirmed leaves of live SetCurves flights."""
        out: dict[str, int] = {}
        for f in self.flights.values():
            if f.plan.name != "SetCurves" or f.done:
                continue
            for t, v in f.plan.expected.items():
                if f.rec["keys"] is None or f.rec["keys"][t]["status"] == "pending":
                    out[t] = v
        return out

    # ------------------------------------------------------------------ start

    def register(self, flight: Flight) -> None:
        if flight.plan.cls == "setting":
            self.flights[flight.rec["uuid"]] = flight

    async def publish(self, plan: Plan, payload: str, flight: Flight) -> None:
        now = self._clock.now_ms()
        flight.last_publish_ts = now
        self._count_publish(plan.name, now)
        await self._transport.publish(plan, payload)

    def arm(self, flight: Flight) -> None:
        """Schedule the retry and the terminal check of a published setting."""
        if flight.plan.cls == "setting":
            flight.retry_handle = self._scheduler.call_later(
                RETRY_AFTER_MS / 1000, lambda f=flight: self._retry(f))
            flight.terminal_handle = self._scheduler.call_later(
                TERMINAL_AFTER_MS / 1000, lambda f=flight: self._terminal(f))

    def _count_publish(self, name: str, ts: int) -> None:
        q = self._publishes.setdefault(name, deque())
        q.append(ts)
        horizon = ts - max(EEPROM_WINDOW_MS, self.rate_window_s * 1000)
        while q and q[0] <= horizon:
            q.popleft()

    # ------------------------------------------------------------------ confirm

    def on_receipt(self, receipt: Receipt) -> None:
        """Feed every receipt (not only changes). Only live ones with ts ≥ published_ts confirm."""
        if receipt.retained:
            return
        for f in list(self.flights.values()):
            if f.done or receipt.ts < (f.rec["published_ts"] or 0):
                continue
            if receipt.topic in f.topics:
                if receipt.changed:
                    f.changed_seen = True
                self._try_confirm(f, receipt)
            elif receipt.changed and receipt.qualifying:
                f.other_changed = True

    def _try_confirm(self, f: Flight, receipt: Receipt) -> None:
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
                self.finish(f, "confirmed", None, receipt.ts)
            else:
                self._update(f, keys=keys)
            return
        expected = f.plan.expected.get(receipt.topic)
        if expected is not None and values_match(f.plan.compare, expected, receipt.value):
            self.finish(f, "confirmed", None, receipt.ts)

    # ------------------------------------------------------------------ retry / terminal

    async def _retry(self, f: Flight) -> None:
        f.retry_handle = None
        if f.done:
            return
        now = self._clock.now_ms()
        try:
            # the meaning check comes first: a changed control mode would otherwise surface as a
            # misleading range error on the old value
            probe = replace(f.plan, meaning={}, unknown_fields=[])
            if f.plan.name == "SetCurves":
                probe.meaning = curve_meaning(self._profile_fn(), {curve_zone_mode(t) for t in f.plan.expected})
                changed = any(v is not None and f.plan.meaning.get(k) is not None and v != f.plan.meaning[k]
                              for k, v in probe.meaning.items())
            else:
                resolve_range(probe, self._profile_fn())
                changed = not probe.unknown_fields and probe.meaning != f.plan.meaning
            if changed:
                raise Reject("meaning_changed", "the control mode changed since submission",
                             {"was": f.plan.meaning, "now": probe.meaning})
            plan = self._replan(f.plan.name, f.plan.value)  # steps 1 and 2 again, in full
            self._regate(plan, f.confirm)
        except Reject as r:
            self._fail_streak.clear()  # failed for a reason other than "no change"
            self.finish(f, "failed", r.code, now, fail_keys=True)
            return
        try:
            self.rate_check(f.plan.name, now)
        except Reject as r:
            self.finish(f, "failed", r.code, now, fail_keys=True)
            return
        payload = f.plan.payload
        keys = f.rec["keys"]
        if keys is not None:
            pending = {t: s["expected"] for t, s in keys.items() if s["status"] == "pending"}
            payload = encode_pending(pending)
        try:
            await self.publish(f.plan, payload, f)
        except PublishError:
            self._fail_streak.clear()
            self.finish(f, "failed", "broker_disconnected", self._clock.now_ms(), fail_keys=True)
            return
        if f.done:  # confirmed while the retry was being published
            return
        self._update(f, status="retried", attempts=2)

    async def _terminal(self, f: Flight) -> None:
        f.terminal_handle = None
        if f.done:
            return
        now = self._clock.now_ms()
        failed = [t for t, e in f.plan.expected.items()
                  if f.rec["keys"] is None or f.rec["keys"][t]["status"] == "pending"]
        detail = json.dumps({t: self._raw(t) for t in failed}, separators=(",", ":"))
        self.finish(f, "failed", detail, now, fail_keys=True)
        online = self._state.device_online == "online"
        if online and not f.changed_seen and f.other_changed:
            self._note_no_change_failure(now)
        else:
            self._fail_streak.clear()

    def _raw(self, topic: str) -> str | None:
        tv = self._state.values.get(topic)
        return tv.raw if tv is not None else None

    # ------------------------------------------------------------------ bookkeeping

    def _update(self, f: Flight, **fields) -> None:
        f.rec.update(fields)
        self._store.update_command(f.rec["uuid"], dict(fields))
        self.push(f.rec)

    def finish(self, f: Flight, status: str, detail: str | None, ts: int, fail_keys: bool = False) -> None:
        if f.done:
            return
        f.done = True
        self.flights.pop(f.rec["uuid"], None)
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

    def push(self, rec: dict) -> None:
        if self.on_status is None:
            return
        try:
            self.on_status(self.to_api(rec))
        except Exception:  # a broken subscriber must not break the command flow
            log.exception("command status callback failed")

    # ------------------------------------------------------------------ listen-only

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
