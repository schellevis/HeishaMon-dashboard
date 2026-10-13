"""HeishaMon topic-stream simulator (spec §10, Appendix A.1).

`Simulator` never opens a socket. The CLI (`python tools/simulator.py`) is the
only entry point that connects to a broker.

All value telemetry is published retained, as HeishaMon does: the initial snapshot, the
300 s full re-publish and the read-back after a command (a new subscriber therefore sees the
new value). The broker still delivers a live read-back to current subscribers with the retain
flag cleared, which is what spec §6 step 6 relies on. Commands stay non-retained; the LWT
`Online` heartbeat is not retained either.
`listen_only` drops command read-backs and keeps the telemetry stream, so the
device stays online while settings fail.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from presets import PROFILE_KEYS, resolve_preset  # noqa: E402

from heishamon_dashboard.catalog import load as load_catalog
from heishamon_dashboard.firmware import parse_firmware
from heishamon_dashboard.rules import load as load_rules

_MODES = {"echo", "drop", "drop_first", "partial", "listen_only"}
_ZONE = {"zone1": "Z1", "zone2": "Z2"}
_CURVE_MODES = ("heat", "cool")
_CURVE_GROUPS = ("target", "outside")
_CURVE_ENDS = ("high", "low")
def _catalog_path():
    import heishamon_dashboard.catalog as catalog_mod
    return Path(catalog_mod.__file__).parent / "catalog.json"


class SystemClock:
    def now_ms(self) -> int:
        return int(time.time() * 1000)


def _top_index(topic_id: str) -> int | None:
    if topic_id.startswith("TOP") and topic_id[3:].isdigit():
        return int(topic_id[3:])
    return None


def _default_payload(topic: dict) -> str:
    sentinels = set(topic.get("sentinels") or [])  # may hold fractional values such as -0.2
    if topic["kind"] == "enum":
        for key in sorted(topic.get("enum") or {}, key=lambda item: int(item)):
            number = int(key)
            if number not in sentinels:
                return str(number)
        return "0"
    if topic["kind"] == "text":
        return "ok"
    return "1" if 0 in sentinels else "0"


def curve_leaves(payload: str) -> list[tuple[str, str]]:
    """Map a SetCurves JSON object onto curve topic keys, in zone/mode/end order."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    rules = load_rules()
    leaves = []
    for zone_name, zone_label in _ZONE.items():
        zone = data.get(zone_name)
        if not isinstance(zone, dict):
            continue
        for mode_name in _CURVE_MODES:
            mode = zone.get(mode_name)
            if not isinstance(mode, dict):
                continue
            for group in _CURVE_GROUPS:
                body = mode.get(group)
                if not isinstance(body, dict):
                    continue
                for end in _CURVE_ENDS:
                    if end not in body:
                        continue
                    value = body[end]
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        continue
                    key = rules.leaf_topic(int(zone_label[1:]), mode_name, group, end.capitalize())
                    leaves.append((key, str(int(value))))
    return leaves


