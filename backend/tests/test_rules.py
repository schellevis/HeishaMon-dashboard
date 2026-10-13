import copy
import json
import re
from pathlib import Path

import pytest

from heishamon_dashboard import curve, derived, rules
from heishamon_dashboard.rules import RulesError

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "backend" / "heishamon_dashboard"
CASES = json.loads((Path(__file__).parent / "fixtures" / "rules_cases.json").read_text())
RAW = json.loads((PKG / "rules.json").read_text())


def test_loads_default_file():
    r = rules.load()
    assert r.curve_shift == (-5, 5)
    assert r.curve_limits["heat"]["target"] == (15, 75)
    assert r.operating_modes["read_only"] == {7, 8}
    assert r.room_sensor_values == {1, 2, 3}
    assert r.s0_meters == ("s0/WatthourTotal/1", "s0/WatthourTotal/2")
    assert "outsideTemp" in r.tiles and len(r.tiles) == len(set(r.tiles))


def test_missing_and_malformed_file(tmp_path):
    with pytest.raises(RulesError):
        rules.load(tmp_path / "nope.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(RulesError):
        rules.load(bad)


def _mut(fn):
    d = copy.deepcopy(RAW)
    fn(d)
    return d


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(schema=2),
    lambda d: d.pop("tiles"),
    lambda d: d.update(extra_key=1),
    lambda d: d["curve_limits"]["heat"].update(outside=[30, -20]),
    lambda d: d["curve_limits"]["heat"].update(outside=[1]),
    lambda d: d.update(curve_shift=["a", "b"]),
    lambda d: d.update(curve_leaf="main/Z{zone}_{Mode}_Curve_{Group}_Temp"),
    lambda d: d["curve_ends"]["cold"].update(outside="Up"),
    lambda d: d["curve_ends"]["warm"].update(outside="Low"),
    lambda d: d["operating_modes"].update(heating=[]),
    lambda d: d.update(room_sensor_values=[True]),
    lambda d: d["power_pairs"]["main"]["heat"].append("x"),
    lambda d: d["power_pairs"]["extra"].pop("dhw"),
    lambda d: d.update(s0_meters=[]),
    lambda d: d.update(tiles=["a", "a"]),
])
def test_validation_errors(mutate):
    with pytest.raises(RulesError):
        rules.parse(_mut(mutate))


@pytest.mark.parametrize("c", CASES["curve_validity"])
def test_curve_validity_cases(c):
    lo, hi = rules.load().curve_limits[c["mode"]][c["group"]]
    assert (lo <= c["value"] <= hi) is c["valid"]


@pytest.mark.parametrize("c", CASES["leaf_names"])
def test_leaf_name_cases(c):
    r = rules.load()
    assert r.leaf_for_end(c["zone"], c["mode"], c["end"], c["group"]) == c["topic"]
    assert r.leaf_regex().match(c["topic"]).groups() == (
        str(c["zone"]), c["mode"].capitalize(), c["group"].capitalize(), r.curve_ends[c["end"]][c["group"]])


@pytest.mark.parametrize("c", CASES["power_selection"])
def test_power_selection_cases(c):
    profile = {"has_extra": {"value": c["has_extra"], "unknown": False}}
    topics, estimate = derived.power_topics(profile)
    assert list(topics[c["mode"]]) == c["topics"]
    assert estimate is (not c["has_extra"])


def test_curve_module_reads_rules():
    r = rules.load()
    assert curve.leaf_key(1, "heat", "cold", "target") == "Z1_Heat_Curve_Target_High_Temp"
    assert curve.LIMITS["cool"]["target"] == r.curve_limits["cool"]["target"]


# Mode sets and curve leaf patterns live in rules.json only (Python sources).
_LITERALS = re.compile(r"[{\[(]\s*0,\s*2,\s*4,\s*6\s*[})\]]|[{\[(]\s*1,\s*5,\s*7,\s*8\s*[})\]]")
_LEAF_BUILD = re.compile(r"""["'][^"'\n]*_Curve_""")


@pytest.mark.parametrize("path", sorted(PKG.rglob("*.py")) + [ROOT / "tools" / "simulator.py"],
                         ids=lambda p: str(p.relative_to(ROOT)))
def test_no_hard_coded_rules(path):
    if path.name == "rules.py":
        pytest.skip("rules.py implements the rules")
    text = path.read_text()
    assert not _LITERALS.search(text), "mode set literal outside rules.json"
    assert not _LEAF_BUILD.search(text), "curve leaf pattern outside rules.json"
