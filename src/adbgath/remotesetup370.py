from __future__ import annotations

import asyncio
import inspect
import secrets
from typing import Any

from fastapi import Request

from .webapp370 import SETUP_HTML, _auth_page

_STARTUP_FIELD = "startup_token"
_STARTUP_LABEL = (
    "<label><span>Remote startup token</span>"
    "<input name='startup_token' type='password' minlength='24' maxlength='1024' "
    "autocomplete='current-password' required></label>"
)


def _with_startup_field(response: Any) -> Any:
    if getattr(response, "status_code", 500) != 200 or not hasattr(response, "body"):
        return response
    try:
        html = response.body.decode("utf-8")
    except Exception:
        return response
    if "Create the first administrator" not in html or f"name='{_STARTUP_FIELD}'" in html:
        return response
    marker = "<button class='primary' type='submit'>Initialize secure workspace</button>"
    html = html.replace(marker, _STARTUP_LABEL + marker, 1)
    response.body = html.encode("utf-8")
    response.headers["content-length"] = str(len(response.body))
    return response


def patch_webapp(module: Any) -> None:
    """Require the configured remote startup token before first-admin bootstrap."""
    if getattr(module, "_adbgath_370_remote_setup_patched", False):
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
        if auth is None or not getattr(app.state, "remote_token", None):
            return app

        for route in list(app.routes):
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", set()) or set()
            is_root = path == "/" and "GET" in methods
            is_setup = path == "/auth/setup" and "POST" in methods
            if not (is_root or is_setup):
                continue

            original_endpoint = getattr(route, "endpoint", None)
            if not callable(original_endpoint):
                continue

            if is_root:
                async def remote_setup_root(request: Request, _original=original_endpoint):
                    result = _original(request)
                    if inspect.isawaitable(result):
                        result = await result
                    if not auth.has_users():
                        result = _with_startup_field(result)
                    return result

                route.endpoint = remote_setup_root
                dependant = getattr(route, "dependant", None)
                if dependant is not None:
                    dependant.call = remote_setup_root

            elif is_setup:
                async def guarded_setup(request: Request, _original=original_endpoint):
                    if auth.has_users():
                        result = _original(request)
                        if inspect.isawaitable(result):
                            result = await result
                        return result

                    client = request.client.host if request.client else "unknown"
                    key = f"setup:{client}"
                    now = asyncio.get_running_loop().time()
                    attempts = [stamp for stamp in app.state.login_attempts.get(key, []) if now - stamp < 60]
                    if len(attempts) >= 5:
                        response = _auth_page(
                            SETUP_HTML,
                            error="Too many setup attempts. Try again in one minute.",
                            legacy=app.state.legacy_workspace_370,
                        )
                        response.status_code = 429
                        return _with_startup_field(response)

                    form = await request.form()
                    supplied = str(form.get(_STARTUP_FIELD, ""))
                    if not secrets.compare_digest(supplied, str(app.state.remote_token)):
                        attempts.append(now)
                        app.state.login_attempts[key] = attempts
                        response = _auth_page(
                            SETUP_HTML,
                            error="Invalid remote startup token.",
                            legacy=app.state.legacy_workspace_370,
                        )
                        response.status_code = 403
                        return _with_startup_field(response)

                    app.state.login_attempts.pop(key, None)
                    result = _original(request)
                    if inspect.isawaitable(result):
                        result = await result
                    if not auth.has_users():
                        result = _with_startup_field(result)
                    return result

                route.endpoint = guarded_setup
                dependant = getattr(route, "dependant", None)
                if dependant is not None:
                    dependant.call = guarded_setup

        return app

    module.create_app = create_app
    module._adbgath_370_remote_setup_patched = True
