"""catalog.json loader and validator (spec Appendix A.3)."""
import json
import re
from dataclasses import dataclass
from pathlib import Path

CMD_CLASSES = {"setting", "trigger", "unverifiable"}
CMD_TYPES = {"int", "bool", "dec1", "dec3", "json", "int2", "int12"}
INPUT_TYPES = {"dec3", "dec1", "int", "bool"}
INPUT_CLASSES = {"retained_exception", "input"}
KINDS = {"number", "enum", "text"}
RANGE_SOURCES = {"panasonic_manual", "heishamon_fact", "encoding_domain"}
COMPARE = {"equal", "holiday", "curve_leaf"}

_TOP = {"schema", "topics", "commands", "inputs", "models"}
_TOPIC_REQ = {"key", "id", "kind", "category", "label", "min_firmware"}
_TOPIC_OPT = {"unit", "decimals", "enum", "sentinels", "feature"}
_CMD_REQ = {"name", "pcb", "class", "risky", "type", "range_source", "min_firmware", "category", "label"}
_CMD_OPT = {"range", "allowed", "conditional_ranges", "readback", "compare", "applicability", "safe_under_unknown"}
_INPUT_REQ = {"path", "class", "retain", "type", "range", "range_source", "min_firmware", "label"}
_MODEL_REQ = {"hex", "name", "series"}
_RANGE_KEYS = {"min", "max", "step"}
# TOP92 as HeishaMon publishes it: ten bytes as upper-case hex pairs separated by single spaces.
_MODEL_HEX = re.compile(r"[0-9A-F]{2}( [0-9A-F]{2}){9}")


class CatalogError(ValueError):
    """Raised when catalog.json violates the schema."""


@dataclass(frozen=True)
class Catalog:
    topics: tuple[dict, ...]
    commands: tuple[dict, ...]
    inputs: tuple[dict, ...]
    models: tuple[dict, ...]
    _topics_by_key: dict
    _commands_by_name: dict
    _inputs_by_path: dict

    def topic(self, key: str) -> dict | None:
        return self._topics_by_key.get(key)

    def command(self, name: str) -> dict | None:
        return self._commands_by_name.get(name)

    def input(self, path: str) -> dict | None:
        return self._inputs_by_path.get(path)

    def model(self, payload: str | None) -> dict | None:
        """The models entry for a Heat_Pump_Model payload (whitespace and case normalised), else None."""
        if not isinstance(payload, str):
            return None
        key = " ".join(payload.split()).upper()
        return next((m for m in self.models if m["hex"] == key), None)


def _keys(obj, where, req, opt=()):
    if not isinstance(obj, dict):
        raise CatalogError(f"{where}: must be an object")
    missing = set(req) - obj.keys()
    if missing:
        raise CatalogError(f"{where}: missing key(s) {sorted(missing)}")
    unknown = obj.keys() - set(req) - set(opt)
    if unknown:
        raise CatalogError(f"{where}: unknown key(s) {sorted(unknown)}")


def _label(obj, where):
    _keys(obj, where, {"en", "nl"})
    if not all(isinstance(v, str) for v in obj.values()):
        raise CatalogError(f"{where}: label values must be strings")


def _range(obj, where, extra_req=()):
    _keys(obj, where, set(extra_req), _RANGE_KEYS)
    for k, v in obj.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise CatalogError(f"{where}.{k}: must be a number")


def _choice(value, allowed, where):
    if value not in allowed:
        raise CatalogError(f"{where}: {value!r} not one of {sorted(allowed)}")


def _str(value, where):
    if not isinstance(value, str) or not value:
        raise CatalogError(f"{where}: must be a non-empty string")


def _bool(value, where):
    if not isinstance(value, bool):
        raise CatalogError(f"{where}: must be a boolean")


def _validate_topic(t, i):
    w = f"topics[{i}]"
    _keys(t, w, _TOPIC_REQ, _TOPIC_OPT)
    _str(t["key"], f"{w}.key")
    _str(t["id"], f"{w}.id")
    _choice(t["kind"], KINDS, f"{w}.kind")
    _str(t["category"], f"{w}.category")
    _str(t["min_firmware"], f"{w}.min_firmware")
    _label(t["label"], f"{w}.label")
    if t.get("unit") is not None:
        _str(t["unit"], f"{w}.unit")
    if "decimals" in t and (isinstance(t["decimals"], bool) or not isinstance(t["decimals"], int) or t["decimals"] < 0):
        raise CatalogError(f"{w}.decimals: must be a non-negative integer")
    if "enum" in t:
        if not isinstance(t["enum"], dict):
            raise CatalogError(f"{w}.enum: must be an object")
        for k, v in t["enum"].items():
            _label(v, f"{w}.enum[{k!r}]")
    if "sentinels" in t and (not isinstance(t["sentinels"], list)
                             or not all(isinstance(s, (int, float)) and not isinstance(s, bool) for s in t["sentinels"])):
        raise CatalogError(f"{w}.sentinels: must be a list of numbers")
    if t.get("feature") is not None:
        _str(t["feature"], f"{w}.feature")


