from __future__ import annotations

import inspect
from typing import Any

_THEME_LINK = '<link rel="stylesheet" href="/static/theme360.css">'


def _inject_theme(response: Any):
    if getattr(response, "status_code", 500) != 200 or not hasattr(response, "body"):
        return response
    content_type = str(getattr(response, "media_type", "") or response.headers.get("content-type", ""))
    if "html" not in content_type.lower():
        return response
    try:
        html = response.body.decode("utf-8")
    except Exception:
        return response
    if "/static/theme360.css" not in html:
        html = html.replace("</head>", f"  {_THEME_LINK}\n</head>", 1)
        response.body = html.encode("utf-8")
        response.headers["content-length"] = str(len(response.body))
    return response


def patch_webapp(module: Any) -> None:
    """Load the same visual theme on every first-party HTML workspace."""
    if getattr(module, "_adbgath_unified_web_theme_360_patched", False):
        return

    original_create_app = module.create_app

    def create_app(*, workspace=None, service=None, remote_token=None, secure_cookie=False):
        app = original_create_app(
            workspace=workspace,
            service=service,
            remote_token=remote_token,
            secure_cookie=secure_cookie,
        )

        for route in list(app.routes):
            if getattr(route, "path", None) not in {"/", "/wireless", "/lab"}:
                continue
            if "GET" not in (getattr(route, "methods", set()) or set()):
                continue
            original_endpoint = route.endpoint

            async def themed_endpoint(*args, _original=original_endpoint, **kwargs):
                result = _original(*args, **kwargs)
                if inspect.isawaitable(result):
                    result = await result
                return _inject_theme(result)

            route.endpoint = themed_endpoint
            if hasattr(route, "dependant"):
                route.dependant.call = themed_endpoint

        return app

    module.create_app = create_app
    module._adbgath_unified_web_theme_360_patched = True
