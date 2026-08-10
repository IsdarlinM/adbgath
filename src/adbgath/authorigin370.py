from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse


def _normalize_host(hostname: str) -> str:
    value = hostname.strip().rstrip(".").lower()
    if not value:
        return ""
    try:
        return ipaddress.ip_address(value).compressed.lower()
    except ValueError:
        try:
            return value.encode("idna").decode("ascii").lower()
        except UnicodeError:
            return ""


def _origin(value: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"} or parsed.username is not None or parsed.password is not None:
            return None
        hostname = parsed.hostname
        port = parsed.port
    except (TypeError, ValueError):
        return None
    if not hostname:
        return None
    host = _normalize_host(hostname)
    if not host:
        return None
    if port is None:
        port = 443 if scheme == "https" else 80
    return scheme, host, port


def _same_origin(request: Request, value: str) -> bool:
    supplied = _origin(value)
    expected = _origin(str(request.url))
    return supplied is not None and expected is not None and supplied == expected


def _fetch_site_decision(request: Request) -> bool | None:
    """Use browser Fetch Metadata when available without weakening non-browser fallback checks."""
    site = request.headers.get("sec-fetch-site", "").strip().lower()
    if site == "same-origin":
        return True
    if site == "cross-site":
        return False
    return None


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
                fetch_site = _fetch_site_decision(request)
                if fetch_site is False:
                    return JSONResponse(
                        status_code=403,
                        content={"ok": False, "error": "Cross-origin authentication request rejected."},
                    )

                # A browser-provided same-origin Fetch Metadata signal is stronger
                # than string-comparing Host/Origin representations and avoids false
                # positives for equivalent IPv6/default-port/hostname forms.
                if fetch_site is not True:
                    origin = request.headers.get("origin")
                    referer = request.headers.get("referer")
                    if origin and not _same_origin(request, origin):
                        return JSONResponse(
                            status_code=403,
                            content={"ok": False, "error": "Cross-origin authentication request rejected."},
                        )
                    if not origin and referer and not _same_origin(request, referer):
                        return JSONResponse(
                            status_code=403,
                            content={"ok": False, "error": "Cross-origin authentication request rejected."},
                        )
            return await call_next(request)

        return app

    module.create_app = create_app
    module._adbgath_370_auth_origin_patched = True
