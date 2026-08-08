from __future__ import annotations

import asyncio
import inspect
from typing import Any

from fastapi import Request

from .webapp370 import AUTH_COOKIE, LEGACY_COOKIE, SESSION_SECONDS


def _replace_legacy_cookie(response: Any, *, app: Any) -> Any:
    if not hasattr(response, "raw_headers"):
        return response
    response.raw_headers = [
        (name, value)
        for name, value in response.raw_headers
        if not (
            name.lower() == b"set-cookie"
            and value.lower().startswith((LEGACY_COOKIE + "=").encode("ascii"))
        )
    ]
    response.set_cookie(
        LEGACY_COOKIE,
        app.state.session_token,
        httponly=True,
        secure=app.state.secure_cookie,
        samesite="strict",
        max_age=SESSION_SECONDS,
        path="/",
    )
    return response


def patch_webapp(module: Any) -> None:
    """Keep the 3.6 remote-token root guard compatible with authenticated 3.7 sessions."""
    if getattr(module, "_adbgath_370_remote_root_patched", False):
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
        root_lock = asyncio.Lock()

        for route in list(app.routes):
            if getattr(route, "path", None) != "/" or "GET" not in (getattr(route, "methods", set()) or set()):
                continue
            original_root = route.endpoint

            async def root_compat(request: Request, _original=original_root):
                async with root_lock:
                    session = auth.resolve_session(request.cookies.get(AUTH_COOKIE), touch=False)
                    if session is None:
                        result = _original(request)
                        if inspect.isawaitable(result):
                            result = await result
                        return result

                    previous_remote_token = app.state.remote_token
                    try:
                        # The 3.7 user session is already authenticated. Disable only
                        # the superseded 3.6 root-token page while rendering this one
                        # serialized request, then restore the configured startup guard.
                        app.state.remote_token = None
                        result = _original(request)
                        if inspect.isawaitable(result):
                            result = await result
                    finally:
                        app.state.remote_token = previous_remote_token
                    return _replace_legacy_cookie(result, app=app)

            route.endpoint = root_compat
            if hasattr(route, "dependant"):
                route.dependant.call = root_compat
            break
        return app

    module.create_app = create_app
    module._adbgath_370_remote_root_patched = True
