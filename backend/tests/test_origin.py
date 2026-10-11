"""Spec §13: one case per bullet of the browser-origin, Host and CSRF policy."""
import pytest
from starlette.testclient import WebSocketDenialResponse
from starlette.websockets import WebSocketDisconnect

from heishamon_dashboard.origin import OriginPolicy

from .test_api import JSON, Rig

PREFS = {"write_lock": False, "pcb_enabled": False, "topic_visibility": {}, "feature_overrides": {},
         "tiles": [], "chart_presets": []}
MUTATIONS = [
    ("post", "/api/command", {"name": "SetDHWTemp", "value": 50, "confirm": False}),
    ("put", "/api/prefs", PREFS),
    ("post", "/api/system/flush", {}),
]


def send(rig, method, path, body, **headers):
    return getattr(rig.client, method)(path, json=body, headers=headers)


def ws_rejected(rig, **headers):
    """True when the handshake is refused (HTTP 403)."""
    try:
        with rig.client.websocket_connect("/api/ws", headers=headers) as ws:
            ws.receive_json()
    except WebSocketDenialResponse as denial:
        assert denial.status_code == 403
        return True
    except WebSocketDisconnect:  # servers without the denial extension close before accept
        return True
    return False


@pytest.fixture
def rig(tmp_path):
    with Rig(tmp_path, env={"ALLOWED_ORIGINS": "https://embed.example.test"}) as r:
        r.prime()
        yield r


@pytest.mark.parametrize("method,path,body", MUTATIONS)
def test_untrusted_origin_is_403_bad_origin(rig, method, path, body):
    response = send(rig, method, path, body, origin="https://evil.example.test")
    assert response.status_code == 403
    assert response.json() == {"error": "bad_origin", "message": response.json()["message"], "detail": None}
    assert rig.broker.published == []


@pytest.mark.parametrize("method,path,body", MUTATIONS)
def test_null_origin_is_403(rig, method, path, body):
    assert send(rig, method, path, body, origin="null").status_code == 403


def test_a_rejected_origin_has_no_side_effects(rig):
    send(rig, "post", "/api/command", MUTATIONS[0][2], origin="https://evil.example.test")
    send(rig, "put", "/api/prefs", {**PREFS, "write_lock": True}, origin="null")
    assert rig.client.get("/api/prefs").json()["write_lock"] is False
    assert rig.client.get("/api/commands").json() == {"commands": []}
    assert rig.client.get("/api/events?kind=command_rejected").json() == {"events": []}


@pytest.mark.parametrize("method,path,body", MUTATIONS)
def test_absent_origin_is_allowed(rig, method, path, body):
    assert "origin" not in {k.lower() for k in rig.client.headers}
    assert send(rig, method, path, body).status_code in (200, 201, 202)


def test_derived_same_origin_matches_with_the_scheme_ignored(rig):
    for origin in ("http://testserver", "https://testserver", "HTTP://TESTSERVER"):
        assert send(rig, "put", "/api/prefs", PREFS, origin=origin).status_code == 200, origin
    # the host[:port] must match exactly
    for origin in ("http://testserver:8000", "http://other", "https://testserver.evil.test"):
        assert send(rig, "put", "/api/prefs", PREFS, origin=origin).status_code == 403, origin
    response = send(rig, "put", "/api/prefs", PREFS, origin="http://localhost:8000", host="localhost:8000")
    assert response.status_code == 200


def test_x_forwarded_headers_are_never_trusted(rig):
    response = send(rig, "put", "/api/prefs", PREFS, origin="https://evil.example.test",
                    **{"x-forwarded-host": "evil.example.test", "x-forwarded-proto": "https"})
    assert response.status_code == 403


def test_allowed_origins_are_trusted_and_get_cors_headers(rig):
    response = send(rig, "put", "/api/prefs", PREFS, origin="https://embed.example.test")
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://embed.example.test"
    assert "access-control-allow-credentials" not in response.headers
    assert response.headers["vary"] == "Origin"


def test_cors_headers_only_for_allowed_origins(rig):
    ok = rig.client.get("/api/state", headers={"origin": "https://embed.example.test"})
    assert ok.headers["access-control-allow-origin"] == "https://embed.example.test"
    for origin in ("https://evil.example.test", "http://testserver", "null"):
        other = rig.client.get("/api/state", headers={"origin": origin})
        assert other.status_code == 200  # reads are not blocked server-side, just not CORS-enabled
        assert not any(h.lower().startswith("access-control-") for h in other.headers), origin
    assert not any(h.lower().startswith("access-control-") for h in rig.client.get("/api/state").headers)


def test_preflight_headers_only_for_allowed_origins(rig):
    request = {"access-control-request-method": "PUT", "access-control-request-headers": "content-type"}
    ok = rig.client.options("/api/prefs", headers={"origin": "https://embed.example.test", **request})
    assert ok.status_code == 204
    assert ok.headers["access-control-allow-origin"] == "https://embed.example.test"
    assert "PUT" in ok.headers["access-control-allow-methods"]
    assert ok.headers["access-control-allow-headers"].lower() == "content-type"
    for origin in ("https://evil.example.test", "http://testserver"):
        denied = rig.client.options("/api/prefs", headers={"origin": origin, **request})
        assert not any(h.lower().startswith("access-control-") for h in denied.headers), origin


