"""REST and WebSocket routes (spec §4.4), one module per feature."""
from pathlib import Path

from fastapi import APIRouter, FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import commands, curve, energy, events, history, prefs, state, static, system
from .common import ApiError, error_response


def register(app: FastAPI, svc, static_dir: Path) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_request, exc: ApiError):
        return error_response(exc.status, exc.code, exc.message, exc.detail)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return error_response(exc.status_code, code, str(exc.detail))

    router = APIRouter()
    for feature in (state, history, commands, events, prefs, system, curve, energy):
        feature.register(router, svc)
    static.register(router, svc, static_dir)  # last: the catch-all must not shadow the routes above
    app.include_router(router)
