"""Pre-publish gates (spec §6 step 2) and the per-command rate limit. Pure: every input is passed in."""
from collections.abc import Iterable

from heishamon_dashboard.commands.planner import Plan, Reject, profile_field, usable
from heishamon_dashboard.firmware import parse_firmware

DEFAULT_RATE_MAX = 6
DEFAULT_RATE_WINDOW_S = 3600


def check_gates(
    plan: Plan,
    confirm: bool,
    *,
    connected: bool,
    device_online: str,
    prefs: dict,
    profile: dict,
    budget_ok: bool,
) -> None:
    """Raise `Reject` for the first gate the plan fails: broker, device, write lock, PCB, firmware,
    series applicability, unknown profile fields, read-only value, confirm, protected-record budget."""
    if not connected:
        raise Reject("broker_disconnected", "the MQTT broker is not connected", status=503)
    if device_online != "online":
        raise Reject("device_offline", "the heat pump is not online")
    if prefs.get("write_lock"):
        raise Reject("write_lock", "write lock is on")
    if plan.pcb:
        if not prefs.get("pcb_enabled"):
            raise Reject("pcb_disabled", "optional-PCB commands are disabled in the preferences")
        pcb = profile_field(profile, "pcb_emulation_active")
        if not (usable(pcb) and pcb["value"] is True):
            raise Reject("pcb_emulation_inactive", "optional-PCB emulation is not active")
    fw = profile_field(profile, "firmware")
    version, assumed = parse_firmware(fw["value"] if fw else None)
    need, _ = parse_firmware(plan.entry["min_firmware"])
    if need > version:
        raise Reject("firmware_too_old",
                     f"needs HeishaMon {plan.entry['min_firmware']}",
                     {"min_firmware": plan.entry["min_firmware"], "assumed": assumed})
    applicability = plan.entry.get("applicability") or {}
    series_unknown = False
    if applicability.get("series"):
        series = profile_field(profile, "series")
        if series is not None and not series.get("unknown") and series["value"] is not None:
            if series["value"] not in applicability["series"]:
                raise Reject("not_applicable", f"only for series {', '.join(applicability['series'])}",
                             {"series": series["value"]})
        else:
            series_unknown = True
    unknown = list(plan.unknown_fields)
    for path in applicability.get("requires", []):
        if not usable(profile_field(profile, path)):
            unknown.append(path)
    if unknown and not plan.entry.get("safe_under_unknown"):
        raise Reject("profile_unknown", f"profile field {unknown[0]} is unknown or stale",
                     {"field": unknown[0]})
    if plan.read_only:
        raise Reject("read_only_value", f"{plan.value} cannot be written")
    if (plan.risky or series_unknown) and not confirm:
        raise Reject("confirm_required", "this command needs confirm: true")
    if not budget_ok:
        raise Reject("storage_unavailable", "protected-record budget is full", status=503)


def check_rate(name: str, publishes: Iterable[int], now: int, rate_max: int, rate_window_s: int) -> None:
    """C4b: at most `rate_max` publish attempts per command name in the sliding window."""
    window_ms = rate_window_s * 1000
    recent = [ts for ts in publishes if ts > now - window_ms]
    if len(recent) >= rate_max:
        wait = recent[-rate_max] + window_ms - now
        raise Reject("rate_limited", f"{name} was written {rate_max} times in the last "
                     f"{rate_window_s} s", {"retry_after_s": -(-wait // 1000)}, status=429)
