from __future__ import annotations

import inspect
from functools import wraps
from typing import Any, Callable

from fastapi import WebSocketDisconnect


def guard_websocket_endpoint(endpoint: Callable[..., Any], *, logger=None, path: str = "websocket"):
    """Prevent expected client disconnects from surfacing as ASGI application errors."""

    @wraps(endpoint)
    async def guarded(*args, **kwargs):
        try:
            result = endpoint(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            return result
        except WebSocketDisconnect as exc:
            if logger is not None:
                logger.debug("WebSocket client disconnected from %s (code=%s)", path, getattr(exc, "code", None))
            return None

    return guarded


def patch_webapp(module: Any) -> None:
    """Guard every first-party WebSocket route against expected disconnect noise."""
    if getattr(module, "_adbgath_websocket_cleanup_360_patched", False):
        return

    original_create_app = module.create_app

    def create_app(*, workspace=None, service=None, remote_token=None, secure_cookie=False):
        app = original_create_app(
            workspace=workspace,
            service=service,
            remote_token=remote_token,
            secure_cookie=secure_cookie,
        )

        logger = getattr(module, "LOGGER", None)
        for route in list(app.routes):
            path = str(getattr(route, "path", "") or "")
            if not path.startswith("/ws/"):
                continue
            original_endpoint = getattr(route, "endpoint", None)
            if not callable(original_endpoint):
                continue
            guarded = guard_websocket_endpoint(original_endpoint, logger=logger, path=path)
            route.endpoint = guarded
            dependant = getattr(route, "dependant", None)
            if dependant is not None:
                dependant.call = guarded

        return app

    module.create_app = create_app
    module._adbgath_websocket_cleanup_360_patched = True
