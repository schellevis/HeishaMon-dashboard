"""GET /api/events."""
import asyncio

from fastapi import APIRouter, Request

from .common import param_int


def register(router: APIRouter, svc) -> None:
    store = svc.store

    @router.get("/api/events")
    async def list_events(request: Request):
        q = request.query_params
        limit = param_int(q, "limit", 1, 1000, default=200)
        since = param_int(q, "since") if q.get("since") else None
        kinds = [k for k in (q.get("kind") or "").split(",") if k] or None
        events = await asyncio.to_thread(
            store.events_list, from_ts=since, kinds=kinds, limit=100_000 if (since or kinds) else limit)
        return {"events": events[:limit]}
