from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _message(exc: RequestValidationError) -> str:
    parts: list[str] = []
    for item in exc.errors():
        location = [str(value) for value in item.get("loc", ()) if value not in {"body"}]
        field = ".".join(location)
        message = str(item.get("msg") or item.get("type") or "Invalid request")
        parts.append(f"{field}: {message}" if field else message)
    return "; ".join(parts) or "Request validation failed."


def patch_webapp(module: Any) -> None:
    """Return stable non-secret text for framework-level HTTP 422 validation errors."""
    if getattr(module, "_adbgath_370_validation_errors_patched", False):
        return
    original_create_app = module.create_app

    def create_app(*, workspace=None, service=None, remote_token=None, secure_cookie=False):
        app = original_create_app(
            workspace=workspace,
            service=service,
            remote_token=remote_token,
            secure_cookie=secure_cookie,
        )

        @app.exception_handler(RequestValidationError)
        async def request_validation_error(_: Request, exc: RequestValidationError):
            return JSONResponse(status_code=422, content={"ok": False, "error": _message(exc)})

        return app

    module.create_app = create_app
    module._adbgath_370_validation_errors_patched = True
