"""POST /api/command, GET /api/commands/{id} and GET /api/commands."""
import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .common import ApiError, json_body, param_int

COMMAND_NAME_MAX_BYTES = 64


def register(router: APIRouter, svc) -> None:
    store, commands = svc.store, svc.commands

    @router.post("/api/command")
    async def post_command(request: Request):
        body = await json_body(request)
        if (not isinstance(body, dict) or not isinstance(body.get("name"), str) or "value" not in body
                or not set(body) <= {"name", "value", "confirm"}):
            raise ApiError(422, "bad_type", 'the body must be {"name": str, "value": …, "confirm": bool}')
        if len(body["name"].encode("utf-8")) > COMMAND_NAME_MAX_BYTES:
            raise ApiError(422, "unknown_command", "unknown command or input")
        confirm = body.get("confirm", False)
        if not isinstance(confirm, bool):
            raise ApiError(422, "bad_type", "confirm must be a boolean")
        status, payload = await commands.submit(body["name"], body["value"], confirm)
        return JSONResponse(payload, status_code=status)

    @router.get("/api/commands/{command_id}")
    async def get_command(command_id: str):
        record = await asyncio.to_thread(store.get_command, command_id)
        if record is None:
            raise ApiError(404, "not_found", "unknown command id")
        return commands.to_api(record)

    @router.get("/api/commands")
    async def list_commands(request: Request):
        q = request.query_params
        limit = param_int(q, "limit", 1, 1000, default=200)
        since = param_int(q, "since", default=0) if q.get("since") else None
        records = await asyncio.to_thread(store.list_commands, limit=1000)
        if since is not None:
            records = [r for r in records if (r.get("submitted_ts") or 0) >= since]
        return {"commands": [commands.to_api(r) for r in records[:limit]]}
