"""REST and WebSocket routes (spec §4.4)."""
import asyncio
import json
import re
import sqlite3
import uuid as uuidlib
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request, WebSocket
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.websockets import WebSocketDisconnect

from heishamon_dashboard import curve
from heishamon_dashboard.commands import CommandService, error_body

MAX_TOPICS = 20
MAX_OVERLAY_MS = 400 * 86_400_000
VISIBILITY = ("visible", "hidden", "ignored")
PREF_KEYS = ("write_lock", "pcb_enabled", "topic_visibility", "feature_overrides", "tiles", "chart_presets")
_INT = re.compile(r"^-?\d+$")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, detail: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.detail = status, code, message, detail


def _error(status: int, code: str, message: str, detail: dict | None = None) -> JSONResponse:
    return JSONResponse(error_body(code, message, detail), status_code=status)


def _param_int(q, name: str, lo: int | None = None, hi: int | None = None, default: int | None = None) -> int:
    raw = q.get(name)
    if raw is None or raw == "":
        if default is not None:
            return default
        raise ApiError(422, "bad_type", f"query parameter {name!r} is required")
    if not _INT.match(raw):
        raise ApiError(422, "bad_type", f"query parameter {name!r} must be an integer")
    value = int(raw)
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        raise ApiError(422, "out_of_range", f"{name!r} must be within {lo}..{hi}", {"min": lo, "max": hi})
    return value


def _range_params(q) -> tuple[int, int]:
    a, b = _param_int(q, "from"), _param_int(q, "to")
    if a >= b:
        raise ApiError(422, "out_of_range", "'from' must be before 'to'")
    return a, b


async def _json_body(request: Request):
    raw = await request.body()
    try:
        return json.loads(raw, parse_constant=_reject_constant)
    except ValueError:
        raise ApiError(400, "bad_request", "malformed JSON") from None


def _reject_constant(name):
    raise ValueError(name)


def validate_prefs(obj) -> str | None:
    """Return a message for the first violation of the §4.4 `Prefs` schema, else None."""
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
    fo = obj["feature_overrides"]
    if not isinstance(fo, dict) or any(not isinstance(k, str) or v != "show" for k, v in fo.items()):
        return 'feature_overrides must map feature ids to "show"'
    if not isinstance(obj["tiles"], list) or any(not isinstance(t, str) for t in obj["tiles"]):
        return "tiles must be a list of topic keys"
    presets = obj["chart_presets"]
    if not isinstance(presets, list):
        return "chart_presets must be a list"
    for p in presets:
        if (not isinstance(p, dict) or set(p) != {"name", "topics"} or not isinstance(p["name"], str)
                or not isinstance(p["topics"], list) or any(not isinstance(t, str) for t in p["topics"])):
            return "each chart preset needs a name and a list of topics"
    return None


def _csv_field(text: str, force: bool = False) -> str:
    if force or any(c in text for c in ',"\r\n'):
        return '"' + text.replace('"', '""') + '"'
    return text


def _csv_number(v) -> str:
    if v is None:
        return ""
    return str(v) if isinstance(v, int) else repr(v)


def history_csv(history: dict, order: list[str]) -> str:
    resolution = history["resolution"]
    lines = ["topic,ts,resolution,value,covered_seconds"]
    for topic in order:
        series = history["series"][topic]
        text = series["kind"] == "text"
        for point in series["points"]:
            if resolution == "raw" or text:
                ts, value, covered = point[0], point[1], ""
                res = "raw"
            else:
                ts, value, covered = point[0], point[1], str(point[2])
                res = resolution
            cell = _csv_field(value, force=True) if text else _csv_number(value)
            lines.append(f"{_csv_field(topic)},{ts},{res},{cell},{covered}")
    return "\r\n".join(lines) + "\r\n"


def _topic_value(svc, tv) -> dict:
    meta = svc.catalog.topic(tv.key)
    number = isinstance(tv.value, (int, float)) and not isinstance(tv.value, bool)
    label = None
    if meta and meta.get("enum") and tv.valid and number:
        label = meta["enum"].get(str(int(tv.value)))
    return {
        "value": tv.value if (number or isinstance(tv.value, str)) else None,
        "raw": tv.raw,
        "kind": tv.kind,
        "unit": meta.get("unit") if meta else None,
        "decimals": meta.get("decimals") if meta else None,
        "enum_label": {"en": label["en"], "nl": label["nl"]} if label else None,
        "catalogued": meta is not None,
        "sentinel": bool(meta and number and not tv.valid and tv.value in (meta.get("sentinels") or [])),
        "last_change": tv.last_change,
        "last_seen": tv.last_seen,
        "retained_only": tv.retained_only,
    }