class Simulator:
    def __init__(self, preset, fault_modes, publish, clock, *, catalog=None, wait_s=5, republish_s=300):
        self.preset = resolve_preset(preset) if isinstance(preset, str) else preset
        self.fault_modes = dict(fault_modes or {})
        self.publish = publish
        self.clock = clock
        self.wait_ms = int(float(wait_s) * 1000)
        self.republish_ms = int(float(republish_s) * 1000)
        if self.wait_ms <= 0 or self.republish_ms <= 0:
            raise ValueError("wait_s and republish_s must be positive")
        self.catalog = catalog if catalog is not None else load_catalog(_catalog_path())
        self.values: dict[str, str] = {}
        self._started = False
        self._t0 = 0
        self._last_lwt = 0
        self._last_full = 0
        self._phases_done: set[int] = set()
        self._attempts: dict[str, int] = {}
        self._delayed: list[tuple[int, list[tuple[str, str]]]] = []

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        now = self.clock.now_ms()
        self._t0 = now
        self._last_lwt = now
        self._last_full = now
        self.values = self._initial_values()
        for topic in sorted(self.values):
            self.publish(topic, self.values[topic], True)
        self._publish_lwt()

    def tick(self) -> None:
        if not self._started:
            raise RuntimeError("Simulator.start() before tick()")
        now = self.clock.now_ms()
        self._apply_phases(now)
        self._flush_delayed(now)
        self._catch_up_lwt(now)
        self._catch_up_republish(now)

    def command(self, name: str, payload: str) -> None:
        mode = self.fault_modes.get(name, self.fault_modes.get("*", "echo"))
        kind, delay_s = _split_mode(mode)
        if kind in ("drop", "listen_only"):
            return
        if kind == "drop_first":
            self._attempts[name] = self._attempts.get(name, 0) + 1
            if self._attempts[name] == 1:
                return
            kind = "echo"
        leaves = self._readbacks(name, payload, partial=(kind == "partial"))
        if kind == "delay":
            due = self.clock.now_ms() + int(float(delay_s) * 1000)
            self._delayed.append((due, leaves))
            return
        self._emit(leaves, retained=True)

    def _initial_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for topic in self.catalog.topics:
            key = topic["key"]
            if not key.startswith("main/") or key in PROFILE_KEYS:
                continue
            if not self._topic_allowed(key, topic):
                continue
            values[key] = _default_payload(topic)
        for key, payload in self.preset.extra:
            if self._topic_allowed(key):
                values[key] = payload
        for key, payload in self.preset.topics.items():
            if self._topic_allowed(key):
                values[key] = str(payload)
        stats = dict(self.preset.stats) if self.preset.stats is not None else {"uptime": 1}
        values["stats"] = json.dumps(stats, separators=(",", ":"))
        return values

    def _topic_allowed(self, key: str, topic: dict | None = None) -> bool:
        if self.preset.block_opentherm_rw and (
            key.startswith("opentherm/read/") or key.startswith("opentherm/write/")
        ):
            return False
        meta = topic if topic is not None else self.catalog.topic(key)
        if meta is None:
            return True
        index = _top_index(meta["id"])
        if self.preset.max_top is not None and index is not None and index > self.preset.max_top:
            return False
        if self.preset.firmware_ceiling is not None:
            version, _assumed = parse_firmware(meta["min_firmware"])
            if version > self.preset.firmware_ceiling:
                return False
        return True

    def _readbacks(self, name: str, payload: str, partial: bool) -> list[tuple[str, str]]:
        command = self.catalog.command(name)
        if command is None:
            return []
        if command.get("type") == "json":
            leaves = [(t, p) for t, p in curve_leaves(payload) if self._topic_allowed(t)]
        else:
            leaves = [
                (topic, payload)
                for topic in command.get("readback") or []
                if self._topic_allowed(topic)
            ]
        if partial and leaves:
            leaves = leaves[:-1]
        return leaves

    def _emit(self, leaves, retained: bool) -> None:
        for topic, payload in leaves:
            self.values[topic] = payload
            self.publish(topic, payload, retained)

    def _apply_phases(self, now: int) -> None:
        for index, (offset, updates) in enumerate(self.preset.phases):
            if index in self._phases_done or now - self._t0 < offset:
                continue
            self._phases_done.add(index)
            changed = [
                (topic, str(payload))
                for topic, payload in updates.items()
                if self._topic_allowed(topic)
            ]
            self._emit(changed, retained=True)

    def _flush_delayed(self, now: int) -> None:
        ready = [item for item in self._delayed if item[0] <= now]
        self._delayed = [item for item in self._delayed if item[0] > now]
        for _due, leaves in ready:
            self._emit(leaves, retained=True)

    def _publish_lwt(self) -> None:
        self.publish("LWT", "Online", False)

    def _catch_up_lwt(self, now: int) -> None:
        steps = 0
        while now - self._last_lwt >= self.wait_ms and steps < 10_000:
            self._last_lwt += self.wait_ms
            self._publish_lwt()
            steps += 1

    def _catch_up_republish(self, now: int) -> None:
        steps = 0
        while now - self._last_full >= self.republish_ms and steps < 10_000:
            self._last_full += self.republish_ms
            for topic in sorted(self.values):
                self.publish(topic, self.values[topic], True)
            steps += 1


def _split_mode(mode: str) -> tuple[str, float | None]:
    if mode.startswith("delay:"):
        return "delay", float(mode.split(":", 1)[1])
    if mode not in _MODES:
        raise ValueError(f"unknown fault mode {mode!r}")
    return mode, None


def parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="simulator")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--preset", required=True)
    parser.add_argument("--base", default="panasonic_heat_pump")
    parser.add_argument("--fault", action="append", default=[], metavar="NAME=MODE")
    return parser.parse_args(argv)


def _faults(items) -> dict[str, str]:
    faults = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--fault must be NAME=MODE, got {item!r}")
        name, mode = item.split("=", 1)
        _split_mode(mode)
        faults[name] = mode
    return faults


async def _serve(args) -> None:
    import asyncio
    import aiomqtt

    faults = _faults(args.fault)
    try:
        preset = resolve_preset(args.preset)
    except KeyError as exc:
        raise SystemExit(str(exc)) from None
    queue: asyncio.Queue = asyncio.Queue()

    def publish(topic, payload, retained):
        queue.put_nowait((topic, str(payload), bool(retained)))

    sim = Simulator(preset, faults, publish, SystemClock())
    will = aiomqtt.Will(f"{args.base}/LWT", payload="Offline", retain=True)
    async with aiomqtt.Client(
        args.host, args.port, will=will, identifier="heishamon-dashboard-simulator"
    ) as client:
        sim.start()

        async def pump():
            while True:
                topic, payload, retained = await queue.get()
                await client.publish(f"{args.base}/{topic}", payload, retain=retained)

        async def ticks():
            while True:
                sim.tick()
                await asyncio.sleep(0.2)

        async def commands():
            await client.subscribe(f"{args.base}/commands/#")
            prefix = f"{args.base}/commands/"
            async for message in client.messages:
                topic = str(message.topic)
                if not topic.startswith(prefix):
                    continue
                raw = message.payload
                if isinstance(raw, (bytes, bytearray)):
                    raw = raw.decode()
                sim.command(topic[len(prefix):], str(raw))

        await asyncio.gather(pump(), ticks(), commands())


def main(argv=None) -> None:
    import asyncio
    asyncio.run(_serve(parse_args(argv)))


if __name__ == "__main__":
    main()
