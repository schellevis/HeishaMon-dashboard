"""Record a sanitized MQTT replay fixture from a live HeishaMon installation (spec §10, decision-006).

READ-ONLY: the script subscribes to `<base>/#` and never publishes. It takes the connection
settings from the environment (the same names as the dashboard: MQTT_HOST, MQTT_PORT, MQTT_USER,
MQTT_PASSWORD, MQTT_TLS, MQTT_BASE_TOPIC) and does not read any `.env` file; export the variables
in your shell first. Run it once on your own network:

    python tools/capture.py --duration 900 --out backend/tests/fixtures/replay_real.json

Sanitizing (nothing identifying leaves this script):

* the `ip` topic, the `log` topic and every topic outside the known HeishaMon subtrees are dropped;
* `stats` is reduced to its `version`;
* 1-wire addresses are replaced by stable pseudonyms (`1wire/pseudo-01`, ...) and their
  `alias` payloads (free text chosen by the owner) by the same pseudonym;
* any payload that contains an IPv4 address, a MAC address or an e-mail address is dropped;
* the base topic and the broker address are not written; topics are relative to the base.

Fixture format (`heishamon-replay/1`): `{"format", "synthetic", "duration_s", "dropped": {...},
"messages": [{"t": ms since start, "topic": relative topic, "payload": str, "retained": bool}]}`.
`retained` is the flag as delivered to the subscriber: true only for the snapshot the broker sends on subscribe.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

FORMAT = "heishamon-replay/1"
KEEP_PREFIXES = ("main/", "extra/", "optional/", "1wire/", "s0/", "opentherm/")
KEEP_EXACT = frozenset({"stats", "LWT"})
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "backend" / "tests" / "fixtures" / "replay_real.json"

_IPV4 = re.compile(r"(?<![\d.])\d{1,3}(?:\.\d{1,3}){3}(?![\d.])")
_MAC = re.compile(r"\b[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}\b")
_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")


class Sanitizer:
    """Stateful, so the same 1-wire address always maps to the same pseudonym."""

    def __init__(self):
        self.pseudonyms: dict[str, str] = {}
        self.dropped: dict[str, int] = {}

    def _drop(self, reason: str) -> None:
        self.dropped[reason] = self.dropped.get(reason, 0) + 1
        return None

    def pseudonym(self, address: str) -> str:
        if address not in self.pseudonyms:
            self.pseudonyms[address] = f"pseudo-{len(self.pseudonyms) + 1:02d}"
        return self.pseudonyms[address]

    def clean(self, topic: str, payload: str) -> tuple[str, str] | None:
        """Return the sanitized (topic, payload), or None when the message must not be recorded."""
        if topic == "ip":
            return self._drop("ip")
        if topic == "log" or topic.startswith("log/"):
            return self._drop("log")
        if topic not in KEEP_EXACT and not topic.startswith(KEEP_PREFIXES):
            return self._drop("other")
        if topic == "stats":
            try:
                data = json.loads(payload)
            except ValueError:
                return self._drop("stats_unparseable")
            version = data.get("version") if isinstance(data, dict) else None
            return topic, json.dumps({"version": version} if isinstance(version, str) else {}, separators=(",", ":"))
        if topic.startswith("1wire/"):
            parts = topic.split("/")
            name = self.pseudonym(parts[1])
            if len(parts) > 2 and parts[2] == "alias":
                return f"1wire/{name}/alias", name
            if len(parts) > 2:
                return self._drop("other")
            topic = f"1wire/{name}"
        if _IPV4.search(payload) or _MAC.search(payload) or _EMAIL.search(payload):
            return self._drop("identifying_payload")
        return topic, payload


async def capture(client, base: str, duration_s: float, *, clock=time.monotonic, sanitizer: Sanitizer | None = None) -> dict:
    """Subscribe to `<base>/#` and record for `duration_s` seconds. Never publishes."""
    sanitizer = sanitizer or Sanitizer()
    messages = []
    prefix = base + "/"
    await client.subscribe(f"{base}/#")
    started = clock()
    try:
        async with asyncio.timeout(duration_s):
            async for message in client.messages:
                topic = str(message.topic)
                if not topic.startswith(prefix):
                    continue
                raw = message.payload
                payload = bytes(raw).decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
                cleaned = sanitizer.clean(topic[len(prefix):], payload)
                if cleaned is None:
                    continue
                messages.append({"t": int((clock() - started) * 1000), "topic": cleaned[0],
                                 "payload": cleaned[1], "retained": bool(getattr(message, "retain", False))})
    except TimeoutError:
        pass
    return {"format": FORMAT, "synthetic": False, "duration_s": int(duration_s),
            "dropped": dict(sorted(sanitizer.dropped.items())), "messages": messages}


def write_fixture(document: dict, path: Path, *, force: bool = False) -> None:
    path = Path(path)
    if path.exists() and not force:
        raise FileExistsError(f"{path} exists; pass --force to overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")


def _client(config):
    import aiomqtt

    kwargs = {}
    if config.mqtt_user is not None:
        kwargs["username"] = config.mqtt_user
    if config.mqtt_password is not None:
        kwargs["password"] = config.mqtt_password
    if config.mqtt_tls:
        kwargs["tls_params"] = aiomqtt.TLSParameters()
    return aiomqtt.Client(config.mqtt_host, port=config.mqtt_port, **kwargs)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Record a sanitized, read-only MQTT replay fixture.")
    parser.add_argument("--duration", type=float, default=900.0,
                        help="seconds to record (default 900; HeishaMon re-publishes everything every 300 s)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--force", action="store_true", help="overwrite an existing fixture")
    return parser.parse_args(argv)


async def _run(args, env) -> dict:
    from heishamon_dashboard.config import load

    config = load(env)
    async with _client(config) as client:
        return await capture(client, config.mqtt_base_topic, args.duration)


def main(argv=None, env=None) -> int:
    args = parse_args(argv)
    from heishamon_dashboard.config import ConfigError

    try:
        document = asyncio.run(_run(args, os.environ if env is None else env))
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    write_fixture(document, args.out, force=args.force)
    print(f"wrote {len(document['messages'])} messages to {args.out}; dropped: {document['dropped']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
