from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse


def _same_origin(request: Request, value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if not parsed.scheme or not parsed.netloc:
        return False
    expected_scheme = "https" if getattr(request.app.state, "secure_cookie", False) else "http"
    return parsed.scheme.lower() == expected_scheme and parsed.netloc.lower() == request.headers.get("host", "").lower()


def patch_webapp(module: Any) -> None:
    if getattr(module, "_adbgath_370_auth_origin_patched", False):
        return
    original_create_app = module.create_app

    def create_app(*, workspace=None, service=None, remote_token=None, secure_cookie=False):
        app = original_create_app(
            workspace=workspace,
            service=service,
            remote_token=remote_token,
            secure_cookie=secure_cookie,
        )

        @app.middleware("http")
        async def auth_form_origin_370(request: Request, call_next):
            if request.method.upper() == "POST" and request.url.path in {"/auth/setup", "/auth/login"}:
                origin = request.headers.get("origin")
                referer = request.headers.get("referer")
                if origin and not _same_origin(request, origin):
                    return JSONResponse(status_code=403, content={"ok": False, "error": "Cross-origin authentication request rejected."})
                if not origin and referer and not _same_origin(request, referer):
                    return JSONResponse(status_code=403, content={"ok": False, "error": "Cross-origin authentication request rejected."})
            return await call_next(request)

        return app

    module.create_app = create_app
    module._adbgath_370_auth_origin_patched = True
