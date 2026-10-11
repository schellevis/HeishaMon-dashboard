"""Application wiring: MQTT → state → store/commands/derived → WebSocket, plus the flush timer.

`build(config, mqtt_factory, clock)` returns the ASGI app; tests inject a fake `mqtt_factory`
so nothing ever connects to a real broker.
"""
import asyncio
import contextlib
import json
import logging
import time
import uuid as uuidlib
from pathlib import Path

from fastapi import FastAPI

from heishamon_dashboard import api, catalog as catalog_mod
from heishamon_dashboard.commands import AsyncioScheduler, CommandService
from heishamon_dashboard.config import Config
from heishamon_dashboard.derived import EventDetector
from heishamon_dashboard.firmware import parse_firmware
from heishamon_dashboard.mqtt import Mqtt
from heishamon_dashboard.origin import OriginMiddleware, OriginPolicy
from heishamon_dashboard.profile import derive
from heishamon_dashboard.state import State
from heishamon_dashboard.store import Store
from heishamon_dashboard.types import Message

log = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).parent / "catalog.json"
DEFAULT_STATIC_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"
CLIENT_QUEUE_MAX = 2000


class SystemClock:
    def now_ms(self) -> int:
        return int(time.time() * 1000)


class Client:
    """One WebSocket subscriber: a bounded queue; `None` means "close, then resync"."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=CLIENT_QUEUE_MAX)


class Hub:
    """Fan-out of server messages. Only touched from the event loop thread."""

    def __init__(self) -> None:
        self.clients: set[Client] = set()

    def register(self) -> Client:
        client = Client()
        self.clients.add(client)
        return client

    def unregister(self, client: Client) -> None:
        self.clients.discard(client)

    def publish(self, message: dict) -> None:
        for client in list(self.clients):
            try:
                client.queue.put_nowait(message)
            except asyncio.QueueFull:
                # too slow: drop it; the client reconnects and `hello` resynchronises it
                self.clients.discard(client)
                while not client.queue.empty():
                    client.queue.get_nowait()
                client.queue.put_nowait(None)

    def close_all(self) -> None:
        for client in list(self.clients):
            self.clients.discard(client)
            while not client.queue.empty():
                client.queue.get_nowait()
            client.queue.put_nowait(None)


class _EventingStore:
    """Hands the commands service a store whose `append_event` also pushes to WebSocket clients."""

    def __init__(self, store: Store, emit):
        self._store = store
        self._emit = emit

    def append_event(self, ts, kind, detail=None):
        return self._emit(ts, kind, detail)

    def __getattr__(self, name):
        return getattr(self._store, name)


class Services:
    def __init__(self, config: Config, catalog, mqtt_factory=None, clock=None, scheduler=None,
                 store: Store | None = None, tick_interval: float = 1.0):
        self.config = config
        self.catalog = catalog
        self.clock = clock or SystemClock()
        self.tick_interval = tick_interval
        self.state = State(catalog)
        self.store = store or Store.from_config(config)
        self.hub = Hub()
        self.mqtt = Mqtt(config, catalog, client_factory=mqtt_factory, clock=self.clock)
        self.detector = EventDetector(self.emit_event)
        self.commands = CommandService(
            catalog, self.mqtt, self.state, _EventingStore(self.store, self.emit_event), self.clock,
            scheduler or AsyncioScheduler(), self.profile,
            on_status=self._on_command, on_listen_only=lambda on: None,
        )
        self.flushing = False
        self.ingest_dropped_total = 0
        self.next_flush_ms = self.clock.now_ms() + config.flush_interval_seconds * 1000
        self._profile_key: str | None = json.dumps(
            {k: v for k, v in self.profile().items() if k != "computed_at"}, sort_keys=True)
        self._tasks: set[asyncio.Task] = set()

        self.mqtt.on_message(self._on_message)
        self.mqtt.on_broker_connect(self._on_broker_connect)
        self.mqtt.on_broker_disconnect(self._on_broker_disconnect)
        self.state.on_online(self._on_device_online)
        self.state.on_offline(self._on_device_offline)

    # ----------------------------------------------------------------- helpers

    def next_seq(self) -> int:
        self.state.seq += 1
        return self.state.seq

    def stats(self) -> dict | None:
        tv = self.state.values.get("stats")
        if tv is None:
            return None
        try:
            data = json.loads(tv.raw)
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def firmware(self) -> str | None:
        stats = self.stats()
        version = stats.get("version") if stats else None
        return version if isinstance(version, str) and version else None

    def firmware_assumed(self) -> bool:
        return parse_firmware(self.firmware())[1]

    def profile(self) -> dict:
        return derive(
            self.state.values, self.clock.now_ms(), self.state.device_online, self.state.presence(),
            self.state.last_live_ts("optional/"), self.firmware(), self.catalog,
        )

    def refresh_profile(self) -> None:
        """Recompute the profile; push it over the WebSocket when something other than the
        timestamp changed."""
        profile = self.profile()
        key = json.dumps({k: v for k, v in profile.items() if k != "computed_at"}, sort_keys=True)
        if key == self._profile_key:
            return
        self._profile_key = key
        self.hub.publish({"type": "profile", "seq": self.next_seq(), "profile": profile})

    def emit_event(self, ts: int, kind: str, detail: dict | None = None) -> bool:
        ok = self.store.append_event(ts, kind, detail)
        if ok:
            self.hub.publish({"type": "event", "seq": self.next_seq(),
                              "event": {"ts": ts, "kind": kind, "detail": detail or {}}})
        return ok

    def publish_online(self, ts: int) -> None:
        self.hub.publish({"type": "online", "seq": self.next_seq(), "device": self.state.device_online,
                          "broker": self.mqtt.connected, "ts": ts})

    # --------------------------------------------------------------- callbacks

    def _on_message(self, message: Message) -> None:
        try:
            self.ingest(message)
        except Exception:  # an ingest error must never take the MQTT loop down
            log.exception("ingest failed for %s", message.topic)

    def ingest(self, message: Message) -> None:
        receipt = self.state.ingest(message)
        if receipt is None:
            return
        # the value message is queued first so its seq stays ahead of anything this receipt causes
        self.hub.publish({"type": "value", "seq": self.state.seq, "topic": receipt.topic,
                          "value": receipt.value, "raw": receipt.raw, "ts": receipt.ts,
                          "retained": receipt.retained})
        self.store.observe(receipt)
        self.commands.on_receipt(receipt)
        self.detector.on_receipt(receipt)
        self.refresh_profile()

    def _on_command(self, command: dict) -> None:
        self.hub.publish({"type": "command", "seq": self.next_seq(), "command": command})

    def _on_broker_connect(self) -> None:
        now = self.clock.now_ms()
        self.state.broker_reconnect(now)
        self.detector.on_broker_connected(now)
        self.publish_online(now)

    def _on_broker_disconnect(self) -> None:
        now = self.clock.now_ms()
        self.detector.on_broker_disconnected(now)
        self.publish_online(now)

    def _on_device_online(self, ts: int) -> None:
        self.detector.on_device_online(ts)
        self.publish_online(ts)

    def _on_device_offline(self, start_ts: int) -> None:
        self.store.open_outage("offline", start_ts)
        self.detector.on_device_offline(start_ts)
        self.publish_online(start_ts)

    # ------------------------------------------------------------------ timer

    def tick(self) -> None:
        """One timer step: liveness timeout, profile staleness, and the flush schedule."""
        now = self.clock.now_ms()
        self.state.tick(now)
        self.refresh_profile()
        due = now >= self.next_flush_ms
        early = self.store.needs_flush and not self.store.failing
        if (due or early) and not self.flushing:
            self.start_flush(str(uuidlib.uuid4()))

    def start_flush(self, flush_id: str) -> bool:
        """Begin a flush in the background; False when one is already running."""
        if self.flushing:
            return False
        self.flushing = True
        task = asyncio.get_running_loop().create_task(self._flush_task(flush_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return True

    async def _flush_task(self, flush_id: str) -> None:
        try:
            now = self.clock.now_ms()
            self._record_ingest_dropped(now)
            liveness = self.state.liveness()
            result = await asyncio.to_thread(self.store.flush, now, liveness)
            self.next_flush_ms = self.clock.now_ms() + self.config.flush_interval_seconds * 1000
            self._publish_flush(now, flush_id, result)
        except Exception:
            log.exception("flush crashed")
        finally:
            self.flushing = False

    def flush_now(self) -> None:
        """Synchronous flush for shutdown."""
        now = self.clock.now_ms()
        self._record_ingest_dropped(now)
        result = self.store.flush(now, self.state.liveness())
        self._publish_flush(now, str(uuidlib.uuid4()), result)

    def _record_ingest_dropped(self, now: int) -> None:
        count = self.state.consume_ingest_dropped()
        if count:
            self.ingest_dropped_total += count
            self.emit_event(now, "ingest_dropped", {"count": count})

    def _publish_flush(self, now: int, flush_id: str, result) -> None:
        if result.ok:
            event = {"ts": now, "kind": "flush", "detail": {"samples": result.samples, "flush_id": flush_id}}
        else:
            event = {"ts": now, "kind": "flush_failed", "detail": {"error": result.error, "flush_id": flush_id}}
        self.hub.publish({"type": "event", "seq": self.next_seq(), "event": event})

    # -------------------------------------------------------------- lifecycle

    async def start(self) -> None:
        if not self.config.public_origins:
            log.warning("PUBLIC_ORIGINS is empty: the Host header is not checked. Set it to the "
                        "public origin of the dashboard (see the README).")
        self.store.startup(self.clock.now_ms())
        self._tasks.add(asyncio.get_running_loop().create_task(self.mqtt.run()))
        self._tasks.add(asyncio.get_running_loop().create_task(self._timer()))

    async def _timer(self) -> None:
        while True:
            await asyncio.sleep(self.tick_interval)
            try:
                self.tick()
            except Exception:
                log.exception("timer tick failed")

    async def stop(self) -> None:
        """Shutdown: stop MQTT and the timer, wait for a running flush, flush once more, close."""
        self.mqtt.stop()
        running = list(self._tasks)
        flushing = [t for t in running if t.get_coro().__name__ == "_flush_task"]
        for task in running:
            if task not in flushing:
                task.cancel()
        for task in running:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self.hub.close_all()
        try:
            self.flush_now()
        finally:
            self.store.close()


def build(config: Config, mqtt_factory=None, clock=None, *, scheduler=None,
          static_dir: str | Path | None = None, catalog=None, store: Store | None = None,
          tick_interval: float = 1.0) -> FastAPI:
    """Create the ASGI app. `mqtt_factory` builds the MQTT client (a fake in tests)."""
    cat = catalog or catalog_mod.load(CATALOG_PATH)
    services = Services(config, cat, mqtt_factory, clock, scheduler, store, tick_interval)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        await services.start()
        try:
            yield
        finally:
            await services.stop()

    app = FastAPI(title="HeishaMon dashboard", lifespan=lifespan, docs_url=None, redoc_url=None,
                  openapi_url=None)
    app.state.services = services
    api.register(app, services, Path(static_dir) if static_dir is not None else DEFAULT_STATIC_DIR)
    app.add_middleware(OriginMiddleware, policy=OriginPolicy(config.public_origins, config.allowed_origins))
    return app
