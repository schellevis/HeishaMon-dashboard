"""The built SPA and the JSON 404 for unknown /api routes. Register last: it matches every path."""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse

from .common import ApiError


def register(router: APIRouter, svc, static_dir: Path) -> None:
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
