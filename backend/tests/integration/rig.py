"""Shared integration rig: an embedded amqtt broker, the app in-process on a fake clock, and a
subprocess runner for `python -m heishamon_dashboard`.

Everything binds to 127.0.0.1 on an ephemeral port. Nothing here reads `.env` or contacts another host.
"""
import asyncio
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
from amqtt.broker import Broker

from heishamon_dashboard import config as config_mod
from heishamon_dashboard.app import build

BASE = "panasonic_heat_pump"
ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
FIXTURES = ROOT / "backend" / "tests" / "fixtures"
# midnight-aligned UTC day, so the §5.4 clock times (hh:mm:ss) map onto whole minutes
DAY = 1_791_000_000_000 // 86_400_000 * 86_400_000


def hms(h, m=0, s=0):
    """Unix ms of `hh:mm:ss` on the test day."""
    return DAY + ((h * 60 + m) * 60 + s) * 1000


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for(predicate, timeout=10.0, step=0.02, what="condition"):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(step)
    raise AssertionError(f"{what} not reached within {timeout} s")


class FakeClock:
    """`step` > 0 makes every read advance the clock, so receipts are strictly after publishes."""

    def __init__(self, t=hms(0), step=0):
        self.t = t
        self.step = step

    def now_ms(self):
        value = self.t
        self.t += self.step
        return value


class EmbeddedBroker:
    """An amqtt broker plus one publisher and one `commands/#` listener, all on a private loop."""

    def __init__(self, base=BASE):
        self.base = base
        self.port = free_port()
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.commands: list[tuple[str, str]] = []  # (name, payload) as the broker received them
        self.on_command = None  # callable(name, payload), runs on the broker loop
        self.sent: dict[str, int] = {}
        self.last_topic: str | None = None
        self._lock = threading.Lock()
        self._tasks = []

    # -- lifecycle
    def start(self):
        self.thread.start()
        self._run(self._start())
        return self

    def stop(self):
        try:
            self._run(self._stop())
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=10)

    def _run(self, coro, timeout=30):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    async def _start(self):
        import aiomqtt

        config = {
            "listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{self.port}"}},
            "sys_interval": 0,
            "auth": {"allow-anonymous": True, "plugins": ["auth_anonymous"]},
            "topic-check": {"enabled": False},
        }
        self.broker = Broker(config)
        await self.broker.start()
        self.queue = asyncio.Queue()
        self._pub = aiomqtt.Client("127.0.0.1", port=self.port)
        await self._pub.__aenter__()
        self._cmd = aiomqtt.Client("127.0.0.1", port=self.port)
        await self._cmd.__aenter__()
        await self._cmd.subscribe(f"{self.base}/commands/#")
        self._tasks = [asyncio.create_task(self._pump()), asyncio.create_task(self._listen())]

    async def _stop(self):
        """Tear down piece by piece; each step is bounded so a stuck socket cannot hang the suite."""

        async def bounded(awaitable):
            try:
                await asyncio.wait_for(awaitable, 5)
            except (asyncio.CancelledError, Exception):
                pass

        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            await bounded(task)
        for client in (self._cmd, self._pub):
            await bounded(client.__aexit__(None, None, None))
        await bounded(self.broker.shutdown())

    async def _pump(self):
        while True:
            topic, payload, retain = await self.queue.get()
            try:
                await self._pub.publish(f"{self.base}/{topic}", payload, qos=1, retain=retain)
            finally:
                self.queue.task_done()

    async def _listen(self):
        prefix = f"{self.base}/commands/"
        async for message in self._cmd.messages:
            topic = str(message.topic)
            if not topic.startswith(prefix):
                continue
            name, payload = topic[len(prefix):], bytes(message.payload).decode()
            self.commands.append((name, payload))
            if self.on_command is not None:
                self.on_command(name, payload)

    # -- publishing (thread-safe; ordered through one connection)
    def publish(self, topic: str, payload, retain: bool = False):
        with self._lock:
            self.sent[topic] = self.sent.get(topic, 0) + (1 if self.live else 0)  # only live publishes are counted
            self.last_topic = topic
        self.loop.call_soon_threadsafe(self.queue.put_nowait, (topic, str(payload), retain))

    live = False  # set once the app is subscribed: from then on every publish is delivered live

    def drain(self):
        self._run(self.queue.join())

    def retained_topics(self, prefix="commands/") -> list[str]:
        """Topics the broker holds as retained under `<base>/<prefix>` (read from its retained store)."""

        async def read():
            return sorted(t for t in self.broker._retained_messages if t.startswith(f"{self.base}/{prefix}"))

        return self._run(read())


def make_env(tmp_path, broker_port, http_port=None, **extra):
    env = {
        "MQTT_HOST": "127.0.0.1",
        "MQTT_PORT": str(broker_port),
        "DATA_DIR": str(tmp_path / "data"),
        "FLUSH_INTERVAL_SECONDS": "86400",
    }
    if http_port is not None:
        env["HTTP_PORT"] = str(http_port)
    env.update({k: str(v) for k, v in extra.items()})
    return env


