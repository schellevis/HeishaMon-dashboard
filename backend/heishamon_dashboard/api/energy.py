"""GET /api/energy (F2)."""
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request

from heishamon_dashboard import derived

from .common import ApiError


def energy_range(period: str, now_ms: int, tz) -> tuple[int, int]:
    """Calendar-aligned (from, to) in ms for the Energy screen, evaluated in `tz` (F2):
    day = the 14 local days ending today, month = the 12 local months ending this month,
    year = from 1 January four years ago."""
    today = datetime.fromtimestamp(now_ms / 1000, tz)
    if period == "day":
        start = datetime(today.year, today.month, today.day, tzinfo=tz) - timedelta(days=13)
        # timedelta on an aware datetime keeps the wall clock, so DST days stay midnight-aligned
    elif period == "month":
        months = today.year * 12 + today.month - 1 - 11
        start = datetime(months // 12, months % 12 + 1, 1, tzinfo=tz)
    elif period == "year":
        start = datetime(today.year - 4, 1, 1, tzinfo=tz)
    else:
        raise ValueError(period)
    return int(start.timestamp() * 1000), now_ms


def register(router: APIRouter, svc) -> None:
    store, state = svc.store, svc.state

    @router.get("/api/energy")
    async def get_energy(request: Request):
        period = request.query_params.get("period")
        if period not in derived.PERIODS:
            raise ApiError(422, "bad_param", "period must be day, month or year",
                           {"allowed": list(derived.PERIODS)})
        tz = ZoneInfo(svc.config.tz)
        now = svc.clock.now_ms()
        a, b = energy_range(period, now, tz)
        result = await asyncio.to_thread(
            derived.energy, store, a, b, period, now, svc.profile(), state.liveness(), tz)
        return {"tz": svc.config.tz, "period": period, "from": a, "to": b, **result}
