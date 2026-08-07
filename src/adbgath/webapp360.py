from __future__ import annotations

import json
import threading
import webbrowser
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse

LAB_HTML = """<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><meta name='color-scheme' content='dark'><title>ADB-Gath // Distributed Lab</title><link rel='stylesheet' href='/static/styles.css'><link rel='stylesheet' href='/static/lab360.css'></head><body><div class='noise'></div><main class='lab-shell'><header class='lab-top'><div><a href='/' class='back-link'>← Workspace</a><p class='eyebrow'>AUTHORIZED MOBILE SECURITY LAB</p><h1>Distributed Lab</h1><p>mTLS agents, policy-controlled jobs, deduplicated evidence and tamper-evident audit history.</p></div><div class='lab-badge'><strong>ADB-Gath 3.6.0</strong><span>LOCAL CONTROL PLANE</span></div></header><section class='lab-metrics'><article><span>AGENTS</span><strong id='agentCount'>0</strong></article><article><span>POOLS</span><strong id='poolCount'>0</strong></article><article><span>JOBS</span><strong id='jobCount'>0</strong></article><article><span>AUDIT</span><strong id='auditState'>--</strong></article></section><section class='lab-grid'><article class='panel'><div class='panel-head'><div><span class='tag'>AGENTS</span><h2>Enrolled workers</h2></div><button id='refreshLab' class='secondary'>Refresh</button></div><div id='agents' class='lab-list empty-state'>No agents enrolled.</div></article><article class='panel'><div class='panel-head'><div><span class='tag'>JOBS</span><h2>Distributed operations</h2></div></div><label>Agent<input id='jobAgent' placeholder='agent ID or name'></label><label>Operation<input id='jobAction' placeholder='devices'></label><label>JSON payload<textarea id='jobPayload' rows='4'>{}</textarea></label><div class='row'><select id='jobRole'><option>viewer</option><option>analyst</option><option selected>operator</option><option>administrator</option></select><label class='inline'><input id='jobApproved' type='checkbox'> Explicit approval</label></div><button id='submitJob' class='primary'>Queue allowlisted job</button><div id='jobs' class='lab-list'></div></article><article class='panel'><div class='panel-head'><div><span class='tag'>POLICY</span><h2>RBAC decision</h2></div></div><div class='row'><select id='policyRole'><option>viewer</option><option>analyst</option><option>operator</option><option>administrator</option></select><input id='policyAction' placeholder='security'></div><button id='checkPolicy' class='secondary'>Evaluate policy</button><pre id='policyOutput' class='console'>Ready.</pre></article><article class='panel'><div class='panel-head'><div><span class='tag'>EVIDENCE</span><h2>Content-addressed store</h2></div></div><div id='artifactStatus' class='lab-list'>Loading…</div><button id='verifyArtifacts' class='secondary'>Verify object integrity</button><pre id='artifactOutput' class='console'>Ready.</pre></article><article class='panel full'><div class='panel-head'><div><span class='tag'>AUDIT CHAIN</span><h2>Recent policy and agent events</h2></div><button id='verifyAudit' class='secondary'>Verify chain</button></div><div id='auditEvents' class='audit-list empty-state'>No events.</div></article></section></main><div id='labToast' class='toast'></div><script src='/static/lab360.js' defer></script></body></html>"""


