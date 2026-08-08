from __future__ import annotations

import inspect
from typing import Any


UX_DIALOGS = r'''
<dialog id="ux371PresetDialog" class="ux371-dialog" aria-labelledby="ux371PresetTitle">
  <form id="ux371PresetForm" method="dialog">
    <div class="panel-head">
      <div><span class="tag">COMMAND PRESET</span><h3 id="ux371PresetTitle">Save operation preset</h3></div>
      <button type="button" class="text-button" data-ux371-close>CLOSE</button>
    </div>
    <p>Save the current Command Center fields for quick reuse. Sensitive fields are deliberately excluded.</p>
    <label><span>PRESET NAME</span><input id="ux371PresetName" maxlength="80" autocomplete="off" required></label>
    <div class="ux371-scope-card">Scope: <strong id="ux371PresetScopeLabel">current user / workspace</strong></div>
    <div id="ux371PresetSaveStatus" class="ux371-dialog-note">Only declared non-secret operation fields are stored in the authenticated workspace.</div>
    <div class="execute-row">
      <button type="button" class="secondary" data-ux371-close>Cancel</button>
      <button id="ux371PresetSaveConfirm" type="submit" class="primary">Save preset</button>
    </div>
  </form>
</dialog>

<dialog id="ux371ConfirmDialog" class="ux371-dialog" aria-labelledby="ux371ConfirmTitle">
  <form id="ux371ConfirmForm" method="dialog">
    <div class="panel-head">
      <div><span class="tag">CONFIRM ACTION</span><h3 id="ux371ConfirmTitle">Confirm action</h3></div>
      <button type="button" class="text-button" data-ux371-close>CLOSE</button>
    </div>
    <p id="ux371ConfirmMessage">Review this action before continuing.</p>
    <div class="ux371-dialog-note warning">ADB-Gath keeps confirmations inside the application UI so the context and impact remain visible.</div>
    <div class="execute-row">
      <button type="button" class="secondary" data-ux371-close>Cancel</button>
      <button id="ux371ConfirmAction" type="submit" class="primary" data-confirm-tone="danger">Confirm</button>
    </div>
  </form>
</dialog>
'''


def _upgrade_html(response: Any) -> Any:
    if not hasattr(response, "body"):
        return response
    content_type = str(getattr(response, "headers", {}).get("content-type", ""))
    if "text/html" not in content_type:
        return response
    try:
        html = response.body.decode("utf-8")
    except Exception:
        return response

    html = html.replace("3.7.0", "3.7.1")
    if 'id="presetSelect"' in html:
        if "/static/ux371.css" not in html:
            html = html.replace("</head>", '  <link rel="stylesheet" href="/static/ux371.css">\n</head>', 1)
        if 'id="ux371PresetDialog"' not in html:
            marker = '<div id="toast" class="toast"></div>'
            if marker in html:
                html = html.replace(marker, UX_DIALOGS + "\n  " + marker, 1)
            else:
                html = html.replace("</body>", UX_DIALOGS + "\n</body>", 1)
        if "/static/ux371.js" not in html:
            html = html.replace("</body>", '  <script src="/static/ux371.js" defer></script>\n</body>', 1)
        if "/static/presets371.js" not in html:
            html = html.replace("</body>", '  <script src="/static/presets371.js" defer></script>\n</body>', 1)
    response.body = html.encode("utf-8")
    response.headers["content-length"] = str(len(response.body))
    return response


def patch_webapp(module: Any) -> None:
    if getattr(module, "_adbgath_371_web_ux_patched", False):
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
            if path not in {"/", "/auth/setup", "/auth/login"} or not ({"GET", "POST"} & methods):
                continue
            original_endpoint = route.endpoint

            async def upgraded_page(*args, _original=original_endpoint, **kwargs):
                result = _original(*args, **kwargs)
                if inspect.isawaitable(result):
                    result = await result
                return _upgrade_html(result)

            route.endpoint = upgraded_page
            if hasattr(route, "dependant"):
                route.dependant.call = upgraded_page
        return app

    module.create_app = create_app
    module._adbgath_371_web_ux_patched = True
