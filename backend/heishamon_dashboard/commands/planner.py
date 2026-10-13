"""Command planning: catalog + profile + state snapshot + input -> `Plan` or `Reject` (spec §6 step 1).

Pure: no scheduler, no MQTT, no store. Live state enters through the `current_int` callable and the
`inflight` mapping the caller passes in."""
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from heishamon_dashboard import rules
from heishamon_dashboard.catalog import Catalog
from heishamon_dashboard.encoding import EncodingError, check_type, encode, to_decimal

_RULES = rules.load()
OPERATION_MODE_READ_ONLY = _RULES.operating_modes["read_only"]

_CURVE_ZONES = {"zone1": "Z1", "zone2": "Z2"}
_CURVE_MODES = {"heat": "Heat", "cool": "Cool"}
_CURVE_GROUPS = {"target": "Target", "outside": "Outside"}
_CURVE_ENDS = {"high": "High", "low": "Low"}
_CURVE_LIMITS = _RULES.curve_limits  # inclusive (min, max) per mode and group, spec §8
_CURVE_TOPIC = _RULES.leaf_regex()
_ROOM_SENSORS = {"ext_thermostat", "int_thermostat", "thermistor"}


class Reject(Exception):
    def __init__(self, code: str, message: str, detail: dict | None = None, status: int = 422):
        super().__init__(message)
        self.code, self.message, self.detail, self.status = code, message, detail, status


def error_body(code: str, message: str, detail: dict | None = None) -> dict:
    return {"error": code, "message": message, "detail": detail}


@dataclass
class Plan:
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


def num_equal(expected, actual) -> bool:
    try:
        return Decimal(repr(float(actual))) == Decimal(repr(float(expected)))
    except (TypeError, ValueError, ArithmeticError):
        return False


def values_match(compare: str, expected, actual) -> bool:
    """A.2 comparison rules: `equal`, `holiday` and `curve_leaf` (a plain per-leaf equality)."""
    if actual is None or isinstance(actual, str):
        return False
    if compare == "holiday":
        if num_equal(expected, 1):
            return num_equal(actual, 1) or num_equal(actual, 2)
        return num_equal(actual, expected)
    return num_equal(expected, actual)


def profile_field(profile: dict, path: str) -> dict | None:
    node: Any = profile
    parts = path.split(".")
    if parts[0] == "profile":
        parts = parts[1:]
    for p in parts:
        if not isinstance(node, dict) or p not in node:
            return None
        node = node[p]
    return node if isinstance(node, dict) and "value" in node else None


def usable(f: dict | None) -> bool:
    return f is not None and not f.get("unknown") and not f.get("stale")


def plain_number(d: Decimal):
    return int(d) if d == d.to_integral_value() else float(d)


def plan_command(
    catalog: Catalog,
    name: str,
    value,
    profile: dict,
    current_int: Callable[[str], int | None],
    inflight: dict[str, int] | None = None,
) -> Plan:
    """Validate `value` for `name` and build the plan. `inflight` maps curve topics to the values
    of unconfirmed SetCurves flights; `current_int` returns a fresh read-back or None."""
    cmd = catalog.command(name)
    inp = None if cmd else catalog.input(name)
    if cmd is None and inp is None:
        raise Reject("unknown_command", f"unknown command or input {name!r}")
    entry = cmd or inp
    type_ = entry["type"]
    cls = entry["class"]

    try:
        checked = check_type(type_, value)
    except EncodingError as e:
        raise Reject(e.code, e.message) from None

    plan = Plan(
        name=name, entry=entry, kind="command" if cmd else "input", cls=cls, type_=type_, value=value,
        payload="", retained=bool(inp and inp.get("retain")), risky=False,
        pcb=bool(cmd and cmd.get("pcb")),
    )
    if cmd:
        plan.readback = list(cmd.get("readback") or [])
        plan.compare = cmd.get("compare", "equal")

    if type_ == "json":
        _plan_curves(plan, checked, profile, current_int, inflight or {})
    else:
        rng = resolve_range(plan, profile)
        if name == "SetOperationMode" and checked in OPERATION_MODE_READ_ONLY:
            plan.read_only = True
        else:
            _check_value(plan, checked, rng)
        plan.payload = encode(type_, value)
        if cls == "setting" and plan.readback:
            plan.expected = {plan.readback[0]: plain_number(checked)}

    plan.risky = _is_risky(plan)
    return plan