def patch_webapp(module: Any) -> None:
    if getattr(module, "_adbgath_360_patched", False):
        return
    original_create_app = module.create_app

    def create_app(*, workspace=None, service=None, remote_token=None, secure_cookie=False):
        app = original_create_app(workspace=workspace, service=service, remote_token=remote_token, secure_cookie=secure_cookie)

        def get_service():
            if app.state.service is None:
                app.state.service = module.AdbgathService(workspace=app.state.workspace)
            return app.state.service

        def require_session(request: Request) -> None:
            if request.cookies.get("adbgath_session") != app.state.session_token:
                raise HTTPException(status_code=403, detail="Invalid local session.")

        for route in app.routes:
            if getattr(route, "path", None) == "/" and "GET" in (getattr(route, "methods", set()) or set()):
                original_index = route.endpoint
                async def index_360(request: Request):
                    response = await original_index(request)
                    if getattr(response, "status_code", 500) == 200 and hasattr(response, "body"):
                        html = response.body.decode("utf-8")
                        link = '<a class="nav-item lab-link" href="/lab"><span>⌬</span>Distributed Lab</a>'
                        if "lab-link" not in html:
                            html = html.replace("</nav>", f"{link}</nav>", 1)
                        for old in ("3.2.9", "3.3.0", "3.4.0"):
                            html = html.replace(old, "3.6.0")
                        response.body = html.encode("utf-8")
                        response.headers["content-length"] = str(len(response.body))
                    return response
                route.endpoint = index_360; route.dependant.call = index_360
                break

        @app.get("/lab", response_class=HTMLResponse)
        async def lab_page(request: Request) -> HTMLResponse:
            require_session(request)
            response = HTMLResponse(LAB_HTML)
            response.headers["Cache-Control"] = "no-store"
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
            return response

        @app.get("/api/lab/status")
        async def lab_status(request: Request):
            require_session(request); return {"ok": True, "data": get_service().lab_status()}

        @app.post("/api/lab/job")
        async def lab_job(request: Request, body: dict[str, Any]):
            require_session(request)
            try:
                result = get_service().lab_job_submit(
                    agent=str(body.get("agent", "")), action=str(body.get("action", "")), payload=dict(body.get("payload") or {}),
                    role=str(body.get("role", "operator")), actor="web-operator", approved=bool(body.get("approved", False)),
                )
            except (ValueError, KeyError, module.AdbgathError) as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return {"ok": True, "data": result}

        @app.post("/api/lab/policy/check")
        async def policy_check(request: Request, body: dict[str, Any]):
            require_session(request)
            result = get_service().policy_operation("check", role=str(body.get("role", "viewer")), action=str(body.get("action", "")), approved=bool(body.get("approved", False)))
            return {"ok": True, "data": result}

        @app.get("/api/lab/audit")
        async def audit(request: Request, limit: int = 100):
            require_session(request); return {"ok": True, "data": get_service().audit_operation("list", limit=limit)}

        @app.get("/api/lab/audit/verify")
        async def audit_verify(request: Request):
            require_session(request); return {"ok": True, "data": get_service().audit_operation("verify")}

        @app.get("/api/artifact-store/status")
        async def artifact_status(request: Request):
            require_session(request); return {"ok": True, "data": get_service().artifact_store("status")}

        @app.get("/api/artifact-store/verify")
        async def artifact_verify(request: Request):
            require_session(request); return {"ok": True, "data": get_service().artifact_store("verify")}

        return app

    def serve(*, host="127.0.0.1", port=8765, open_browser=True, workspace=None, remote_token=None, tls_cert=None, tls_key=None):
        loopback = host in {"127.0.0.1", "localhost", "::1"}
        if not loopback:
            if not remote_token or len(remote_token) < 24:
                raise module.AdbgathError("Remote mode requires --remote-token with at least 24 characters.")
            if not tls_cert or not tls_key:
                raise module.AdbgathError("Remote mode requires --tls-cert and --tls-key; plaintext remote access is refused.")
        certificate = Path(tls_cert).expanduser().resolve() if tls_cert else None
        private_key = Path(tls_key).expanduser().resolve() if tls_key else None
        if certificate and not certificate.is_file():
            raise module.AdbgathError("The TLS certificate does not exist.")
        if private_key and not private_key.is_file():
            raise module.AdbgathError("The TLS private key does not exist.")

        import uvicorn

        scheme = "https" if certificate and private_key else "http"
        shown_host = host if host not in {"::1", "0.0.0.0"} else ("[::1]" if host == "::1" else "HOSTNAME")
        url = f"{scheme}://{shown_host}:{port}"
        print(f"ADB-Gath web UI: {url}")
        print("Remote access is disabled by default; no arbitrary shell endpoint is exposed.")
        if open_browser and loopback:
            threading.Timer(0.8, lambda: webbrowser.open(url)).start()
        application = module.create_app(
            workspace=workspace,
            remote_token=remote_token,
            secure_cookie=bool(certificate),
        )
        uvicorn.run(
            application,
            host=host,
            port=port,
            log_level="info",
            ssl_certfile=str(certificate) if certificate else None,
            ssl_keyfile=str(private_key) if private_key else None,
        )

    def main() -> None:
        serve()

    module.create_app = create_app
    module.serve = serve
    module.main = main
    module._adbgath_360_patched = True
