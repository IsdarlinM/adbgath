from __future__ import annotations

import asyncio
import contextlib
import inspect
import time
from functools import wraps
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from .webapp370 import AUTH_COOKIE


def patch_webapp(module: Any) -> None:
    """Enforce authenticated session expiry for long-lived first-party WebSockets."""
    if getattr(module, "_adbgath_370_websocket_expiry_patched", False):
        return
    original_create_app = module.create_app

    def create_app(*, workspace=None, service=None, remote_token=None, secure_cookie=False):
        app = original_create_app(
            workspace=workspace,
            service=service,
            remote_token=remote_token,
            secure_cookie=secure_cookie,
        )
        auth = getattr(app.state, "auth_store", None)
        if auth is None:
            return app

        for route in list(app.routes):
            path = str(getattr(route, "path", "") or "")
            if not path.startswith("/ws/"):
                continue
            endpoint = route.endpoint

            @wraps(endpoint)
            async def expiring_endpoint(*args, _endpoint=endpoint, **kwargs):
                websocket = next((arg for arg in args if isinstance(arg, WebSocket)), kwargs.get("websocket"))
                if websocket is None:
                    raise RuntimeError("WebSocket route did not receive a WebSocket object.")
                session = auth.resolve_session(websocket.cookies.get(AUTH_COOKIE), touch=False)
                if session is None:
                    with contextlib.suppress(Exception):
                        await websocket.close(code=4401)
                    return None
                remaining = max(0.0, float(session.expires_at) - time.time())
                if remaining <= 0:
                    with contextlib.suppress(Exception):
                        await websocket.close(code=4401)
                    return None
                try:
                    result = _endpoint(*args, **kwargs)
                    if inspect.isawaitable(result):
                        return await asyncio.wait_for(result, timeout=remaining)
                    return result
                except asyncio.TimeoutError:
                    with contextlib.suppress(Exception):
                        await websocket.close(code=4401)
                    return None
                except WebSocketDisconnect:
                    return None

            route.endpoint = expiring_endpoint
            if hasattr(route, "dependant"):
                route.dependant.call = expiring_endpoint

        return app

    module.create_app = create_app
    module._adbgath_370_websocket_expiry_patched = True
