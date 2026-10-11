"""MQTT connection, publish allowlist and ingest dispatch (spec §3, §4.1, §9)."""
import time
from collections.abc import Awaitable, Callable

from heishamon_dashboard.catalog import Catalog
from heishamon_dashboard.config import Config
from heishamon_dashboard.types import Clock, Message

_BACKOFF_START = 1.0
_BACKOFF_CAP = 60.0


class PublishError(ValueError):
    """A publish was rejected by the allowlist or because the broker is down."""


class Mqtt:
    """One broker session. The three publish methods are the only write paths."""

    def __init__(
        self,
        config: Config,
        catalog: Catalog,
        *,
        client_factory: Callable[[], object] | None = None,
        clock: Clock | None = None,
    ):
        self._config = config
        self._catalog = catalog
        self._base = config.mqtt_base_topic
        self._client = None
        self._client_factory = client_factory
        self._clock = clock
        self._sleep: Callable[[float], Awaitable[None]] = _async_sleep
        self.connected = False
        self._stopped = False
        self._on_message: list[Callable[[Message], None]] = []
        self._on_connect: list[Callable[[], None]] = []
        self._on_disconnect: list[Callable[[], None]] = []

    def attach(self, client) -> None:
        """Use an already connected client (tests). Does not start the read loop."""
        self._client = client
        self.connected = True

    def stop(self) -> None:
        self._stopped = True

    def on_message(self, callback: Callable[[Message], None]) -> Callable[[Message], None]:
        self._on_message.append(callback)
        return callback

    def on_broker_connect(self, callback: Callable[[], None]) -> Callable[[], None]:
        self._on_connect.append(callback)
        return callback

    def on_broker_disconnect(self, callback: Callable[[], None]) -> Callable[[], None]:
        self._on_disconnect.append(callback)
        return callback

    async def publish_command(self, name: str, payload: str) -> None:
        """Publish `<base>/commands/<name>`, always non-retained, QoS 0."""
        if self._catalog.command(name) is None:
            raise PublishError(f"topic not allowed for publish_command: {name}")
        await self._publish(f"commands/{name}", payload, retain=False)

    async def publish_retained_exception(self, path: str, payload: str) -> None:
        """Publish one of the six retained paths (S0 totals and OpenTherm bounds)."""
        entry = self._catalog.input(path)
        if entry is None or entry.get("class") != "retained_exception" or not entry.get("retain"):
            raise PublishError(f"topic not allowed for publish_retained_exception: {path}")
        await self._publish(path, payload, retain=True)

    async def publish_input(self, path: str, payload: str) -> None:
        """Publish a non-bound `opentherm/read/<name>` input, always non-retained."""
        entry = self._catalog.input(path)
        if entry is None or entry.get("class") != "input" or entry.get("retain"):
            raise PublishError(f"topic not allowed for publish_input: {path}")
        await self._publish(path, payload, retain=False)

    async def run(self) -> None:
        """Connect, subscribe to `<base>/#`, and reconnect with backoff.

        Backoff starts at 1 s and doubles, capped at 60 s. A successful subscribe
        resets it to 1 s.
        """
        factory = self._client_factory or self._default_factory
        delay = _BACKOFF_START
        while not self._stopped:
            try:
                async with factory() as client:
                    self._client = client
                    await client.subscribe(f"{self._base}/#")
                    self.connected = True
                    delay = _BACKOFF_START
                    for callback in list(self._on_connect):
                        callback()
                    try:
                        stream = client.messages
                        if callable(stream):
                            stream = stream()
                        async for raw in stream:
                            if self._stopped:
                                break
                            self._dispatch(raw)
                    finally:
                        if self.connected:
                            self.connected = False
                            for callback in list(self._on_disconnect):
                                callback()
                        self._client = None
            except Exception:
                self.connected = False
                self._client = None
            if self._stopped:
                break
            await self._sleep(delay)
            delay = min(delay * 2, _BACKOFF_CAP)

    async def _publish(self, relative: str, payload: str, *, retain: bool) -> None:
        if not self.connected or self._client is None:
            raise PublishError("broker disconnected")
        await self._client.publish(f"{self._base}/{relative}", payload, qos=0, retain=retain)

    def _dispatch(self, raw) -> None:
        topic = str(raw.topic)
        prefix = self._base + "/"
        if not topic.startswith(prefix):
            return
        payload = raw.payload
        if isinstance(payload, (bytes, bytearray)):
            payload = bytes(payload).decode("utf-8", errors="replace")
        else:
            payload = str(payload)
        ts = self._clock.now_ms() if self._clock is not None else int(time.time() * 1000)
        message = Message(
            topic=topic[len(prefix):],
            payload=payload,
            retained=bool(getattr(raw, "retain", False)),
            ts=ts,
        )
        for callback in self._on_message:
            callback(message)

    def _default_factory(self):
        import aiomqtt

        kwargs = {}
        if self._config.mqtt_user is not None:
            kwargs["username"] = self._config.mqtt_user
        if self._config.mqtt_password is not None:
            kwargs["password"] = self._config.mqtt_password
        if self._config.mqtt_tls:
            kwargs["tls_params"] = aiomqtt.TLSParameters()
        return aiomqtt.Client(self._config.mqtt_host, port=self._config.mqtt_port, **kwargs)


async def _async_sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
