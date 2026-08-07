from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from .core.jobs import JobManager
from .core.operations import OPERATIONS, WEB_ACTIONS, validate_operation_payload

WIRELESS_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ADB-Gath Wireless Debugging</title><link rel="stylesheet" href="/static/styles.css"><link rel="stylesheet" href="/static/wireless.css"></head>
<body><div class="wireless-shell">
<header class="wireless-header"><div><strong>ADB-Gath</strong><span>Wireless Debugging</span></div><nav><a href="/">Dashboard</a><button id="refreshAll">Refresh</button></nav></header>
<main>
<section class="wireless-hero"><div><p class="eyebrow">Android 11+ pairing-code workflow</p><h1>Discover, pair and connect safely</h1><p>The temporary pairing port and the later connection port are different. Pair first, then connect to the endpoint shown on Android's main Wireless debugging screen.</p></div><div id="wirelessHealth" class="health-card">Loading ADB and mDNS status…</div></section>
<section class="wireless-actions">
<article class="wireless-card"><h2>1. Discover</h2><p>Find `_adb-tls-pairing` and `_adb-tls-connect` services.</p><div class="button-row"><button id="discover" class="primary">Discover now</button><button id="watch">Start live watch</button><button id="autoConnect">Auto-connect</button></div></article>
<article class="wireless-card"><h2>2. Pair using code</h2><label>Pairing endpoint<input id="pairEndpoint" placeholder="192.168.1.50:37123" autocomplete="off"></label><label>Six-digit code<input id="pairCode" type="password" inputmode="numeric" maxlength="6" pattern="[0-9]{6}" autocomplete="one-time-code"></label><button id="pair" class="primary">Pair authorized device</button></article>
<article class="wireless-card"><h2>3. Connect</h2><label>Connection endpoint<input id="connectEndpoint" placeholder="192.168.1.50:41267" autocomplete="off"></label><div class="button-row"><button id="connect" class="primary">Connect</button><button id="disconnect">Disconnect</button></div></article>
</section>
<section class="wireless-grid"><article class="wireless-card wide"><div class="card-title"><h2>Discovered services</h2><span id="serviceCount">0 services</span></div><div id="services" class="service-list empty">No services discovered yet.</div></article>
<article class="wireless-card"><h2>Diagnostics</h2><div class="button-row"><button id="diagnose">Run diagnostics</button><button id="repair">Repair mDNS</button></div><div id="diagnostics" class="diagnostic-list"></div></article>
<article class="wireless-card wide"><div class="card-title"><h2>Known targets</h2><span>Non-secret local metadata only</span></div><div id="known" class="known-list empty">No known targets.</div></article>
<article class="wireless-card wide"><h2>Activity</h2><pre id="output" aria-live="polite">Ready.</pre></article></section>
</main></div><script src="/static/wireless.js" defer></script></body></html>"""


def patch_webapp(module: Any) -> None:
    original_create_app = module.create_app

    def create_app(*, workspace=None, service=None, remote_token=None, secure_cookie=False):
        app = original_create_app(
            workspace=workspace,
            service=service,
            remote_token=remote_token,
            secure_cookie=secure_cookie,
        )

        def get_service():
            if app.state.service is None:
                app.state.service = module.AdbgathService(workspace=app.state.workspace)
            return app.state.service

        def get_jobs():
            if app.state.job_manager is None:
                app.state.job_manager = JobManager(get_service().store)
            return app.state.job_manager

        def require_session(request: Request) -> None:
            if request.cookies.get("adbgath_session") != app.state.session_token:
                raise HTTPException(status_code=403, detail="Invalid local session.")

        for route in list(app.router.routes):
            if getattr(route, "path", None) == "/api/jobs" and "POST" in (getattr(route, "methods", set()) or set()):
                app.router.routes.remove(route)

        @app.post("/api/jobs")
        async def create_job(request: Request, body: module.ExecuteRequest) -> dict[str, Any]:
            require_session(request)
            if body.action not in WEB_ACTIONS:
                raise HTTPException(status_code=400, detail="Unsupported action.")
            operation = OPERATIONS[body.action]
            if not operation.long_running:
                raise HTTPException(
                    status_code=400,
                    detail="Only catalogued long-running actions may be persisted as jobs.",
                )
            if operation.destructive and body.confirmation != "AUTHORIZED":
                raise HTTPException(status_code=409, detail="Destructive action requires AUTHORIZED confirmation.")
            try:
                payload = validate_operation_payload(body.action, body.payload)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

            def execute_job(cancel_event, progress):
                if cancel_event.is_set():
                    return {"cancelled": True}
                progress(10)
                adb = get_service().adb
                context = adb.cancellation(cancel_event) if hasattr(adb, "cancellation") else contextlib.nullcontext()
                with context:
                    result = get_service().dispatch(body.action, payload)
                progress(90)
                return result.to_dict() if hasattr(result, "to_dict") else result

            return {"ok": True, "data": get_jobs().submit(body.action, payload, execute_job)}

        @app.get("/wireless", response_class=HTMLResponse)
        async def wireless_page(request: Request) -> HTMLResponse:
            current = request.cookies.get("adbgath_session")
            if current != app.state.session_token and app.state.remote_token:
                raise HTTPException(status_code=403, detail="Sign in from the dashboard first.")
            response = HTMLResponse(WIRELESS_HTML)
            if current != app.state.session_token:
                response.set_cookie(
                    "adbgath_session",
                    app.state.session_token,
                    httponly=True,
                    samesite="strict",
                    secure=app.state.secure_cookie,
                    max_age=12 * 60 * 60,
                )
            scheme = "wss:" if app.state.secure_cookie else "ws:"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                f"connect-src 'self' {scheme}; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
            )
            response.headers["Cache-Control"] = "no-store"
            return response

        @app.websocket("/ws/wireless")
        async def wireless_watch(websocket: WebSocket) -> None:
            if websocket.cookies.get("adbgath_session") != app.state.session_token:
                await websocket.close(code=4403)
                return
            origin = websocket.headers.get("origin")
            scheme = "https" if app.state.secure_cookie else "http"
            allowed = {
                f"{scheme}://{websocket.headers.get('host')}",
                f"http://127.0.0.1:{websocket.url.port}",
                f"http://localhost:{websocket.url.port}",
                f"http://[::1]:{websocket.url.port}",
            }
            if origin and origin not in allowed:
                await websocket.close(code=4403)
                return
            await websocket.accept()
            try:
                while True:
                    data = await asyncio.to_thread(get_service().wireless_discover, refresh=True, detailed=True)
                    await websocket.send_json({"ok": True, "data": data})
                    await asyncio.sleep(3)
            except WebSocketDisconnect:
                return
            except Exception:
                with contextlib.suppress(Exception):
                    await websocket.close(code=1011)

        return app

    module.create_app = create_app
