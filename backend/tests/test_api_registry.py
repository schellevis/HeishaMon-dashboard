"""The (method, path) route set of the app, captured before the api module became a package (R6)."""
from .test_api import Rig

EXPECTED = {
    ("GET", "/api/state"),
    ("GET", "/api/profile"),
    ("GET", "/api/history"),
    ("GET", "/api/history.csv"),
    ("POST", "/api/command"),
    ("GET", "/api/commands/{command_id}"),
    ("GET", "/api/commands"),
    ("GET", "/api/events"),
    ("GET", "/api/prefs"),
    ("PUT", "/api/prefs"),
    ("GET", "/api/system"),
    ("GET", "/api/overlay"),
    ("GET", "/api/energy"),
    ("POST", "/api/system/flush"),
    ("WS", "/api/ws"),
    *((m, "/{path:path}") for m in ("GET", "HEAD", "POST", "PUT", "DELETE", "PATCH")),
}
FRAMEWORK = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def flat_routes(routes):
    """Routes in matching order, looking through the wrapper newer FastAPI puts around included routers."""
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from flat_routes(inner.routes)
        elif route.path not in FRAMEWORK:
            yield route


def test_route_set_is_unchanged(tmp_path):
    with Rig(tmp_path) as rig:
        found = set()
        for route in flat_routes(rig.app.routes):
            if hasattr(route, "methods"):
                found |= {(m, route.path) for m in route.methods}
            else:
                found.add(("WS", route.path))
    assert found == EXPECTED


def test_spa_catch_all_is_registered_last(tmp_path):
    with Rig(tmp_path) as rig:
        assert list(flat_routes(rig.app.routes))[-1].path == "/{path:path}"
