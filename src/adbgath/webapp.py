from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import secrets
import threading
import webbrowser
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .errors import AdbgathError
from .service import WEB_ACTIONS, AdbgathService
from .validation import ensure_within

LOGGER = logging.getLogger(__name__)


class ExecuteRequest(BaseModel):
    action: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    confirmation: str | None = None


DESTRUCTIVE_ACTIONS = {"install", "uninstall", "replace", "proxy", "forward", "push_tcpdump"}


def create_app(*, workspace: str | Path | None = None, service: AdbgathService | None = None) -> FastAPI:
    static_dir = Path(__file__).parent / "web" / "static"
    session_token = secrets.token_urlsafe(32)
    app = FastAPI(
        title="adbgath Web",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.service = service
    app.state.workspace = workspace
    app.state.session_token = session_token
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"],
    )
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        return response

    def get_service() -> AdbgathService:
        if app.state.service is None:
            app.state.service = AdbgathService(workspace=app.state.workspace)
        return app.state.service

    def require_session(request: Request) -> None:
        if request.cookies.get("adbgath_session") != app.state.session_token:
            raise HTTPException(status_code=403, detail="Invalid local session.")

    @app.exception_handler(AdbgathError)
    async def handle_adbgath_error(_: Request, exc: AdbgathError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        LOGGER.exception("Unhandled web application error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "Unexpected server error."},
        )

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        response = HTMLResponse((static_dir / "index.html").read_text(encoding="utf-8"))
        response.set_cookie(
            "adbgath_session",
            session_token,
            httponly=True,
            samesite="strict",
            secure=False,
            max_age=12 * 60 * 60,
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self' ws://127.0.0.1:* ws://localhost:* ws://[::1]:*; "
            "frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'"
        )
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/api/bootstrap")
    async def bootstrap(request: Request) -> dict[str, Any]:
        require_session(request)
        service_instance = get_service()
        doctor: dict[str, Any]
        try:
            doctor = service_instance.doctor()
        except AdbgathError as exc:
            doctor = {"ok": False, "error": str(exc), "checks": []}
        devices: list[dict[str, Any]] = []
        with contextlib.suppress(AdbgathError):
            devices = service_instance.devices()
        return {
            "ok": True,
            "version": __version__,
            "workspace": str(service_instance.workspace),
            "doctor": doctor,
            "devices": devices,
            "destructive_actions": sorted(DESTRUCTIVE_ACTIONS),
            "actions": sorted(WEB_ACTIONS),
        }

    @app.get("/api/devices")
    async def devices(request: Request) -> dict[str, Any]:
        require_session(request)
        return {"ok": True, "data": get_service().devices()}

    @app.post("/api/execute")
    async def execute(request: Request, body: ExecuteRequest) -> dict[str, Any]:
        require_session(request)
        if body.action in DESTRUCTIVE_ACTIONS and body.confirmation != "AUTHORIZED":
            raise HTTPException(
                status_code=409,
                detail="Destructive action requires the confirmation value AUTHORIZED.",
            )
        result = await asyncio.to_thread(get_service().dispatch, body.action, body.payload)
        if hasattr(result, "to_dict"):
            result = result.to_dict()
        return {"ok": True, "data": result}

    @app.post("/api/upload")
    async def upload(request: Request, file: Annotated[UploadFile, File(...)]) -> dict[str, Any]:
        require_session(request)
        service_instance = get_service()
        filename = Path(file.filename or "upload.bin").name
        if not filename or filename in {".", ".."}:
            raise HTTPException(status_code=400, detail="Invalid filename.")
        uploads = service_instance.workspace / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        target = ensure_within(uploads / filename, uploads)
        max_bytes = 512 * 1024 * 1024
        written = 0
        with target.open("wb") as handle:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    handle.close()
                    target.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="Upload exceeds 512 MiB.")
                handle.write(chunk)
        return {"ok": True, "path": str(target), "name": filename, "size": written}

    @app.get("/api/artifact")
    async def artifact(request: Request, path: str) -> FileResponse:
        require_session(request)
        service_instance = get_service()
        target = ensure_within(Path(path), service_instance.workspace)
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Artifact not found.")
        return FileResponse(target, filename=target.name)

    @app.websocket("/ws/logs")
    async def websocket_logs(websocket: WebSocket) -> None:
        if websocket.cookies.get("adbgath_session") != app.state.session_token:
            await websocket.close(code=4403)
            return
        origin = websocket.headers.get("origin")
        allowed_origins = {
            f"http://127.0.0.1:{websocket.url.port}",
            f"http://localhost:{websocket.url.port}",
            f"http://[::1]:{websocket.url.port}",
        }
        if origin and origin not in allowed_origins:
            await websocket.close(code=4403)
            return
        await websocket.accept()
        try:
            params = websocket.query_params
            serial = params.get("device")
            package = params.get("package") or None
            regex = params.get("regex") or None
            log_format = params.get("format") or "threadtime"
            service_instance = get_service()
            iterator = service_instance.logs_stream(
                serial,
                package=package,
                regex=regex,
                log_format=log_format,
            )
            while True:
                line = await asyncio.to_thread(next, iterator, None)
                if line is None:
                    break
                await websocket.send_text(json.dumps({"line": line}))
        except WebSocketDisconnect:
            pass
        except AdbgathError as exc:
            with contextlib.suppress(RuntimeError):
                await websocket.send_text(json.dumps({"error": str(exc)}))
        except Exception:
            LOGGER.exception("Unhandled log stream error")
            with contextlib.suppress(RuntimeError):
                await websocket.send_text(json.dumps({"error": "Unexpected log stream error."}))
        finally:
            with contextlib.suppress(RuntimeError):
                await websocket.close()

    return app


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    workspace: str | Path | None = None,
) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise AdbgathError("The web interface is intentionally restricted to the local loopback interface.")
    import uvicorn

    url = f"http://{host if host != '::1' else '[::1]'}:{port}"
    print(f"adbgath web UI: {url}")
    print("The server is local-only by default and does not expose an arbitrary shell endpoint.")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(workspace=workspace), host=host, port=port, log_level="info")


def main() -> None:
    serve()


app = create_app()
