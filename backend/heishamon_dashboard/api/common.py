"""Shared API plumbing: errors, query-parameter parsing and the request-body guard."""
import json
import re

from fastapi import Request
from fastapi.responses import JSONResponse

from heishamon_dashboard.commands import error_body

BODY_MAX_BYTES = 64 * 1024
_INT = re.compile(r"^-?\d+$")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, detail: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.detail = status, code, message, detail


def error_response(status: int, code: str, message: str, detail: dict | None = None) -> JSONResponse:
    return JSONResponse(error_body(code, message, detail), status_code=status)


def param_int(q, name: str, lo: int | None = None, hi: int | None = None, default: int | None = None) -> int:
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


def range_params(q) -> tuple[int, int]:
    a, b = param_int(q, "from"), param_int(q, "to")
    if a >= b:
        raise ApiError(422, "out_of_range", "'from' must be before 'to'")
    return a, b


def _reject_constant(name):
    raise ValueError(name)


async def json_body(request: Request):
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > BODY_MAX_BYTES:
        raise ApiError(413, "body_too_large", f"the body must not exceed {BODY_MAX_BYTES} bytes")
    raw = b""
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > BODY_MAX_BYTES:
            raise ApiError(413, "body_too_large", f"the body must not exceed {BODY_MAX_BYTES} bytes")
    try:
        return json.loads(raw, parse_constant=_reject_constant)
    except ValueError:
        raise ApiError(400, "bad_request", "malformed JSON") from None
