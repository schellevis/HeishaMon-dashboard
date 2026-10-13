"""Domain rules shared by backend and frontend (`rules.json`, schema 1): curve limits, leaf naming,
operating-mode sets, power-topic pairs, meters and overview tile ids."""
import json
import re
from functools import lru_cache
from pathlib import Path

SCHEMA = 1
DEFAULT_PATH = Path(__file__).parent / "rules.json"
_MODES = ("heat", "cool")
_ENDS = ("cold", "warm")
_FIELDS = ("outside", "target")
_POWER_MODES = ("heat", "cool", "dhw")
_OP_MODES = ("heating", "cooling", "dhw", "read_only")
_LEAF_FIELDS = ("{zone}", "{Mode}", "{Group}", "{End}")


class RulesError(ValueError):
    """rules.json is missing, unreadable or does not match schema 1."""


def _int_pair(v, where):
    if (not isinstance(v, list) or len(v) != 2 or any(isinstance(x, bool) or not isinstance(x, int) for x in v)
            or v[0] > v[1]):
        raise RulesError(f"{where}: expected [min, max] integers")
    return (v[0], v[1])


def _int_list(v, where):
    if not isinstance(v, list) or not v or any(isinstance(x, bool) or not isinstance(x, int) for x in v):
        raise RulesError(f"{where}: expected a non-empty list of integers")
    return tuple(v)


def _str_list(v, where):
    if not isinstance(v, list) or not v or any(not isinstance(x, str) or not x for x in v):
        raise RulesError(f"{where}: expected a non-empty list of strings")
    return tuple(v)


def _obj(v, where, keys):
    if not isinstance(v, dict):
        raise RulesError(f"{where}: expected an object")
    if set(v) != set(keys):
        raise RulesError(f"{where}: keys must be exactly {sorted(keys)}, got {sorted(v)}")
    return v


class Rules:
    def __init__(self, data):
        d = _obj(data, "rules", ("schema", "curve_limits", "curve_shift", "curve_leaf", "curve_ends",
                                 "operating_modes", "room_sensor_values", "power_pairs", "s0_meters", "tiles"))
        if d["schema"] != SCHEMA:
            raise RulesError(f"unsupported schema {d['schema']!r} (expected {SCHEMA})")
        lim = _obj(d["curve_limits"], "curve_limits", _MODES)
        self.curve_limits = {m: {f: _int_pair(_obj(lim[m], f"curve_limits.{m}", _FIELDS)[f],
                                              f"curve_limits.{m}.{f}") for f in _FIELDS} for m in _MODES}
        self.curve_shift = _int_pair(d["curve_shift"], "curve_shift")
        leaf = d["curve_leaf"]
        if not isinstance(leaf, str) or any(leaf.count(f) != 1 for f in _LEAF_FIELDS):
            raise RulesError("curve_leaf: must contain {zone}, {Mode}, {Group} and {End} once each")
        self.curve_leaf = leaf
        ends = _obj(d["curve_ends"], "curve_ends", _ENDS)
        self.curve_ends = {}
        for e in _ENDS:
            o = _obj(ends[e], f"curve_ends.{e}", _FIELDS)
            if any(o[f] not in ("High", "Low") for f in _FIELDS):
                raise RulesError(f"curve_ends.{e}: values must be High or Low")
            self.curve_ends[e] = {f: o[f] for f in _FIELDS}
        if any(self.curve_ends["cold"][f] == self.curve_ends["warm"][f] for f in _FIELDS):
            raise RulesError("curve_ends: cold and warm must use opposite leaves")
        om = _obj(d["operating_modes"], "operating_modes", _OP_MODES)
        self.operating_modes = {k: frozenset(_int_list(om[k], f"operating_modes.{k}")) for k in _OP_MODES}
        self.room_sensor_values = frozenset(_int_list(d["room_sensor_values"], "room_sensor_values"))
        pp = _obj(d["power_pairs"], "power_pairs", ("main", "extra"))
        self.power_pairs = {}
        for src in ("main", "extra"):
            sm = _obj(pp[src], f"power_pairs.{src}", _POWER_MODES)
            self.power_pairs[src] = {}
            for m in _POWER_MODES:
                pair = _str_list(sm[m], f"power_pairs.{src}.{m}")
                if len(pair) != 2:
                    raise RulesError(f"power_pairs.{src}.{m}: expected [production, consumption]")
                self.power_pairs[src][m] = pair
        self.s0_meters = _str_list(d["s0_meters"], "s0_meters")
        self.tiles = _str_list(d["tiles"], "tiles")
        if len(set(self.tiles)) != len(self.tiles):
            raise RulesError("tiles: duplicate id")

    # leaf naming ---------------------------------------------------------------------------
    def leaf_topic(self, zone: int, mode: str, group: str, end: str) -> str:
        """Topic key of one curve point. `mode`: heat|cool, `group`: outside|target, `end`: High|Low."""
        return (self.curve_leaf.replace("{zone}", str(zone)).replace("{Mode}", mode.capitalize())
                .replace("{Group}", group.capitalize()).replace("{End}", end))

    def leaf_for_end(self, zone: int, mode: str, curve_end: str, group: str) -> str:
        """Topic key of the curve point at `curve_end` (cold|warm) for `group` (outside|target)."""
        return self.leaf_topic(zone, mode, group, self.curve_ends[curve_end][group])

    def leaf_regex(self) -> re.Pattern:
        """Parses a curve topic into (zone, mode, group, end); inverse of `leaf_topic`."""
        pat = re.escape(self.curve_leaf)
        for token, rx in (("zone", "([12])"), ("Mode", "(Heat|Cool)"), ("Group", "(Target|Outside)"),
                          ("End", "(High|Low)")):
            pat = pat.replace(re.escape("{" + token + "}"), rx)
        return re.compile(f"^{pat}$")

    def power_topics(self, extra: bool) -> dict[str, tuple[str, str]]:
        return {m: tuple(p) for m, p in self.power_pairs["extra" if extra else "main"].items()}


@lru_cache(maxsize=None)
def _load(path: str) -> Rules:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise RulesError(f"cannot read {path}: {e}") from e
    return Rules(data)


def load(path=None) -> Rules:
    """Load and validate rules.json (cached per path); raises RulesError."""
    return _load(str(path or DEFAULT_PATH))


def parse(data) -> Rules:
    """Validate an already-parsed document (used by tests)."""
    return Rules(data)
