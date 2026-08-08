from __future__ import annotations

from typing import Any


NAV_ITEM = """<button class=\"nav-item\" data-view=\"wireless-main\"><span>⌁</span>Wireless</button>"""

WIRELESS_VIEW = r"""
<section id="view-wireless-main" class="view">
  <div class="wireless-main-header">
    <div>
      <span class="tag">WIRELESS DEBUGGING</span>
      <h2>Pair and connect authorized Android devices</h2>
      <p>Use QR pairing without typing a code, or the six-digit pairing-code workflow. Pairing and connection endpoints normally use different ports.</p>
    </div>
    <a class="secondary wireless-advanced-link" href="/wireless">Advanced wireless workspace</a>
  </div>

  <div class="wireless-main-grid">
    <article class="panel wireless-main-card">
      <div class="panel-head"><div><span class="tag">PAIR WITHOUT CODE</span><h3>QR pairing</h3></div><span id="dashQrBadge" class="wireless-badge">IDLE</span></div>
      <p class="muted">On Android open Developer options → Wireless debugging → Pair device with QR code, then scan this one-time QR.</p>
      <div class="wireless-qr-layout">
        <div class="wireless-qr-box"><img id="dashQrImage" alt="ADB Wireless Debugging pairing QR" hidden><span id="dashQrPlaceholder">Create a one-time QR session</span></div>
        <div class="wireless-control-stack">
          <label><span>Session lifetime</span><select id="dashQrTtl"><option value="60">60 seconds</option><option value="120" selected>120 seconds</option><option value="180">180 seconds</option></select></label>
          <label class="wireless-check"><input id="dashQrAutoConnect" type="checkbox" checked> Connect automatically after pairing</label>
          <label class="wireless-check"><input id="dashQrAuthorized" type="checkbox"> Authorized device / in scope</label>
          <div class="wireless-button-row"><button id="dashQrCreate" class="primary">Create QR</button><button id="dashQrCancel" class="secondary" disabled>Cancel</button></div>
          <small id="dashQrStatus">No active QR session.</small>
        </div>
      </div>
    </article>

    <article class="panel wireless-main-card">
      <div class="panel-head"><div><span class="tag">PAIR WITH CODE</span><h3>Six-digit code</h3></div><span class="wireless-badge">ANDROID 11+</span></div>
      <p class="muted">Use the temporary HOST:PORT shown by Android under “Pair device with pairing code”. The code is sent only to ADB and is not stored.</p>
      <div class="wireless-form-stack">
        <label><span>Pairing endpoint</span><input id="dashPairTarget" placeholder="192.168.1.50:37123" autocomplete="off" spellcheck="false"></label>
        <label><span>Six-digit code</span><input id="dashPairCode" type="password" inputmode="numeric" maxlength="6" pattern="[0-9]{6}" placeholder="000000" autocomplete="one-time-code"></label>
        <label class="wireless-check"><input id="dashPairAuthorized" type="checkbox"> Authorized device / in scope</label>
        <button id="dashPairSubmit" class="primary">Pair device</button>
      </div>
    </article>

    <article class="panel wireless-main-card">
      <div class="panel-head"><div><span class="tag">DISCOVERY</span><h3>Nearby ADB services</h3></div><button id="dashDiscover" class="secondary">Discover</button></div>
      <p class="muted">ADB-Gath separates pairing services from post-pairing connection services so the temporary pairing port is not reused incorrectly.</p>
      <div class="wireless-service-columns">
        <div><strong>PAIRING</strong><div id="dashPairingServices" class="wireless-service-list empty-state">No pairing services discovered.</div></div>
        <div><strong>CONNECTION</strong><div id="dashConnectServices" class="wireless-service-list empty-state">No connection services discovered.</div></div>
      </div>
    </article>

    <article class="panel wireless-main-card">
      <div class="panel-head"><div><span class="tag">CONNECTION</span><h3>Connect after pairing</h3></div><span id="dashWirelessState" class="wireless-badge">READY</span></div>
      <div class="wireless-form-stack">
        <label><span>Connection endpoint</span><input id="dashConnectTarget" placeholder="192.168.1.50:41267" autocomplete="off" spellcheck="false"></label>
        <div class="wireless-button-row"><button id="dashConnect" class="primary">Connect</button><button id="dashAutoConnect" class="secondary">Auto-connect known</button></div>
      </div>
      <pre id="dashWirelessOutput" class="console wireless-main-console">Ready.</pre>
    </article>
  </div>
</section>
"""


def patch_webapp(module: Any) -> None:
    """Inject a first-class Wireless view into the main dashboard.

    The actual QR and pairing operations continue to use the existing 3.4/3.6
    API endpoints. This module only exposes those capabilities in the main UI,
    keeping one backend implementation and one security model.
    """
    if getattr(module, "_adbgath_dashboard_pairing_360_patched", False):
        return

    original_create_app = module.create_app

    def create_app(*, workspace=None, service=None, remote_token=None, secure_cookie=False):
        app = original_create_app(
            workspace=workspace,
            service=service,
            remote_token=remote_token,
            secure_cookie=secure_cookie,
        )

        for route in app.routes:
            if getattr(route, "path", None) != "/" or "GET" not in (getattr(route, "methods", set()) or set()):
                continue
            original_index = route.endpoint

            async def index_with_pairing(request, _original=original_index):
                response = await _original(request)
                if getattr(response, "status_code", 500) != 200 or not hasattr(response, "body"):
                    return response
                html = response.body.decode("utf-8")
                if "view-wireless-main" not in html:
                    html = html.replace(
                        '<button class="nav-item" data-view="workspace">',
                        NAV_ITEM + '\n        <button class="nav-item" data-view="workspace">',
                        1,
                    )
                    html = html.replace(
                        '<section id="view-workspace" class="view">',
                        WIRELESS_VIEW + '\n      <section id="view-workspace" class="view">',
                        1,
                    )
                if "/static/dashboardpairing360.css" not in html:
                    html = html.replace(
                        '<link rel="stylesheet" href="/static/styles.css">',
                        '<link rel="stylesheet" href="/static/styles.css">\n  <link rel="stylesheet" href="/static/dashboardpairing360.css">',
                        1,
                    )
                if "/static/dashboardpairing360.js" not in html:
                    html = html.replace(
                        "</body>",
                        '  <script src="/static/dashboardpairing360.js" defer></script>\n</body>',
                        1,
                    )
                response.body = html.encode("utf-8")
                response.headers["content-length"] = str(len(response.body))
                return response

            route.endpoint = index_with_pairing
            if hasattr(route, "dependant"):
                route.dependant.call = index_with_pairing
            break

        return app

    module.create_app = create_app
    module._adbgath_dashboard_pairing_360_patched = True