@pytest.mark.parametrize("method,path,body", MUTATIONS)
def test_non_json_bodies_are_415(rig, method, path, body):
    for ctype in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x"):
        response = getattr(rig.client, method)(path, content=b"a=b", headers={"content-type": ctype})
        assert response.status_code == 415, ctype
    assert getattr(rig.client, method)(path, content=b"{}").status_code == 415  # no content type at all
    assert rig.broker.published == []


def test_415_comes_after_the_origin_check(rig):
    response = rig.client.put("/api/prefs", content=b"x", headers={
        "content-type": "text/plain", "origin": "https://evil.example.test"})
    assert response.status_code == 403


def test_json_content_type_with_charset_is_fine(rig):
    response = rig.client.put("/api/prefs", content=b'{"write_lock": false, "pcb_enabled": false, '
                              b'"topic_visibility": {}, "feature_overrides": {}, "tiles": [], '
                              b'"chart_presets": []}',
                              headers={"content-type": "application/json; charset=utf-8"})
    assert response.status_code == 200


def test_websocket_handshake_follows_the_same_origin_rules(rig):
    assert not ws_rejected(rig)  # absent Origin
    assert not ws_rejected(rig, origin="http://testserver")  # derived same origin
    assert not ws_rejected(rig, origin="https://testserver")  # scheme ignored
    assert not ws_rejected(rig, origin="https://embed.example.test")  # ALLOWED_ORIGINS
    assert ws_rejected(rig, origin="https://evil.example.test")
    assert ws_rejected(rig, origin="null")


def test_origin_policy_unit():
    p = OriginPolicy(["https://heat.example.test"], ["https://embed.example.test:8443"])
    assert p.host_ok("heat.example.test") and p.host_ok("HEAT.example.test")
    assert not p.host_ok("evil.test") and not p.host_ok(None)
    assert p.trusted("https://heat.example.test", "heat.example.test")
    assert not p.trusted("http://heat.example.test", "heat.example.test")  # exact set when configured
    assert p.trusted("https://embed.example.test:8443", "heat.example.test")
    assert p.cors_origin("https://embed.example.test:8443") == "https://embed.example.test:8443"
    assert p.cors_origin("https://heat.example.test") is None and p.cors_origin("null") is None
    open_policy = OriginPolicy([], [])
    assert open_policy.host_ok("anything") and open_policy.host_ok(None)
    assert open_policy.trusted("https://a.test:1", "a.test:1") and not open_policy.trusted("http://a.test", "a.test:1")


# --------------------------------------------------------------- PUBLIC_ORIGINS


@pytest.fixture
def public_rig(tmp_path):
    env = {"PUBLIC_ORIGINS": "https://heat.example.test", "ALLOWED_ORIGINS": "https://embed.example.test"}
    with Rig(tmp_path, env=env) as r:
        r.prime()
        yield r


@pytest.mark.parametrize("headers", [{}, {"host": "evil.example.test"}, {"host": "heat.example.test:8000"}])
def test_bad_host_is_403_bad_host_with_public_origins(public_rig, headers):
    if not headers:
        headers = {"host": "testserver"}
    response = public_rig.client.get("/api/state", headers=headers)
    assert response.status_code == 403 and response.json()["error"] == "bad_host"
    response = public_rig.client.put("/api/prefs", json=PREFS, headers={**headers, "origin": "https://heat.example.test"})
    assert response.status_code == 403 and response.json()["error"] == "bad_host"
    assert ws_rejected(public_rig, **headers)


def test_proxy_case_rest_and_websocket_pass(public_rig):
    host = {"host": "heat.example.test", "origin": "https://heat.example.test"}  # TLS ended at the proxy; plain http here
    assert public_rig.client.get("/api/state", headers=host).status_code == 200
    assert public_rig.client.put("/api/prefs", json=PREFS, headers=host).status_code == 200
    assert public_rig.client.post("/api/command", json={"name": "SetDHWTemp", "value": 50, "confirm": False},
                                  headers=host).status_code == 201
    assert not ws_rejected(public_rig, **host)
    assert not ws_rejected(public_rig, host="heat.example.test")  # absent Origin


def test_with_public_origins_the_trusted_set_is_exact(public_rig):
    host = {"host": "heat.example.test"}
    for origin in ("http://heat.example.test", "https://testserver", "https://evil.example.test"):
        response = public_rig.client.put("/api/prefs", json=PREFS, headers={**host, "origin": origin})
        assert response.status_code == 403 and response.json()["error"] == "bad_origin", origin
        assert ws_rejected(public_rig, **host, origin=origin)
    allowed = public_rig.client.put("/api/prefs", json=PREFS, headers={**host, "origin": "https://embed.example.test"})
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://embed.example.test"
