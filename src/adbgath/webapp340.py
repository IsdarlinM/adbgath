from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from fastapi import HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field


class QrCreateRequest(BaseModel):
    ttl_seconds: int = Field(default=120, ge=30, le=300)
    auto_connect: bool = True
    confirmation: str = Field(max_length=32)


QR_CARD = """
<article class='panel wireless-card full-span qr-pairing-card'>
  <div class='panel-head'><div><span class='tag'>PAIR BY QR</span><h2>One-time QR pairing</h2></div></div>
  <p class='hint'>On Android open Developer options → Wireless debugging → Pair device with QR code. The secret remains only in memory and expires automatically.</p>
  <div class='qr-grid'>
    <div class='qr-frame'><img id='wirelessQrImage' alt='ADB Wireless Debugging pairing QR' hidden></div>
    <div class='qr-controls'>
      <label>SESSION LIFETIME<input id='wirelessQrTtl' type='number' min='30' max='300' value='120'></label>
      <label class='authorized'><input id='wirelessQrAutoConnect' type='checkbox' checked> Connect automatically after pairing.</label>
      <label class='authorized'><input id='wirelessQrAuthorized' type='checkbox'> I confirm this device is authorized and in scope.</label>
      <div class='wireless-actions'><button id='wirelessQrCreateButton' class='primary'>Create QR</button><button id='wirelessQrCancelButton' class='secondary' disabled>Cancel</button></div>
      <div id='wirelessQrState' class='qr-state'>No active QR session.</div>
    </div>
  </div>
</article>
"""

WIRELESS_PAGE = """<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><meta name='color-scheme' content='dark'><title>ADB-Gath // Wireless Debugging</title><link rel='stylesheet' href='/static/styles.css'><link rel='stylesheet' href='/static/wireless.css'><link rel='stylesheet' href='/static/wireless340.css'></head><body><div class='noise'></div><main class='wireless-shell'><header class='wireless-top'><div><a href='/' class='back-link'>← Workspace</a><p class='eyebrow'>AUTHORIZED ANDROID ASSESSMENT</p><h1>Wireless Debugging</h1><p>Discover, pair by QR or six-digit code, connect, diagnose mDNS, and manage known targets.</p></div><div class='wireless-state'><span id='wirelessDot'></span><strong id='wirelessEngine'>INITIALIZING</strong><small>ADB-Gath 3.4.0</small></div></header><section class='wireless-grid'>""" + QR_CARD + """<article class='panel wireless-card'><div class='panel-head'><div><span class='tag'>DISCOVERY</span><h2>Nearby ADB services</h2></div><div class='wireless-actions'><button id='discoverNow' class='primary'>Discover</button><button id='toggleWatch' class='secondary'>Live watch</button></div></div><p class='hint'>Pairing and connection services use different ports.</p><div class='service-columns'><div><h3>PAIRING SERVICES</h3><div id='pairingServices' class='wireless-list empty-state'>No pairing services discovered.</div></div><div><h3>CONNECTION SERVICES</h3><div id='connectServices' class='wireless-list empty-state'>No connection services discovered.</div></div></div></article><article class='panel wireless-card'><div class='panel-head'><div><span class='tag'>PAIR BY CODE</span><h2>Secure pairing</h2></div></div><label>PAIRING HOST:PORT<input id='pairTarget' placeholder='192.168.1.50:37123' autocomplete='off'></label><label>SIX-DIGIT CODE<input id='pairCode' type='password' inputmode='numeric' pattern='[0-9]{6}' maxlength='6' placeholder='000000' autocomplete='one-time-code'></label><label class='authorized'><input id='pairAuthorized' type='checkbox'> I confirm this device is authorized and in scope.</label><button id='pairDevice' class='primary full'>Pair device</button></article><article class='panel wireless-card'><div class='panel-head'><div><span class='tag'>CONNECTION</span><h2>Connect or disconnect</h2></div></div><label>CONNECTION HOST:PORT<input id='connectTarget' placeholder='192.168.1.50:41267' autocomplete='off'></label><div class='wireless-actions'><button id='connectDevice' class='primary'>Connect</button><button id='disconnectDevice' class='secondary'>Disconnect</button><button id='autoConnect' class='secondary'>Auto-connect</button></div><pre id='wirelessOutput' class='console wireless-console'>Ready.</pre></article><article class='panel wireless-card'><div class='panel-head'><div><span class='tag'>DIAGNOSTICS</span><h2>ADB and mDNS health</h2></div><div class='wireless-actions'><button id='runWirelessDoctor' class='primary'>Diagnose</button><button id='repairWireless' class='secondary'>Repair</button></div></div><div id='wirelessChecks' class='check-list empty-state'>No diagnostics yet.</div></article><article class='panel wireless-card full-span'><div class='panel-head'><div><span class='tag'>KNOWN TARGETS</span><h2>Local wireless inventory</h2></div><button id='refreshKnown' class='secondary'>Refresh</button></div><div id='knownWireless' class='wireless-list empty-state'>No known targets.</div></article></section></main><div id='wirelessToast' class='toast'></div><script src='/static/wireless.js' defer></script><script src='/static/wireless340.js' defer></script></body></html>"""


