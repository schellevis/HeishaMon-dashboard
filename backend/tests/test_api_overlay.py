"""GET /api/overlay: the T08 result shape, parameter validation and the 400-day limit."""
import pytest

from .test_api import T0, Rig

OVERLAY_KEYS = {"zone", "mode", "boundary_ts", "windows", "median", "histogram"}
WINDOW_KEYS = {"start_ts", "outside", "water", "target", "water_minus_target", "cop", "freq",
               "room_minus_setpoint", "side", "eligible_minutes"}
DAY = 86_400_000


@pytest.fixture
def rig(tmp_path):
    with Rig(tmp_path) as r:
        yield r


def test_empty_overlay_has_the_exact_shape(rig):
    body = rig.client.get(f"/api/overlay?zone=z1&mode=heat&from={T0}&to={T0 + DAY}").json()
    assert body == {"zone": "z1", "mode": "heat", "boundary_ts": None, "windows": [], "median": [],
                    "histogram": []}


@pytest.mark.parametrize("query", [
    "zone=z3&mode=heat",
    "zone=zone1&mode=heat",
    "zone=z1&mode=auto",
    "zone=z1&mode=dhw",
    "mode=heat",
    "zone=z1",
])
def test_bad_zone_or_mode_is_422(rig, query):
    response = rig.client.get(f"/api/overlay?{query}&from={T0}&to={T0 + DAY}")
    assert response.status_code == 422
    assert set(response.json()) == {"error", "message", "detail"}


@pytest.mark.parametrize("window", [
    "from=5&to=5",
    "from=9&to=5",
    "from=x&to=5",
    "to=5",
    "from=5",
])
def test_bad_range_is_422(rig, window):
    assert rig.client.get(f"/api/overlay?zone=z1&mode=heat&{window}").status_code == 422


def test_range_limit_is_400_days(rig):
    ok = rig.client.get(f"/api/overlay?zone=z2&mode=cool&from={T0}&to={T0 + 400 * DAY}")
    assert ok.status_code == 200 and ok.json()["zone"] == "z2" and ok.json()["mode"] == "cool"
    over = rig.client.get(f"/api/overlay?zone=z2&mode=cool&from={T0}&to={T0 + 400 * DAY + 1}")
    assert over.status_code == 422 and over.json()["error"] == "out_of_range"


def feed_minute(rig, minute, extra=None):
    rig.clock.t = T0 + minute * 60_000
    rig.feed("LWT", "Online")
    values = {
        "main/Outside_Temp": "5", "main/Main_Outlet_Temp": "35", "main/Z1_Water_Target_Temp": "34",
        "main/Operating_Mode_State": "0", "main/ThreeWay_Valve_State": "0",
        "main/Defrosting_State": "0", "main/Compressor_Freq": "40",
        "main/Heat_Power_Production": "4000", "main/Heat_Power_Consumption": "1000",
        "main/Z1_Sensor_Settings": "0",
    }
    values.update(extra or {})
    for topic, payload in values.items():
        rig.feed(topic, payload)


def test_overlay_returns_eligible_windows_from_the_real_store(rig):
    for minute in range(0, 41):
        feed_minute(rig, minute)
    # a 15-minute window needs 12 eligible minutes and a clean 10-minute lead-in
    body = rig.client.get(f"/api/overlay?zone=z1&mode=heat&from={T0 + 15 * 60_000}&to={T0 + 40 * 60_000}").json()
    assert set(body) == OVERLAY_KEYS and body["zone"] == "z1" and body["mode"] == "heat"
    assert body["boundary_ts"] is None
    assert [w["start_ts"] for w in body["windows"]] == [T0 + 15 * 60_000]
    window = body["windows"][0]
    assert set(window) == WINDOW_KEYS
    assert window["outside"] == 5 and window["water"] == 35 and window["target"] == 34
    assert window["water_minus_target"] == 1 and window["cop"] == 4 and window["freq"] == 40
    assert window["eligible_minutes"] == 15 and window["side"] is None
    assert window["room_minus_setpoint"] is None  # a water sensor: no room reading
    assert body["median"] == []  # fewer than three windows in the band
    assert body["histogram"] == [{"band_lo": 4, "hours": 0.25}]


def test_the_zones_own_water_sensor_is_used_when_it_has_a_reading(rig):
    for minute in range(0, 41):
        feed_minute(rig, minute, {"main/Z1_Water_Temp": "37"})
    body = rig.client.get(f"/api/overlay?zone=z1&mode=heat&from={T0 + 15 * 60_000}&to={T0 + 30 * 60_000}").json()
    assert body["windows"][0]["water"] == 37
    # a sentinel (absent sensor) falls back to the common outlet temperature
    for minute in range(41, 82):
        feed_minute(rig, minute, {"main/Z1_Water_Temp": "-128"})
    body = rig.client.get(f"/api/overlay?zone=z1&mode=heat&from={T0 + 60 * 60_000}&to={T0 + 75 * 60_000}").json()
    assert body["windows"] and body["windows"][0]["water"] == 35


def test_a_confirmed_setcurves_gives_boundary_and_side(rig):
    for minute in range(0, 41):
        feed_minute(rig, minute)
    rig.clock.t = T0 + 20 * 60_000 + 7_000
    rig.svc.store.append_command({
        "uuid": "c1", "name": "SetCurves", "payload": "{}", "retained": False, "class": "setting",
        "status": "confirmed", "submitted_ts": rig.clock.t, "published_ts": rig.clock.t,
        "confirmed_ts": rig.clock.t + 3_000, "attempts": 1, "prev_value": None, "detail": None,
        "keys": {"main/Z1_Heat_Curve_Target_High_Temp": {"expected": 40, "status": "confirmed"}},
    })
    rig.clock.t = T0 + 41 * 60_000
    rig.feed("LWT", "Online")
    body = rig.client.get(f"/api/overlay?zone=z1&mode=heat&from={T0 + 15 * 60_000}&to={T0 + 40 * 60_000}").json()
    assert body["boundary_ts"] == T0 + 20 * 60_000 + 10_000
    assert [w["side"] for w in body["windows"]] == ["boundary"]
    other = rig.client.get(f"/api/overlay?zone=z2&mode=heat&from={T0}&to={T0 + DAY}").json()
    assert other["boundary_ts"] is None