def _validate_command(c, i):
    w = f"commands[{i}]"
    _keys(c, w, _CMD_REQ, _CMD_OPT)
    _str(c["name"], f"{w}.name")
    _bool(c["pcb"], f"{w}.pcb")
    _choice(c["class"], CMD_CLASSES, f"{w}.class")
    _bool(c["risky"], f"{w}.risky")
    _choice(c["type"], CMD_TYPES, f"{w}.type")
    _choice(c["range_source"], RANGE_SOURCES, f"{w}.range_source")
    _str(c["min_firmware"], f"{w}.min_firmware")
    _str(c["category"], f"{w}.category")
    _label(c["label"], f"{w}.label")
    if c.get("range") is not None:
        _range(c["range"], f"{w}.range")
    if c.get("allowed") is not None and not isinstance(c["allowed"], list):
        raise CatalogError(f"{w}.allowed: must be a list or null")
    if "conditional_ranges" in c:
        cr = c["conditional_ranges"]
        if not isinstance(cr, list):
            raise CatalogError(f"{w}.conditional_ranges: must be a list")
        for j, item in enumerate(cr):
            ww = f"{w}.conditional_ranges[{j}]"
            _keys(item, ww, {"when"}, _RANGE_KEYS)
            if not isinstance(item["when"], dict):
                raise CatalogError(f"{ww}.when: must be an object")
            _range({k: v for k, v in item.items() if k != "when"}, ww)
    if "readback" in c and (not isinstance(c["readback"], list) or not all(isinstance(r, str) for r in c["readback"])):
        raise CatalogError(f"{w}.readback: must be a list of strings")
    if "compare" in c:
        _choice(c["compare"], COMPARE, f"{w}.compare")
    if "applicability" in c:
        _keys(c["applicability"], f"{w}.applicability", set(), {"requires"})
        req = c["applicability"].get("requires", [])
        if not isinstance(req, list) or not all(isinstance(r, str) for r in req):
            raise CatalogError(f"{w}.applicability.requires: must be a list of strings")
    if "safe_under_unknown" in c:
        _bool(c["safe_under_unknown"], f"{w}.safe_under_unknown")


def _validate_input(x, i):
    w = f"inputs[{i}]"
    _keys(x, w, _INPUT_REQ)
    _str(x["path"], f"{w}.path")
    _choice(x["class"], INPUT_CLASSES, f"{w}.class")
    _bool(x["retain"], f"{w}.retain")
    _choice(x["type"], INPUT_TYPES, f"{w}.type")
    _range(x["range"], f"{w}.range")
    _choice(x["range_source"], RANGE_SOURCES, f"{w}.range_source")
    _str(x["min_firmware"], f"{w}.min_firmware")
    _label(x["label"], f"{w}.label")


def _validate_model(m, i):
    w = f"models[{i}]"
    _keys(m, w, _MODEL_REQ)
    _str(m["hex"], f"{w}.hex")
    if not _MODEL_HEX.fullmatch(m["hex"]):
        raise CatalogError(f"{w}.hex: must be ten upper-case hex bytes separated by single spaces")
    _str(m["name"], f"{w}.name")
    _choice(m["series"], {"J", "K", "L", "other"}, f"{w}.series")


def _index(items, field, what):
    out = {}
    for it in items:
        if it[field] in out:
            raise CatalogError(f"duplicate {what} {it[field]!r}")
        out[it[field]] = it
    return out


def parse(data) -> Catalog:
    _keys(data, "catalog", {"schema", "topics", "commands"}, _TOP)
    if data["schema"] != 1 or isinstance(data["schema"], bool):
        raise CatalogError(f"schema: unsupported version {data['schema']!r}")
    for sect in ("topics", "commands", "inputs", "models"):
        if sect in data and not isinstance(data[sect], list):
            raise CatalogError(f"{sect}: must be a list")
    topics, commands = data["topics"], data["commands"]
    inputs, models = data.get("inputs", []), data.get("models", [])
    for i, t in enumerate(topics):
        _validate_topic(t, i)
    for i, c in enumerate(commands):
        _validate_command(c, i)
    for i, x in enumerate(inputs):
        _validate_input(x, i)
    for i, m in enumerate(models):
        _validate_model(m, i)
    _index(models, "hex", "model hex")
    return Catalog(
        topics=tuple(topics), commands=tuple(commands), inputs=tuple(inputs), models=tuple(models),
        _topics_by_key=_index(topics, "key", "topic key"),
        _commands_by_name=_index(commands, "name", "command name"),
        _inputs_by_path=_index(inputs, "path", "input path"),
    )


def load(path) -> Catalog:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CatalogError(f"{path}: invalid JSON: {e}") from None
    return parse(data)