def state_snapshot(svc) -> dict:
    st = svc.state
    return {
        "seq": st.seq,
        "topics": {k: _topic_value(svc, v) for k, v in st.values.items()},
        "device_online": st.device_online,
        "last_device_message": st.last_qualifying_ts,
        "broker_connected": svc.mqtt.connected,
        "listen_only_suspected": svc.commands.listen_only_suspected,
    }


def default_prefs() -> dict:
    return {"write_lock": False, "pcb_enabled": False, "topic_visibility": {}, "feature_overrides": {},
            "tiles": [], "chart_presets": []}


def current_prefs(svc) -> dict:
    prefs = default_prefs()
    prefs.update({k: v for k, v in svc.store.prefs_get().items() if k in PREF_KEYS})
    return prefs


def system_info(svc) -> dict:
    store = svc.store
    failing = store.failing
    overflow = sum(e["detail"].get("count", 0) for e in store.events_list(kinds=["buffer_overflow"], limit=1000))
    return {
        "broker_connected": svc.mqtt.connected,
        "device_online": svc.state.device_online,
        "firmware": svc.firmware(),
        "firmware_assumed": svc.firmware_assumed(),
        "stats": svc.stats(),
        "listen_only_suspected": svc.commands.listen_only_suspected,
        "db_bytes": store.db_bytes(),
        "last_flush_ts": store.last_flush_ts,
        "last_flush_ok": not failing,
        "last_flush_error": store.last_error if failing else None,
        "flush_interval_s": svc.config.flush_interval_seconds,
        "buffer": {"samples": store.sample_count, "sample_bytes": store.sample_bytes,
                   "protected": store.audit_count()},
        "dropped": {"samples": overflow, "ingest": svc.ingest_dropped_total + svc.state.ingest_dropped},
    }


def _refine_kinds(svc, history: dict) -> dict:
    for key, series in history["series"].items():
        meta = svc.catalog.topic(key)
        if series.get("kind") == "number" and meta and meta["kind"] == "enum":
            series["kind"] = "enum"
    return history


def _history_query(q) -> tuple[list[str], int, int, int]:
    raw = q.get("topics")
    topics = list(dict.fromkeys(t for t in (raw or "").split(",") if t))
    if not topics:
        raise ApiError(422, "bad_type", "query parameter 'topics' is required")
    if len(topics) > MAX_TOPICS:
        raise ApiError(422, "out_of_range", f"at most {MAX_TOPICS} topics per request")
    a, b = _range_params(q)
    return topics, a, b, _param_int(q, "max_points", 10, 10000, default=1000)


