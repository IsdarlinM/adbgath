from __future__ import annotations

import inspect
from typing import Any


def _upgrade(response: Any) -> Any:
    if not hasattr(response, "body"):
        return response
    content_type = str(getattr(response, "headers", {}).get("content-type", ""))
    if "text/html" not in content_type:
        return response
    try:
        html = response.body.decode("utf-8")
    except Exception:
        return response
    if 'id="presetSelect"' not in html:
        return response
    if "/static/ux372.css" not in html:
        html = html.replace("</head>", '  <link rel="stylesheet" href="/static/ux372.css">\n</head>', 1)
    if "/static/ux372.js" not in html:
        html = html.replace("</body>", '  <script src="/static/ux372.js" defer></script>\n</body>', 1)
    response.body = html.encode("utf-8")
    response.headers["content-length"] = str(len(response.body))
    return response


def patch_webapp(module: Any) -> None:
    if getattr(module, "_adbgath_372_final_web_patched", False):
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
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", set()) or set()
            if path != "/" or "GET" not in methods:
                continue
            original_endpoint = route.endpoint

            async def upgraded_dashboard(*args, _original=original_endpoint, **kwargs):
                result = _original(*args, **kwargs)
                if inspect.isawaitable(result):
                    result = await result
                return _upgrade(result)

            route.endpoint = upgraded_dashboard
            if hasattr(route, "dependant"):
                route.dependant.call = upgraded_dashboard
            break
        return app

    module.create_app = create_app
    module._adbgath_372_final_web_patched = True