class AppRig:
    """The real app (real aiomqtt) in this process, on a fake clock, against an embedded broker.

    Live messages are delivered with the retain flag cleared by the broker, so retained snapshots
    must be published *before* `AppRig` is entered.
    """

    def __init__(self, tmp_path, broker: EmbeddedBroker, *, clock=None, scheduler=None, **env):
        from fastapi.testclient import TestClient

        self.broker = broker
        self.clock = clock or FakeClock()
        self.data_dir = tmp_path / "data"
        self.config = config_mod.load(make_env(tmp_path, broker.port, **env))
        self.app = build(self.config, None, self.clock, scheduler=scheduler, static_dir=tmp_path / "no-dist",
                         tick_interval=3600.0)
        self.svc = self.app.state.services
        self.seen: dict[str, int] = {}
        self.svc.mqtt.on_message(self._count)
        self.client = TestClient(self.app)

    def _count(self, message):
        if not message.retained:
            self.seen[message.topic] = self.seen.get(message.topic, 0) + 1

    def __enter__(self):
        self.client.__enter__()
        wait_for(lambda: self.svc.mqtt.connected, what="broker connection")
        self.broker.live = True
        return self

    def __exit__(self, *exc):
        self.broker.live = False
        return self.client.__exit__(*exc)

    # -- driving
    def call(self, fn, *args):
        """Run `fn` on the app's event loop (the services are not thread-safe)."""
        return self.client.portal.call(fn, *args)

    def sync(self, timeout=15.0):
        """Wait until the app has processed everything published so far."""
        self.broker.drain()
        topic = self.broker.last_topic
        if topic is None:
            return
        want = self.broker.sent[topic]
        wait_for(lambda: self.seen.get(topic, 0) >= want, timeout, what=f"receipt of {topic}")

    def feed(self, topic, payload, at=None, retain=False):
        if at is not None:
            self.clock.t = at
        self.broker.publish(topic, payload, retain)
        self.sync()

    def feed_many(self, items, at=None):
        if at is not None:
            self.clock.t = at
        for topic, payload in items:
            self.broker.publish(topic, payload, False)
        self.sync()

    def tick(self, at=None):
        if at is not None:
            self.clock.t = at
        self.call(self.svc.tick)

    def flush(self, at=None, timeout=20.0):
        if at is not None:
            self.clock.t = at
        when = self.clock.t
        response = self.client.post("/api/system/flush", json={})
        assert response.status_code == 202, response.text
        wait_for(lambda: self.system()["last_flush_ts"] == when, timeout, what="flush")
        assert self.system()["last_flush_ok"] is True

    def system(self):
        return self.client.get("/api/system").json()

    def state(self):
        return self.client.get("/api/state").json()

    def db(self) -> sqlite3.Connection:
        """A read-only view of the app's database (WAL allows a concurrent reader)."""
        conn = sqlite3.connect(f"file:{self.data_dir / 'heishamon.db'}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def rollups(self, topic, table="rollup_1m"):
        with self.db() as conn:
            rows = conn.execute(
                f"SELECT bucket, covered_seconds, avg FROM {table} r JOIN topics t ON t.id = r.topic_id "
                "WHERE t.key = ? ORDER BY bucket", (topic,)).fetchall()
        return [(r["bucket"], r["covered_seconds"], r["avg"]) for r in rows]

    def outages(self, kind=None, topic=None):
        with self.db() as conn:
            rows = conn.execute(
                "SELECT o.start_ts, o.end_ts, o.kind, t.key FROM outages o LEFT JOIN topics t ON t.id = o.topic_id "
                "ORDER BY o.start_ts").fetchall()
        return [(r[0], r[1], r[2], r[3]) for r in rows if (kind is None or r[2] == kind) and (topic is None or r[3] == topic)]


class SubprocessApp:
    """`python -m heishamon_dashboard` with an explicit, minimal environment (no `.env`)."""

    def __init__(self, tmp_path, broker_port, **extra):
        self.http_port = free_port()
        self.tmp_path = tmp_path
        env = make_env(tmp_path, broker_port, self.http_port, STATIC_DIR=tmp_path / "no-dist", **extra)
        env.update({
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(tmp_path),
            "PYTHONPATH": str(ROOT / "backend"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
        })
        self.env = env
        self.proc: subprocess.Popen | None = None
        self.log = tmp_path / f"app-{self.http_port}.log"
        self.url = f"http://127.0.0.1:{self.http_port}"

    def start(self, ready_timeout=10.0):
        with open(self.log, "wb") as out:
            self.proc = subprocess.Popen([sys.executable, "-m", "heishamon_dashboard"], env=self.env,
                                         cwd=str(self.tmp_path), stdout=out, stderr=subprocess.STDOUT)

        def ready():
            assert self.proc.poll() is None, f"app exited early: {self.log.read_text()}"
            try:
                return httpx.get(f"{self.url}/api/system", timeout=1.0).status_code == 200
            except httpx.HTTPError:
                return False

        wait_for(ready, ready_timeout, step=0.1, what="GET /api/system")
        return self

    def get(self, path, **params):
        return httpx.get(f"{self.url}{path}", params=params, timeout=10.0)

    def terminate(self, kill_after=65.0):
        """SIGTERM; returns (returncode, seconds taken). Kills the child after `kill_after` s."""
        started = time.monotonic()
        self.proc.send_signal(signal.SIGTERM)
        try:
            code = self.proc.wait(timeout=kill_after)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            code = self.proc.wait()
        return code, time.monotonic() - started

    def cleanup(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=65)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()


def load_sim_modules():
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    import presets
    import simulator

    return simulator, presets
