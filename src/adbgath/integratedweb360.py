from __future__ import annotations

import inspect
from typing import Any

from fastapi.responses import RedirectResponse


LAB_VIEW = r'''
<section id="view-lab-main" class="view">
  <div class="integrated-section-head">
    <div>
      <span class="tag">DISTRIBUTED LAB</span>
      <h2>Distributed Android assessment lab</h2>
      <p>Manage mTLS agents, policy-controlled jobs, content-addressed evidence and tamper-evident audit history without leaving the main ADB-Gath workspace.</p>
    </div>
    <span class="integrated-status-badge">LOCAL CONTROL PLANE</span>
  </div>

  <div class="lab-metrics integrated-metrics">
    <article><span>AGENTS</span><strong id="agentCount">0</strong></article>
    <article><span>POOLS</span><strong id="poolCount">0</strong></article>
    <article><span>JOBS</span><strong id="jobCount">0</strong></article>
    <article><span>AUDIT</span><strong id="auditState">--</strong></article>
  </div>

  <div class="lab-grid integrated-lab-grid">
    <article class="panel">
      <div class="panel-head"><div><span class="tag">AGENTS</span><h2>Enrolled workers</h2></div><button id="refreshLab" class="secondary">Refresh</button></div>
      <div id="agents" class="lab-list empty-state">No agents enrolled.</div>
    </article>
    <article class="panel">
      <div class="panel-head"><div><span class="tag">JOBS</span><h2>Distributed operations</h2></div></div>
      <label>Agent<input id="jobAgent" placeholder="agent ID or name" autocomplete="off"></label>
      <label>Operation<input id="jobAction" placeholder="devices" autocomplete="off"></label>
      <label>JSON payload<textarea id="jobPayload" rows="4">{}</textarea></label>
      <div class="row"><select id="jobRole"><option>viewer</option><option>analyst</option><option selected>operator</option><option>administrator</option></select><label class="inline"><input id="jobApproved" type="checkbox"> Explicit approval</label></div>
      <button id="submitJob" class="primary">Queue allowlisted job</button>
      <div id="jobs" class="lab-list"></div>
    </article>
    <article class="panel">
      <div class="panel-head"><div><span class="tag">POLICY</span><h2>RBAC decision</h2></div></div>
      <div class="row"><select id="policyRole"><option>viewer</option><option>analyst</option><option>operator</option><option>administrator</option></select><input id="policyAction" placeholder="security"></div>
      <button id="checkPolicy" class="secondary">Evaluate policy</button>
      <pre id="policyOutput" class="console">Ready.</pre>
    </article>
    <article class="panel">
      <div class="panel-head"><div><span class="tag">EVIDENCE</span><h2>Content-addressed store</h2></div></div>
      <div id="artifactStatus" class="lab-list">Not loaded yet.</div>
      <button id="verifyArtifacts" class="secondary">Verify object integrity</button>
      <pre id="artifactOutput" class="console">Ready.</pre>
    </article>
    <article class="panel full">
      <div class="panel-head"><div><span class="tag">AUDIT CHAIN</span><h2>Recent policy and agent events</h2></div><button id="verifyAudit" class="secondary">Verify chain</button></div>
      <div id="auditEvents" class="audit-list empty-state">No events.</div>
    </article>
  </div>
  <div id="labToast" class="toast"></div>
</section>
'''


ADVANCED_WIRELESS = r'''
<article id="advancedWirelessPanel" class="panel wireless-advanced-panel hidden">
  <div class="panel-head">
    <div><span class="tag">ADVANCED WIRELESS</span><h3>Diagnostics, known targets and live broker</h3></div>
    <span id="dashAdvancedState" class="wireless-badge">IDLE</span>
  </div>
  <p class="muted">Advanced controls reuse the same Wireless Debugging backend and stay inside the main workspace.</p>
  <div class="wireless-advanced-grid">
    <section>
      <h4>Diagnostics</h4>
      <div class="wireless-button-row">
        <button id="dashDiagnose" class="secondary">Run diagnostics</button>
        <button id="dashRepair" class="secondary">Repair mDNS</button>
      </div>
      <pre id="dashDiagnosticOutput" class="console compact-console">Not run yet.</pre>
    </section>
    <section>
      <h4>Connection control</h4>
      <div class="wireless-button-row">
        <button id="dashDisconnect" class="secondary">Disconnect current endpoint</button>
        <button id="dashRefreshKnown" class="secondary">Refresh known targets</button>
      </div>
      <div id="dashKnownWireless" class="wireless-service-list empty-state">Known targets not loaded.</div>
    </section>
    <section class="wide">
      <div class="advanced-title-row"><h4>Live broker</h4><div class="wireless-button-row"><button id="dashStartWirelessWatch" class="secondary">Start live watch</button><button id="dashStopWirelessWatch" class="secondary" disabled>Stop</button></div></div>
      <pre id="dashBrokerOutput" class="console compact-console">Live wireless events are stopped.</pre>
    </section>
  </div>
</article>
'''


