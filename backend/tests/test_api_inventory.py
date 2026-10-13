"""A2 (plan review I4): every catalog command and input goes through POST /api/command and reaches the
fake publisher with the exact topic, payload and retain flag."""
import json
from pathlib import Path

import pytest

from heishamon_dashboard import catalog as catalog_mod

from .test_origin import PREFS
from .test_api import BASE, Rig

CATALOG = catalog_mod.load(Path(__file__).parent.parent / "heishamon_dashboard" / "catalog.json")
COMMANDS = [c["name"] for c in CATALOG.commands]
INPUTS = [i["path"] for i in CATALOG.inputs]

# values already held by the primed installation (a command equal to its read-back is a no-op)
CURRENT = {"SetOperationMode": 0, "SetZones": 2, "SetBuffer": 1, "SetBivalentControl": 1}

CURVES_VALUE = {"zone1": {"heat": {"target": {"high": 40, "low": 30}, "outside": {"high": 15, "low": -5}}}}
CURVES_PAYLOAD = '{"zone1":{"heat":{"target":{"high":40,"low":30},"outside":{"high":15,"low":-5}}}}'


def expected_payload(type_, value):
    """Independent of encoding.py: the §4.4 value-encoding table."""
    if type_ in ("int", "bool", "int12"):
        return str(value)
    if type_ == "int2":
        return f"{value:02d}"
    if type_ == "dec1":
        return f"{value:.1f}"
    if type_ == "dec3":
        text = f"{value:.3f}".rstrip("0").rstrip(".")
        return text
    raise AssertionError(type_)


def pick(entry, current=None):
    """A valid value for an entry (the top of its range or allowed set, else the bottom)."""
    allowed = entry.get("allowed")
    if allowed is not None:
        candidates = list(reversed(allowed))
    else:
        rng = entry["range"]
        if entry["type"] == "dec3":
            candidates = [123456.789]
        else:
            candidates = [rng["max"], rng["min"]]
    for value in candidates:
        if value != current:
            return value
    raise AssertionError("no candidate")


@pytest.fixture(scope="module")
def rig(tmp_path_factory):
    with Rig(tmp_path_factory.mktemp("inventory")) as r:
        r.prime()
        r.feed("optional/Anything", "1")  # optional-PCB emulation is live
        response = r.client.put("/api/prefs", json={**PREFS, "pcb_enabled": True})
        assert response.status_code == 200
        yield r


def risky(entry):
    """§6: switching the heat pump on is harmless, only SetHeatpump 0 needs a confirmation."""
    if entry.get("name") == "SetHeatpump":
        return False
    return bool(entry.get("pcb") or entry["class"] in ("trigger", "retained_exception")
                or entry.get("risky")
                or (entry.get("applicability") or {}).get("series"))  # K4: the series is unknown in this rig


def test_inventory_covers_the_whole_catalog():
    assert len(COMMANDS) == 64 and len(INPUTS) == 18
    assert set(COMMANDS) | set(INPUTS) == {e["name"] for e in CATALOG.commands} | {e["path"] for e in CATALOG.inputs}


@pytest.mark.parametrize("name", COMMANDS)
def test_every_catalog_command(rig, name):
    entry = CATALOG.command(name)
    if name == "SetCurves":
        value, payload = CURVES_VALUE, CURVES_PAYLOAD
    else:
        value = pick(entry, CURRENT.get(name))
        payload = expected_payload(entry["type"], value)
    needs_confirm = risky(entry) or (name == "SetHeatpump" and value == 0)
    rig.broker.published.clear()
    if needs_confirm:
        rejected = rig.post(name, value, confirm=False)
        assert rejected.status_code == 422 and rejected.json()["error"] == "confirm_required"
        assert rig.broker.published == []
    response = rig.post(name, value, confirm=needs_confirm)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == name and body["payload"] == payload and body["retained"] is False
    assert body["class"] == entry["class"]
    assert body["status"] == ("pending" if entry["class"] == "setting" else "sent")
    assert rig.broker.published == [(f"{BASE}/commands/{name}", payload, 0, False)]


@pytest.mark.parametrize("path", INPUTS)
def test_every_catalog_input(rig, path):
    entry = CATALOG.input(path)
    value = pick(entry)
    payload = expected_payload(entry["type"], value)
    retained = entry["class"] == "retained_exception"
    assert entry["retain"] is retained
    rig.broker.published.clear()
    if retained:
        rejected = rig.post(path, value, confirm=False)
        assert rejected.status_code == 422 and rejected.json()["error"] == "confirm_required"
        assert rig.broker.published == []
    response = rig.post(path, value, confirm=retained)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == path and body["payload"] == payload and body["retained"] is retained
    assert body["class"] == entry["class"] and body["status"] == "sent"
    assert rig.broker.published == [(f"{BASE}/{path}", payload, 0, retained)]


def test_spec_fixtures_for_value_encoding(rig):
    rig.broker.published.clear()
    assert rig.post("SetPoolTemp", 20.5, confirm=True).json()["payload"] == "20.5"
    assert rig.post("SetPoolTemp", 20, confirm=True).json()["payload"] == "20.0"
    assert rig.post("s0/WatthourTotal/1", 123456.789, confirm=True).json()["payload"] == "123456.789"
    assert rig.post("s0/WatthourTotal/2", 5000, confirm=True).json()["payload"] == "5000"
    assert rig.post("opentherm/read/outsideTemp", 7.5).json()["payload"] == "7.5"
    assert rig.post("SetSterilizationTemp", 60).json()["payload"] == "60"
    assert rig.broker.published == [
        (f"{BASE}/commands/SetPoolTemp", "20.5", 0, False),
        (f"{BASE}/commands/SetPoolTemp", "20.0", 0, False),
        (f"{BASE}/s0/WatthourTotal/1", "123456.789", 0, True),
        (f"{BASE}/s0/WatthourTotal/2", "5000", 0, True),
        (f"{BASE}/opentherm/read/outsideTemp", "7.5", 0, False),
        (f"{BASE}/commands/SetSterilizationTemp", "60", 0, False),
    ]


def test_switching_the_heat_pump_off_needs_confirm(rig):
    rig.broker.published.clear()
    assert rig.post("SetHeatpump", 0).json()["error"] == "confirm_required"
    assert rig.post("SetHeatpump", 0, confirm=True).status_code == 201
    assert rig.broker.published == [(f"{BASE}/commands/SetHeatpump", "0", 0, False)]


def test_value_encoding_rejections(rig):
    rig.broker.published.clear()
    for name, value, code in [
        ("SetDHWTemp", 50.0, "bad_type"),  # an integer literal is required
        ("SetPoolTemp", 20.25, "bad_type"),  # at most one fractional digit
        ("SetPoolTemp", 20.1, "bad_step"),  # off the 0.5 grid
        ("s0/WatthourTotal/1", 1.2345, "bad_type"),
        ("s0/WatthourTotal/1", -1, "out_of_range"),
        ("SetCurves", [1], "bad_type"),
        ("SetCurves", {"zone1": {"heat": {"target": {"high": 99}}}}, "out_of_range"),
        ("SetHeatpump", 2, "not_allowed_value"),
        ("opentherm/read/chPressure", "7", "bad_type"),
    ]:
        response = rig.post(name, value, confirm=True)
        assert response.status_code == 422 and response.json()["error"] == code, (name, value, response.text)
    assert rig.broker.published == []
