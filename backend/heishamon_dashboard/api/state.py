"""GET /api/state, GET /api/profile and the WebSocket /api/ws."""
import asyncio

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect


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


def register(router: APIRouter, svc) -> None:
    state = svc.state

    @router.get("/api/state")
    async def get_state():
        return state_snapshot(svc)

    @router.get("/api/profile")
    async def get_profile():
        return svc.profile()

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
