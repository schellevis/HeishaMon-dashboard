"""GET /api/history and /api/history.csv."""
import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import Response

from .common import ApiError, param_int, range_params

MAX_TOPICS = 20
_CSV_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def _csv_field(text: str, force: bool = False) -> str:
    if text.startswith(_CSV_DANGEROUS):
        text = "'" + text  # spreadsheet formula injection guard
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
    a, b = range_params(q)
    return topics, a, b, param_int(q, "max_points", 10, 10000, default=1000)


def register(router: APIRouter, svc) -> None:
    store, state = svc.store, svc.state

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