def _inject_assets(html: str) -> str:
    styles = (
        '<link rel="stylesheet" href="/static/lab360.css">\n'
        '  <link rel="stylesheet" href="/static/integratedweb360.css">'
    )
    if "/static/integratedweb360.css" not in html:
        if '<link rel="stylesheet" href="/static/theme360.css">' in html:
            html = html.replace('<link rel="stylesheet" href="/static/theme360.css">', styles + '\n  <link rel="stylesheet" href="/static/theme360.css">', 1)
        else:
            html = html.replace("</head>", "  " + styles + "\n</head>", 1)
    scripts = (
        '  <script src="/static/lab360.js" defer></script>\n'
        '  <script src="/static/integratedweb360.js" defer></script>\n'
    )
    if "/static/integratedweb360.js" not in html:
        html = html.replace("</body>", scripts + "</body>", 1)
    return html


def _integrate_dashboard(response: Any):
    if getattr(response, "status_code", 500) != 200 or not hasattr(response, "body"):
        return response
    try:
        html = response.body.decode("utf-8")
    except Exception:
        return response

    legacy_lab = '<a class="nav-item lab-link" href="/lab"><span>⌬</span>Distributed Lab</a>'
    integrated_lab = '<button class="nav-item" data-view="lab-main"><span>⌬</span>Distributed Lab</button>'
    if legacy_lab in html:
        html = html.replace(legacy_lab, integrated_lab, 1)
    elif 'data-view="lab-main"' not in html:
        html = html.replace("</nav>", integrated_lab + "</nav>", 1)

    legacy_advanced = '<a class="secondary wireless-advanced-link" href="/wireless">Advanced wireless workspace</a>'
    advanced_button = '<button id="toggleAdvancedWireless" class="secondary wireless-advanced-link" type="button">Advanced wireless controls</button>'
    html = html.replace(legacy_advanced, advanced_button, 1)

    workspace_marker = '<section id="view-workspace" class="view">'
    workspace_index = html.find(workspace_marker)
    if workspace_index >= 0:
        if 'id="advancedWirelessPanel"' not in html:
            wireless_close = html.rfind("</section>", 0, workspace_index)
            if wireless_close >= 0:
                html = html[:wireless_close] + ADVANCED_WIRELESS + "\n" + html[wireless_close:]
                workspace_index = html.find(workspace_marker)
        if 'id="view-lab-main"' not in html:
            html = html[:workspace_index] + LAB_VIEW + "\n      " + html[workspace_index:]

    html = _inject_assets(html)
    response.body = html.encode("utf-8")
    response.headers["content-length"] = str(len(response.body))
    return response


def patch_webapp(module: Any) -> None:
    if getattr(module, "_adbgath_integrated_web_sections_360_patched", False):
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
            if "GET" not in methods:
                continue
            original_endpoint = route.endpoint

            if path == "/":
                async def integrated_index(*args, _original=original_endpoint, **kwargs):
                    result = _original(*args, **kwargs)
                    if inspect.isawaitable(result):
                        result = await result
                    return _integrate_dashboard(result)

                route.endpoint = integrated_index
                if hasattr(route, "dependant"):
                    route.dependant.call = integrated_index

            elif path == "/lab":
                async def integrated_lab_redirect(*args, **kwargs):
                    return RedirectResponse(url="/?view=lab-main", status_code=302)

                route.endpoint = integrated_lab_redirect
                if hasattr(route, "dependant"):
                    route.dependant.call = integrated_lab_redirect

            elif path == "/wireless":
                async def integrated_wireless_redirect(*args, **kwargs):
                    return RedirectResponse(url="/?view=wireless-main&advanced=1", status_code=302)

                route.endpoint = integrated_wireless_redirect
                if hasattr(route, "dependant"):
                    route.dependant.call = integrated_wireless_redirect

        return app

    module.create_app = create_app
    module._adbgath_integrated_web_sections_360_patched = True
