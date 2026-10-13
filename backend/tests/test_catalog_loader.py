import copy
import json
from pathlib import Path

import pytest

from heishamon_dashboard import catalog
from heishamon_dashboard.catalog import CatalogError

HERE = Path(__file__).parent
STUB = HERE.parent / "heishamon_dashboard" / "catalog.json"
FIXTURE = HERE / "fixtures" / "catalog_min.json"


def raw():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_loads():
    c = catalog.load(FIXTURE)
    assert len(c.topics) == 2 and len(c.commands) == 2


def test_lookups():
    c = catalog.load(FIXTURE)
    assert c.topic("main/Outside_Temp")["id"] == "TOP14"
    assert c.command("SetDHWTemp")["type"] == "int"
    assert c.topic("nope") is None and c.command("nope") is None
    assert c.input("s0/WatthourTotal/1") is None


def test_input_lookup():
    d = raw()
    d["inputs"] = [{"path": "s0/WatthourTotal/1", "class": "retained_exception", "retain": True,
                    "type": "dec3", "range": {"min": 0}, "range_source": "heishamon_fact",
                    "min_firmware": "3.2.3", "ui_group": "s0",
                    "label": {"en": "S0 total", "nl": "S0 totaal"}}]
    assert catalog.parse(d).input("s0/WatthourTotal/1")["retain"] is True


def mutate(fn):
    d = copy.deepcopy(raw())
    fn(d)
    return d


_HEX = "AA BB CC DD EE FF 00 11 22 33"

VIOLATIONS = {
    "unknown top key": lambda d: d.update(extra=1),
    "bad schema version": lambda d: d.update(schema=2),
    "missing topics": lambda d: d.pop("topics"),
    "unknown topic key": lambda d: d["topics"][0].update(bogus=1),
    "bad topic kind": lambda d: d["topics"][0].update(kind="float"),
    "missing topic label": lambda d: d["topics"][0].pop("label"),
    "label missing nl": lambda d: d["topics"][0]["label"].pop("nl"),
    "bad enum label": lambda d: d["topics"][1]["enum"].update({"2": "x"}),
    "unknown command key": lambda d: d["commands"][0].update(bogus=1),
    "missing range_source": lambda d: d["commands"][0].pop("range_source"),
    "bad range_source": lambda d: d["commands"][0].update(range_source="guess"),
    "bad class": lambda d: d["commands"][0].update({"class": "weird"}),
    "bad type": lambda d: d["commands"][0].update(type="float"),
    "bad compare": lambda d: d["commands"][0].update(compare="approx"),
    "bad range key": lambda d: d["commands"][0]["range"].update(bogus=1),
    "non-numeric range": lambda d: d["commands"][0]["range"].update(min="40"),
    "non-bool risky": lambda d: d["commands"][0].update(risky="no"),
    "bad conditional range": lambda d: d["commands"][0].update(conditional_ranges=[{"min": 1}]),
    "duplicate command": lambda d: d["commands"].append(copy.deepcopy(d["commands"][0])),
    "duplicate topic": lambda d: d["topics"].append(copy.deepcopy(d["topics"][0])),
    "bad input class": lambda d: d.update(inputs=[{"path": "p", "class": "x", "retain": False, "type": "int",
                                                   "range": {}, "range_source": "heishamon_fact",
                                                   "min_firmware": "3.2.3", "ui_group": "s0", "label": {"en": "a", "nl": "b"}}]),
    "missing command ui_group": lambda d: d["commands"][0].pop("ui_group"),
    "unknown command ui_group": lambda d: d["commands"][0].update(ui_group="misc"),
    "unknown input ui_group": lambda d: d.update(inputs=[{"path": "p", "class": "input", "retain": False, "type": "int",
                                                          "range": {}, "range_source": "heishamon_fact",
                                                          "min_firmware": "3.2.3", "ui_group": "misc",
                                                          "label": {"en": "a", "nl": "b"}}]),
    "missing input ui_group": lambda d: d.update(inputs=[{"path": "p", "class": "input", "retain": False, "type": "int",
                                                          "range": {}, "range_source": "heishamon_fact",
                                                          "min_firmware": "3.2.3", "label": {"en": "a", "nl": "b"}}]),
    "bad model series": lambda d: d.update(models=[{"hex": _HEX, "name": "WH", "series": "Z"}]),
    "short model hex": lambda d: d.update(models=[{"hex": "AA BB", "name": "WH", "series": "J"}]),
    "lower-case model hex": lambda d: d.update(models=[{"hex": _HEX.lower(), "name": "WH", "series": "J"}]),
    "duplicate model hex": lambda d: d.update(models=[{"hex": _HEX, "name": "A", "series": "J"},
                                                      {"hex": _HEX, "name": "B", "series": "K"}]),
}


def test_model_lookup_normalises_payload():
    data = mutate(lambda d: d.update(models=[{"hex": _HEX, "name": "WH-X", "series": "other"}]))
    cat = catalog.parse(data)
    assert cat.model(_HEX)["name"] == "WH-X"
    assert cat.model("  " + _HEX.lower().replace(" ", "  ") + " ")["name"] == "WH-X"
    assert cat.model("00 11 22 33 44 55 66 77 88 99") is None
    assert cat.model(None) is None


@pytest.mark.parametrize("name", VIOLATIONS)
def test_violation_rejected(name):
    with pytest.raises(CatalogError):
        catalog.parse(mutate(VIOLATIONS[name]))


def test_invalid_json(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{nope")
    with pytest.raises(CatalogError):
        catalog.load(p)


def test_applicability_series_is_a_string_list():
    r = raw()
    r["commands"][0]["applicability"] = {"series": ["J"]}
    assert catalog.parse(r).commands[0]["applicability"] == {"series": ["J"]}
    r["commands"][0]["applicability"] = {"series": "J"}
    with pytest.raises(CatalogError):
        catalog.parse(r)
