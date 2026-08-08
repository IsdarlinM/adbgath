from __future__ import annotations

import asyncio

import pytest
from fastapi import WebSocketDisconnect

from adbgath.webapp import create_app
from adbgath.websocketcleanup360 import guard_websocket_endpoint


def test_guard_treats_client_disconnect_as_normal_lifecycle():
    async def endpoint():
        raise WebSocketDisconnect(code=1006)

    guarded = guard_websocket_endpoint(endpoint, path="/ws/test")
    assert asyncio.run(guarded()) is None


def test_guard_does_not_hide_real_application_errors():
    async def endpoint():
        raise ValueError("real bug")

    guarded = guard_websocket_endpoint(endpoint, path="/ws/test")
    with pytest.raises(ValueError, match="real bug"):
        asyncio.run(guarded())


def test_every_first_party_websocket_route_uses_the_final_guard(tmp_path):
    app = create_app(workspace=tmp_path)
    websocket_routes = [route for route in app.routes if str(getattr(route, "path", "")).startswith("/ws/")]

    paths = {route.path for route in websocket_routes}
    assert "/ws/logs" in paths
    assert "/ws/wireless" in paths
    assert "/ws/wireless/qr/{session_id}" in paths

    for route in websocket_routes:
        assert route.endpoint is route.dependant.call
        assert hasattr(route.endpoint, "__wrapped__")