def patch_webapp(module: Any) -> None:
    if getattr(module, "_adbgath_340_patched", False):
        return
    original_create = module.create_app


    def create_app(*, workspace=None, service=None, remote_token=None, secure_cookie=False):
        app = original_create(
            workspace=workspace,
            service=service,
            remote_token=remote_token,
            secure_cookie=secure_cookie,
        )

        def get_service():
            if app.state.service is None:
                app.state.service = module.AdbgathService(workspace=app.state.workspace)
            return app.state.service

        def require_session(request: Request):
            if request.cookies.get("adbgath_session") != app.state.session_token:
                raise HTTPException(status_code=403, detail="Invalid local session.")

        for route in list(app.router.routes):
            if getattr(route, "path", None) == "/ws/wireless" or (getattr(route, "path", None) == "/wireless" and "GET" in (getattr(route, "methods", set()) or set())):
                app.router.routes.remove(route)

        @app.get("/wireless", response_class=HTMLResponse)
        async def wireless_page(request: Request):
            require_session(request)
            response = HTMLResponse(WIRELESS_PAGE)
            response.headers["Cache-Control"] = "no-store"
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' ws: wss:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
            return response

        @app.get("/api/wireless/qr/{session_id}.svg")
        async def qr_svg(request: Request, session_id: str):
            require_session(request)
            try:
                svg = get_service().qr_pairing.svg(session_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return Response(content=svg, media_type="image/svg+xml", headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"})

        @app.post("/api/wireless/qr")
        async def create_qr(request: Request, body: QrCreateRequest):
            require_session(request)
            if body.confirmation != "AUTHORIZED":
                raise HTTPException(status_code=409, detail="QR pairing requires AUTHORIZED confirmation.")
            data = await asyncio.to_thread(
                get_service().wireless_qr_create,
                ttl_seconds=body.ttl_seconds,
                auto_connect=body.auto_connect,
            )
            return {"ok": True, "data": data, "svg_url": f"/api/wireless/qr/{data['id']}.svg"}

        @app.get("/api/wireless/qr/{session_id}")
        async def qr_status(request: Request, session_id: str):
            require_session(request)
            try:
                data = get_service().wireless_qr_status(session_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return {"ok": True, "data": data}

        @app.post("/api/wireless/qr/{session_id}/cancel")
        async def cancel_qr(request: Request, session_id: str):
            require_session(request)
            try:
                data = await asyncio.to_thread(get_service().wireless_qr_cancel, session_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return {"ok": True, "data": data}

        @app.websocket("/ws/wireless")
        async def wireless_events(websocket: WebSocket):
            if websocket.cookies.get("adbgath_session") != app.state.session_token:
                await websocket.close(code=4403)
                return
            await websocket.accept()
            sequence = -1
            try:
                broker = get_service().wireless_broker
                broker.start()
                while True:
                    data = await asyncio.to_thread(broker.wait, after_sequence=sequence, timeout=20)
                    sequence = data["sequence"]
                    await websocket.send_json({"ok": True, "data": data})
            except WebSocketDisconnect:
                return
            except Exception:
                with contextlib.suppress(Exception):
                    await websocket.close(code=1011)

        @app.websocket("/ws/wireless/qr/{session_id}")
        async def qr_events(websocket: WebSocket, session_id: str):
            if websocket.cookies.get("adbgath_session") != app.state.session_token:
                await websocket.close(code=4403)
                return
            await websocket.accept()
            sequence = -1
            try:
                while True:
                    data = await asyncio.to_thread(
                        get_service().qr_pairing.wait,
                        session_id,
                        after_sequence=sequence,
                        timeout=20,
                    )
                    sequence = data["sequence"]
                    await websocket.send_json({"ok": True, "data": data})
                    if data["terminal"]:
                        return
            except (KeyError, WebSocketDisconnect):
                return
            except Exception:
                with contextlib.suppress(Exception):
                    await websocket.close(code=1011)

        return app

    module.create_app = create_app
    module._adbgath_340_patched = True
