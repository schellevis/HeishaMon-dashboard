"""GET /api/overlay: the heating-curve overlay."""
import asyncio

from fastapi import APIRouter, Request

from heishamon_dashboard import curve, derived

from .common import ApiError, range_params

MAX_OVERLAY_MS = 400 * 86_400_000


def register(router: APIRouter, svc) -> None:
    store, state = svc.store, svc.state

    @router.get("/api/overlay")
    async def get_overlay(request: Request):
        q = request.query_params
        zone, mode = q.get("zone"), q.get("mode")
        if zone not in ("z1", "z2"):
            raise ApiError(422, "not_allowed_value", "zone must be z1 or z2", {"allowed": ["z1", "z2"]})
        if mode not in ("heat", "cool"):
            raise ApiError(422, "not_allowed_value", "mode must be heat or cool", {"allowed": ["heat", "cool"]})
        a, b = range_params(q)
        if b - a > MAX_OVERLAY_MS:
            raise ApiError(422, "out_of_range", "the range must not exceed 400 days", {"max_days": 400})
        # a zone has its own water sensor when its Z*_Water_Temp topic carries a valid reading
        own = state.values.get(f"main/Z{zone[1]}_Water_Temp")
        liveness = state.liveness()
        return await asyncio.to_thread(
            curve.overlay, store, zone, mode, a, b, svc.clock.now_ms(), liveness,
            own_water_sensor=own is not None and own.valid, has_extra=derived.has_extra(svc.profile()))
