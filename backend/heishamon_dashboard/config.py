"""Environment configuration (spec §12)."""
import re
from dataclasses import dataclass
from typing import Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ConfigError(ValueError):
    """Raised for a missing required variable or an out-of-range value; names the variable."""


@dataclass(frozen=True)
class Config:
    mqtt_host: str
    mqtt_port: int
    mqtt_user: str | None
    mqtt_password: str | None
    mqtt_tls: bool
    mqtt_base_topic: str
    data_dir: str
    flush_interval_seconds: int
    buffer_max_entries: int
    buffer_max_bytes: int
    audit_buffer_max: int
    raw_retention_days: int | None
    http_port: int
    tz: str
    public_origins: tuple[str, ...]
    allowed_origins: tuple[str, ...]


_HOST = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$|^\[[0-9A-Fa-f:.]+\]$|^[0-9A-Fa-f:]+:[0-9A-Fa-f:]*$")
_ORIGIN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^/\s?#@]+$")


def _int(env: Mapping[str, str], name: str, default: int, lo: int, hi: int | None = None) -> int:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        raise ConfigError(f"{name}: {raw!r} is not an integer") from None
    if value < lo or (hi is not None and value > hi):
        rng = f">= {lo}" if hi is None else f"{lo}..{hi}"
        raise ConfigError(f"{name}: {value} is out of range ({rng})")
    return value


def _base_topic(value: str) -> str:
    err = None
    if len(value.encode("utf-8")) < 1 or len(value.encode("utf-8")) > 128:
        err = "must be 1-128 bytes of UTF-8"
    elif "+" in value or "#" in value or "\x00" in value:
        err = "must not contain '+', '#' or NUL"
    elif value.startswith("$"):
        err = "must not start with '$'"
    elif value.startswith("/") or value.endswith("/"):
        err = "must not start or end with '/'"
    elif any(seg == "" for seg in value.split("/")):
        err = "must not contain empty segments"
    if err:
        raise ConfigError(f"MQTT_BASE_TOPIC: {value!r} {err}")
    return value


def _origins(env: Mapping[str, str], name: str) -> tuple[str, ...]:
    raw = env.get(name, "")
    out = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if not _ORIGIN.match(part):
            raise ConfigError(f"{name}: {part!r} is not an origin (scheme://host[:port])")
        out.append(part)
    return tuple(out)


def load(env: Mapping[str, str]) -> Config:
    host = (env.get("MQTT_HOST") or "").strip()
    if not host:
        raise ConfigError("MQTT_HOST: required but not set")
    if not _HOST.match(host):
        raise ConfigError(f"MQTT_HOST: {host!r} is not a valid hostname")

    base = env.get("MQTT_BASE_TOPIC")
    base = "panasonic_heat_pump" if base is None or base == "" else _base_topic(base)

    tz = env.get("TZ") or "UTC"
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ConfigError(f"TZ: {tz!r} is not a known IANA timezone") from None

    raw_ret = (env.get("RAW_RETENTION_DAYS") or "").strip()
    retention = _int(env, "RAW_RETENTION_DAYS", 0, 1) if raw_ret else None

    return Config(
        mqtt_host=host,
        mqtt_port=_int(env, "MQTT_PORT", 1883, 1, 65535),
        mqtt_user=env.get("MQTT_USER") or None,
        mqtt_password=env.get("MQTT_PASSWORD") or None,
        mqtt_tls=(env.get("MQTT_TLS") or "").strip().lower() in ("1", "true", "yes"),
        mqtt_base_topic=base,
        data_dir=env.get("DATA_DIR") or "/data",
        flush_interval_seconds=_int(env, "FLUSH_INTERVAL_SECONDS", 900, 10, 86400),
        buffer_max_entries=_int(env, "BUFFER_MAX_ENTRIES", 200000, 1000),
        buffer_max_bytes=_int(env, "BUFFER_MAX_BYTES", 268435456, 16777216),
        audit_buffer_max=_int(env, "AUDIT_BUFFER_MAX", 10000, 100, 100000),
        raw_retention_days=retention,
        http_port=_int(env, "HTTP_PORT", 8000, 1, 65535),
        tz=tz,
        public_origins=_origins(env, "PUBLIC_ORIGINS"),
        allowed_origins=_origins(env, "ALLOWED_ORIGINS"),
    )