def _is_risky(plan: Plan) -> bool:
    if plan.cls in ("trigger", "retained_exception") or plan.pcb:
        return True
    if plan.name == "SetHeatpump":
        return plan.value == 0
    return bool(plan.entry.get("risky"))


def resolve_range(plan: Plan, profile: dict) -> dict | None:
    """The effective range; records the profile fields it depends on (meaning, unknowns)."""
    entry = plan.entry
    base = entry.get("range")
    cond = entry.get("conditional_ranges") or []
    if cond:
        for item in cond:
            results = []
            for path, expected in item["when"].items():
                f = profile_field(profile, path)
                if not usable(f):
                    plan.unknown_fields.append(path)
                    results.append(None)
                else:
                    plan.meaning[path] = f["value"]
                    results.append(f["value"] == expected)
            if all(r is True for r in results):
                return {k: v for k, v in item.items() if k != "when"}
        return None if plan.unknown_fields else base
    return base


def _check_value(plan: Plan, checked: Decimal, rng: dict | None) -> None:
    entry = plan.entry
    allowed = entry.get("allowed")
    if allowed is None and plan.type_ == "bool":
        allowed = [0, 1]
    if allowed is not None:
        if checked not in [Decimal(repr(a)) for a in allowed]:
            raise Reject("not_allowed_value", f"{plan.value} is not one of {allowed}",
                         {"allowed": allowed})
        return
    if rng is None:
        return  # range depends on an unknown profile field; gate 7 reports it
    lo, hi, step = rng.get("min"), rng.get("max"), rng.get("step")
    if (lo is not None and checked < to_decimal(lo)) or (hi is not None and checked > to_decimal(hi)):
        raise Reject("out_of_range", f"{plan.value} is outside {lo}..{hi}", {"min": lo, "max": hi})
    if step:
        base = to_decimal(lo if lo is not None else 0)
        if (checked - base) % to_decimal(step) != 0:
            raise Reject("bad_step", f"{plan.value} is not on the step grid of {step}",
                         {"step": step, "min": lo})


def _plan_curves(plan: Plan, value: dict, profile: dict, current_int: Callable[[str], int | None],
                 inflight: dict[str, int]) -> None:
    leaves: dict[str, int] = {}
    meta: dict[str, tuple[str, str, str]] = {}  # topic -> (mode, group, end)
    for zk, zv in value.items():
        if zk not in _CURVE_ZONES or not isinstance(zv, dict):
            raise Reject("bad_type", f"unknown or malformed zone key {zk!r}")
        for mk, mv in zv.items():
            if mk not in _CURVE_MODES or not isinstance(mv, dict):
                raise Reject("bad_type", f"unknown or malformed mode key {mk!r}")
            for gk, gv in mv.items():
                if gk not in _CURVE_GROUPS or not isinstance(gv, dict):
                    raise Reject("bad_type", f"unknown or malformed curve group {gk!r}")
                for ek, ev in gv.items():
                    if ek not in _CURVE_ENDS:
                        raise Reject("bad_type", f"unknown curve end {ek!r}")
                    if isinstance(ev, bool) or not isinstance(ev, int):
                        raise Reject("bad_type", "curve values must be integer literals")
                    topic = _curve_topic(zk, mk, gk, ek)
                    leaves[topic] = ev
                    meta[topic] = (mk, gk, ek)
    if not leaves:
        raise Reject("bad_type", "SetCurves needs at least one value")
    for topic, v in leaves.items():
        mode, group, _ = meta[topic]
        lo, hi = _CURVE_LIMITS[mode][group]
        if not lo <= v <= hi:
            raise Reject("out_of_range", f"{topic} {v} is outside {lo}..{hi}",
                         {"key": topic, "min": lo, "max": hi})
    touched = {curve_zone_mode(t) for t in meta}
    coupled = {k: curve_coupled(profile, k) for k in touched}
    plan.meaning = curve_meaning(profile, touched)

    # the resulting curve: read-back, overlaid with unconfirmed in-flight leaves, overlaid with ours
    def resulting(topic: str) -> int:
        if topic in leaves:
            return leaves[topic]
        if topic in inflight:
            return inflight[topic]
        cur = current_int(topic)
        if cur is None:
            raise Reject("profile_unknown", f"curve value {topic} is unknown or stale", {"field": topic})
        return cur

    def skip(topic: str, group: str) -> bool:
        # In coupled mode the cold-end target is the direct setpoint and the warm-end target is
        # unused, so the target ordering does not apply (outside ordering and limits still do).
        return group == "target" and coupled[curve_zone_mode(topic)]

    checked: set[str] = set()
    for topic, (mode, group, end) in meta.items():  # ordering on the resulting curve
        high_topic = topic.replace("_Low_", "_High_")
        if high_topic in checked or skip(topic, group):
            continue
        checked.add(high_topic)
        low_topic = high_topic.replace("_High_", "_Low_")
        high, low = resulting(high_topic), resulting(low_topic)
        ok = low + 1 <= high if group == "outside" else high >= low
        if not ok:
            raise Reject("out_of_range", f"curve ordering violated for {high_topic}",
                         {"rule": "ordering", "key": high_topic})
    plan.readback = list(plan.entry.get("readback") or [])
    plan.compare = "curve_leaf"
    plan.expected = dict(leaves)
    plan.payload = encode("json", value)


