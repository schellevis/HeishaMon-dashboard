"""Shared test client whose requests carry `Host: localhost` (the Host policy of spec §13)."""
from fastapi.testclient import TestClient


class LocalClient(TestClient):
    """HTTP and WebSocket requests carry `Host: localhost`; Starlette hard-codes `testserver` for WebSockets."""

    def __init__(self, app, **kw):
        super().__init__(app, base_url="http://localhost", **kw)

    def websocket_connect(self, url, *args, **kwargs):
        if url.startswith("/"):
            url = "ws://localhost" + url
        return super().websocket_connect(url, *args, **kwargs)
