"""GET and PUT /api/prefs (spec §4.4 `Prefs`)."""
import logging
import sqlite3

from fastapi import APIRouter, Request

from heishamon_dashboard import rules

from .common import ApiError, json_body

log = logging.getLogger(__name__)

TOPIC_KEY_MAX_BYTES = 256
VISIBILITY = ("visible", "hidden", "ignored")
PREF_KEYS = ("write_lock", "pcb_enabled", "topic_visibility", "feature_overrides", "tiles", "chart_presets")


def _bad_visibility_key(key: str) -> bool:
    return (len(key.encode("utf-8")) > TOPIC_KEY_MAX_BYTES or "+" in key or "#" in key
            or key.startswith("/") or key == "")


def validate_prefs(obj, known_topic=None, known_tile=None) -> str | None:
    """Return a message for the first violation of the §4.4 `Prefs` schema, else None.

    `known_topic(key)` says whether a key is catalogued or present in `State`; without it only the
    key format is checked. `known_tile(entry)` says whether a `tiles` entry is a built-in tile id or a
    catalogued topic key; without it only the type is checked.
    """
    if not isinstance(obj, dict):
        return "the body must be an object"
    for key in obj:
        if key not in PREF_KEYS:
            return f"unknown key {key!r}"
    for key in PREF_KEYS:
        if key not in obj:
            return f"missing key {key!r}"
    for key in ("write_lock", "pcb_enabled"):
        if not isinstance(obj[key], bool):
            return f"{key} must be a boolean"
    tv = obj["topic_visibility"]
    if not isinstance(tv, dict) or any(not isinstance(k, str) or v not in VISIBILITY for k, v in tv.items()):
        return "topic_visibility must map topic keys to visible, hidden or ignored"
    for key in tv:
        if _bad_visibility_key(key):
            return f"topic_visibility key {key[:64]!r} is not a valid topic key"
        if known_topic is not None and not known_topic(key):
            return f"topic_visibility key {key[:64]!r} is not a known topic"
    fo = obj["feature_overrides"]
    if not isinstance(fo, dict) or any(not isinstance(k, str) or v != "show" for k, v in fo.items()):
        return 'feature_overrides must map feature ids to "show"'
    if not isinstance(obj["tiles"], list) or any(not isinstance(t, str) for t in obj["tiles"]):
        return "tiles must be a list of topic keys"
    if known_tile is not None:
        for t in obj["tiles"]:
            if not known_tile(t):
                return f"tiles entry {t[:64]!r} is neither a built-in tile id nor a catalogued topic key"
    presets = obj["chart_presets"]
    if not isinstance(presets, list):
        return "chart_presets must be a list"
    for p in presets:
        if (not isinstance(p, dict) or set(p) != {"name", "topics"} or not isinstance(p["name"], str)
                or not isinstance(p["topics"], list) or any(not isinstance(t, str) for t in p["topics"])):
            return "each chart preset needs a name and a list of topics"
    return None


def default_prefs() -> dict:
    return {"write_lock": False, "pcb_enabled": False, "topic_visibility": {}, "feature_overrides": {},
            "tiles": [], "chart_presets": []}


def _known_tile(svc, entry) -> bool:
    return isinstance(entry, str) and (entry in rules.load().tiles or svc.catalog.topic(entry) is not None)


def current_prefs(svc) -> dict:
    prefs = default_prefs()
    prefs.update({k: v for k, v in svc.store.prefs_get().items() if k in PREF_KEYS})
    tv = prefs["topic_visibility"]
    if isinstance(tv, dict):
        bad = [k for k in tv if not isinstance(k, str) or _bad_visibility_key(k)]
        if bad:
            log.warning("dropping %d invalid topic_visibility key(s) from stored preferences", len(bad))
            prefs["topic_visibility"] = {k: v for k, v in tv.items() if k not in bad}
    tiles = prefs["tiles"]
    if isinstance(tiles, list):
        bad = [t for t in tiles if not _known_tile(svc, t)]
        if bad:
            log.warning("dropping %d invalid tiles entr(ies) from stored preferences", len(bad))
            prefs["tiles"] = [t for t in tiles if t not in bad]
    return prefs


def register(router: APIRouter, svc) -> None:
    store, state = svc.store, svc.state

    @router.get("/api/prefs")
    async def get_prefs():
        return current_prefs(svc)

    @router.put("/api/prefs")
    async def put_prefs(request: Request):
        body = await json_body(request)
        stored = current_prefs(svc)["topic_visibility"]  # keys saved earlier stay saveable
        problem = validate_prefs(
            body, lambda k: svc.catalog.topic(k) is not None or k in state.values or k in stored,
            lambda t: _known_tile(svc, t))
        if problem:
            raise ApiError(422, "bad_type", problem)
        old = {k for k, v in current_prefs(svc)["topic_visibility"].items() if v == "ignored"}
        new = {k for k, v in body["topic_visibility"].items() if v == "ignored"}
        try:
            store.prefs_put(body)
        except sqlite3.Error as exc:
            raise ApiError(503, "storage_unavailable", f"could not save preferences: {exc}") from None
        now = svc.clock.now_ms()
        for topic in sorted(new - old):
            store.set_ignored(topic, True, now)
        for topic in sorted(old - new):
            store.set_ignored(topic, False, now)
        return current_prefs(svc)