def _curve_topic(zone: str, mode: str, group: str, end: str) -> str:
    return _RULES.leaf_topic(int(_CURVE_ZONES[zone][1:]), mode, group, _CURVE_ENDS[end])


def curve_zone_mode(topic: str) -> tuple[int, str]:
    z, m, _, _ = _CURVE_TOPIC.match(topic).groups()
    return int(z), m.lower()


def curve_coupled(profile: dict, zone_mode: tuple[int, str]) -> bool:
    """Direct control with a room sensor (thermostat/thermistor) for this zone and mode: the
    firmware then stores the direct setpoint in the curve's cold-end target (Target_High) and
    the warm-end target is unused. False when either profile field is unknown or stale."""
    zone, mode = zone_mode
    ctl = profile_field(profile, "heating_control" if mode == "heat" else "cooling_control")
    sensor = profile_field(profile, f"zone.z{zone}.sensor")
    return (usable(ctl) and ctl["value"] == "direct"
            and usable(sensor) and sensor["value"] in _ROOM_SENSORS)


def curve_meaning(profile: dict, zone_modes) -> dict[str, Any]:
    """Per touched (zone, mode): the control mode and whether the zone sensor is a room sensor.
    None marks a profile field that is unknown or stale."""
    out: dict[str, Any] = {}
    for zone, mode in sorted(zone_modes):
        ctl = profile_field(profile, "heating_control" if mode == "heat" else "cooling_control")
        sensor = profile_field(profile, f"zone.z{zone}.sensor")
        out[f"z{zone}.{mode}.control"] = ctl["value"] if usable(ctl) else None
        out[f"z{zone}.{mode}.room_sensor"] = sensor["value"] in _ROOM_SENSORS if usable(sensor) else None
    return out


def nest_curve_leaves(leaves: dict[str, int]) -> dict:
    out: dict = {}
    for topic, v in leaves.items():
        z, m, g, e = _CURVE_TOPIC.match(topic).groups()
        out.setdefault(f"zone{z}", {}).setdefault(m.lower(), {}).setdefault(g.lower(), {})[e.lower()] = v
    return out


def encode_pending(pending: dict[str, int]) -> str:
    """The partial SetCurves payload for the leaves still pending."""
    return encode("json", nest_curve_leaves(pending))


def drop_matching(plan: Plan, live_match: Callable[[Plan, str, Any], bool],
                  force: set[str]) -> tuple[Plan, dict[str, int]]:
    """Drop what the live read-back already shows, except the `force` topics (conflicting flights).
    `live_match(plan, topic, expected)` says whether a fresh live read-back already equals `expected`."""
    if plan.name == "SetCurves":
        keep = {t: v for t, v in plan.expected.items() if t in force or not live_match(plan, t, v)}
        plan.expected = keep
        if keep:
            plan.payload = encode("json", nest_curve_leaves(keep))
        return plan, dict(keep)
    if not force:
        for topic, exp in plan.expected.items():
            if live_match(plan, topic, exp):
                plan.expected = {}
    return plan, {}
