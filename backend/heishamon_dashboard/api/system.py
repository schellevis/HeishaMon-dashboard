"""GET /api/system and POST /api/system/flush."""
import asyncio
import uuid as uuidlib

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .common import error_response, json_body


def system_info(svc, overflow: int) -> dict:
    """`overflow` is the buffer-overflow event count, read by the caller off the event loop."""
    store = svc.store
    failing = store.failing
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


def register(router: APIRouter, svc) -> None:
    store = svc.store

    @router.get("/api/system")
    async def get_system():
        events = await asyncio.to_thread(store.events_list, kinds=["buffer_overflow"], limit=1000)
        return system_info(svc, sum(e["detail"].get("count", 0) for e in events))

    @router.post("/api/system/flush")
    async def post_flush(request: Request):
        await json_body(request)
        flush_id = str(uuidlib.uuid4())
        if not svc.start_flush(flush_id):
            return error_response(409, "flush_in_progress", "a flush is already running")
        return JSONResponse({"flush_id": flush_id}, status_code=202)
