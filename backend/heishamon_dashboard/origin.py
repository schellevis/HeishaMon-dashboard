"""Browser-origin, Host and CSRF policy (spec §13), as a pure ASGI middleware.

It runs before routing, so every rule is enforced before any request processing, and the same
rules apply at the WebSocket handshake.
"""
import ipaddress
import json
from urllib.parse import urlsplit

MUTATION_PATHS = frozenset({"/api/command", "/api/prefs", "/api/system/flush"})
MUTATION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_PREFLIGHT_METHODS = "GET, POST, PUT, OPTIONS"


def _hostport(origin: str) -> str:
    return urlsplit(origin).netloc.lower()


def _bare_host(host: str | None) -> str:
    """The raw Host header without a trailing `:port` (`[::1]:8000` -> `::1`), lower-cased."""
    text = (host or "").strip().lower()
    if text.startswith("["):
        end = text.find("]")
        return text[1:end] if end > 0 else text
    if text.count(":") == 1:
        return text.split(":", 1)[0]
    return text  # a bare IPv6 literal has several colons and no port


def literal_or_localhost(host: str | None) -> bool:
    """True for `localhost` and any IPv4/IPv6 literal (the Host policy without PUBLIC_ORIGINS)."""
    name = _bare_host(host)
    if name == "localhost":
        return True
    try:
        ipaddress.ip_address(name)
    except ValueError:
        return False
    return True


def _norm(origin: str) -> str:
    parts = urlsplit(origin)
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


class OriginPolicy:
    def __init__(self, public_origins=(), allowed_origins=()):
        self.public = tuple(_norm(o) for o in public_origins)
        self.allowed = tuple(_norm(o) for o in allowed_origins)
        self._public_hosts = {_hostport(o) for o in self.public}

    def host_ok(self, host: str | None) -> bool:
        """Host check: only active when PUBLIC_ORIGINS is set (DNS-rebinding protection)."""
        if not self.public:
            return True
        return (host or "").lower() in self._public_hosts

    def write_host_ok(self, host: str | None) -> bool:
        """Without PUBLIC_ORIGINS, writes and WebSockets need a localhost or IP-literal Host."""
        return bool(self.public) or literal_or_localhost(host)

    def trusted(self, origin: str, host: str | None) -> bool:
        """`origin` is a present, non-"null" Origin header value."""
        norm = _norm(origin)
        if norm in self.allowed:
            return True
        if self.public:
            return norm in self.public
        # derived same origin: host[:port] equals the Host header; the scheme is ignored
        return bool(host) and urlsplit(origin).netloc.lower() == host.lower()

    def cors_origin(self, origin: str | None) -> str | None:
        """The exact origin to echo in Access-Control-Allow-Origin, or None."""
        if origin and origin != "null" and _norm(origin) in self.allowed:
            return origin
        return None


def _json_body(code: str, message: str) -> bytes:
    return json.dumps({"error": code, "message": message, "detail": None}).encode()


class OriginMiddleware:
    def __init__(self, app, policy: OriginPolicy):
        self.app = app
        self.policy = policy

    async def __call__(self, scope, receive, send):
        kind = scope["type"]
        if kind not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        host, origin = headers.get("host"), headers.get("origin")
        policy = self.policy

        if not policy.host_ok(host):
            await self._reject(scope, send, 403, "bad_host", "this Host is not served here")
            return

        cors = policy.cors_origin(origin)
        method = scope.get("method", "GET")
        path = scope["path"]

        if (kind == "websocket" or method in MUTATION_METHODS) and not policy.write_host_ok(host):
            await self._reject(scope, send, 403, "bad_host",
                               "this Host is not accepted for writes; set PUBLIC_ORIGINS to serve a DNS name", cors)
            return

        if kind == "websocket":
            if origin is not None and (origin == "null" or not policy.trusted(origin, host)):
                await self._reject(scope, send, 403, "bad_origin", "origin not allowed")
                return
            await self.app(scope, receive, send)
            return

        if method == "OPTIONS" and "access-control-request-method" in headers:
            extra = []
            if cors is not None:
                extra = [
                    (b"access-control-allow-origin", cors.encode()),
                    (b"access-control-allow-methods", _PREFLIGHT_METHODS.encode()),
                    (b"access-control-allow-headers", b"content-type"),
                    (b"access-control-max-age", b"600"),
                    (b"vary", b"Origin"),
                ]
            await send({"type": "http.response.start", "status": 204, "headers": extra})
            await send({"type": "http.response.body", "body": b""})
            return

        if method in MUTATION_METHODS and path in MUTATION_PATHS:
            if origin is not None and (origin == "null" or not policy.trusted(origin, host)):
                await self._reject(scope, send, 403, "bad_origin", "origin not allowed", cors)
                return
            ctype = headers.get("content-type", "").split(";")[0].strip().lower()
            if ctype != "application/json":
                await self._reject(scope, send, 415, "bad_type", "the body must be application/json", cors)
                return

        if cors is None:
            await self.app(scope, receive, send)
            return

        async def send_cors(message):
            if message["type"] == "http.response.start":
                message = dict(message)
                message["headers"] = list(message.get("headers", [])) + [
                    (b"access-control-allow-origin", cors.encode()),
                    (b"vary", b"Origin"),
                ]
            await send(message)

        await self.app(scope, receive, send_cors)

    async def _reject(self, scope, send, status, code, message, cors=None):
        if scope["type"] == "websocket":
            if "websocket.http.response" not in scope.get("extensions", {}):
                # without the denial extension, closing before accept still yields an HTTP 403
                await send({"type": "websocket.close", "code": 1008, "reason": code})
                return
        body = _json_body(code, message)
        headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
        if cors is not None:
            headers += [(b"access-control-allow-origin", cors.encode()), (b"vary", b"Origin")]
        kind = "websocket.http.response" if scope["type"] == "websocket" else "http.response"
        await send({"type": f"{kind}.start", "status": status, "headers": headers})
        await send({"type": f"{kind}.body", "body": body})