def register(app: FastAPI, svc, static_dir: Path) -> None:
    router = APIRouter()
    store, state, commands = svc.store, svc.state, svc.commands

    @app.exception_handler(ApiError)
    async def _api_error(_request, exc: ApiError):
        return _error(exc.status, exc.code, exc.message, exc.detail)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _error(exc.status_code, code, str(exc.detail))

    @router.get("/api/state")
    async def get_state():
        return state_snapshot(svc)

    @router.get("/api/profile")
    async def get_profile():
        return svc.profile()

    async def run_history(request: Request):
        topics, a, b, max_points = _history_query(request.query_params)
        liveness = state.liveness()
        history = await asyncio.to_thread(store.history, topics, a, b, max_points, svc.clock.now_ms(), liveness)
        return topics, _refine_kinds(svc, history)

    @router.get("/api/history")
    async def get_history(request: Request):
        return (await run_history(request))[1]

    @router.get("/api/history.csv")
    async def get_history_csv(request: Request):
        topics, history = await run_history(request)
        return Response(history_csv(history, topics), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="history.csv"'})

    @router.post("/api/command")
    async def post_command(request: Request):
        body = await _json_body(request)
        if (not isinstance(body, dict) or not isinstance(body.get("name"), str) or "value" not in body
                or not set(body) <= {"name", "value", "confirm"}):
            raise ApiError(422, "bad_type", 'the body must be {"name": str, "value": …, "confirm": bool}')
        confirm = body.get("confirm", False)
        if not isinstance(confirm, bool):
            raise ApiError(422, "bad_type", "confirm must be a boolean")
        status, payload = await commands.submit(body["name"], body["value"], confirm)
        return JSONResponse(payload, status_code=status)

    @router.get("/api/commands/{command_id}")
    async def get_command(command_id: str):
        record = store.get_command(command_id)
        if record is None:
            raise ApiError(404, "not_found", "unknown command id")
        return CommandService.to_api(record)

    @router.get("/api/commands")
    async def list_commands(request: Request):
        q = request.query_params
        limit = _param_int(q, "limit", 1, 1000, default=200)
        since = _param_int(q, "since", default=0) if q.get("since") else None
        records = store.list_commands(limit=1000)
        if since is not None:
            records = [r for r in records if (r.get("submitted_ts") or 0) >= since]
        return {"commands": [CommandService.to_api(r) for r in records[:limit]]}

    @router.get("/api/events")
    async def list_events(request: Request):
        q = request.query_params
        limit = _param_int(q, "limit", 1, 1000, default=200)
        since = _param_int(q, "since") if q.get("since") else None
        kinds = [k for k in (q.get("kind") or "").split(",") if k] or None
        events = store.events_list(from_ts=since, kinds=kinds, limit=100_000 if (since or kinds) else limit)
        return {"events": events[:limit]}

    @router.get("/api/prefs")
    async def get_prefs():
        return current_prefs(svc)

    @router.put("/api/prefs")
    async def put_prefs(request: Request):
        body = await _json_body(request)
        problem = validate_prefs(body)
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

    @router.get("/api/system")
    async def get_system():
        return system_info(svc)

    @router.get("/api/overlay")
    async def get_overlay(request: Request):
        q = request.query_params
        zone, mode = q.get("zone"), q.get("mode")
        if zone not in ("z1", "z2"):
            raise ApiError(422, "not_allowed_value", "zone must be z1 or z2", {"allowed": ["z1", "z2"]})
        if mode not in ("heat", "cool"):
            raise ApiError(422, "not_allowed_value", "mode must be heat or cool", {"allowed": ["heat", "cool"]})
        a, b = _range_params(q)
        if b - a > MAX_OVERLAY_MS:
            raise ApiError(422, "out_of_range", "the range must not exceed 400 days", {"max_days": 400})
        # a zone has its own water sensor when its Z*_Water_Temp topic carries a valid reading
        own = state.values.get(f"main/Z{zone[1]}_Water_Temp")
        liveness = state.liveness()
        return await asyncio.to_thread(
            curve.overlay, store, zone, mode, a, b, svc.clock.now_ms(), liveness,
            own_water_sensor=own is not None and own.valid)

    @router.post("/api/system/flush")
    async def post_flush(request: Request):
        await _json_body(request)
        flush_id = str(uuidlib.uuid4())
        if not svc.start_flush(flush_id):
            return _error(409, "flush_in_progress", "a flush is already running")
        return JSONResponse({"flush_id": flush_id}, status_code=202)

    @router.websocket("/api/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        # register for fan-out BEFORE the snapshot, with no await in between (§4.4 ordering)
        client = svc.hub.register()
        hello = {"type": "hello", "seq": state.seq, "state": state_snapshot(svc), "profile": svc.profile()}

        async def drain():
            try:
                while True:
                    await websocket.receive_text()  # the socket is read-only; just notice a close
            except (WebSocketDisconnect, RuntimeError):
                pass

        async def pump():
            await websocket.send_json(hello)
            while True:
                message = await client.queue.get()
                if message is None:
                    await websocket.close(code=1013)
                    return
                await websocket.send_json(message)

        tasks = [asyncio.create_task(drain()), asyncio.create_task(pump())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task.exception() and not isinstance(task.exception(), (WebSocketDisconnect, RuntimeError)):
                    raise task.exception()
        finally:
            svc.hub.unregister(client)
            for task in tasks:
                task.cancel()

    index = static_dir / "index.html"

    @router.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH"],
                      include_in_schema=False)
    async def spa(path: str, request: Request):
        if path == "api" or path.startswith("api/"):
            raise ApiError(404, "not_found", "unknown route")
        if request.method not in ("GET", "HEAD"):
            raise ApiError(404, "not_found", "unknown route")
        if path:
            root = static_dir.resolve()
            target = (root / path).resolve()
            if target.is_file() and target.is_relative_to(root):
                return FileResponse(target)
        if index.is_file():
            return FileResponse(index)
        return HTMLResponse("<!doctype html><title>HeishaMon dashboard</title>"
                            "<p>The frontend has not been built yet.</p>", status_code=404)

    app.include_router(router)
