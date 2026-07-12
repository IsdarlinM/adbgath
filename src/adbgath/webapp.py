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
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .core.files import collision_safe_path, sha256_file
from .core.jobs import JobManager
from .core.operations import OPERATIONS, WEB_ACTIONS, operation_catalog, validate_operation_payload
from .errors import AdbgathError
from .service import AdbgathService
from .validation import ensure_within

LOGGER = logging.getLogger(__name__)


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    confirmation: str | None = Field(default=None, max_length=32)


DESTRUCTIVE_ACTIONS = {name for name, operation in OPERATIONS.items() if operation.destructive}
LONG_RUNNING_ACTIONS = {name for name, operation in OPERATIONS.items() if operation.long_running}


def create_app(
    *,
    workspace: str | Path | None = None,
    service: AdbgathService | None = None,
    remote_token: str | None = None,
    secure_cookie: bool = False,
) -> FastAPI:
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
    app.state.job_manager = None
    app.state.remote_token = remote_token
    app.state.secure_cookie = secure_cookie
    app.state.login_attempts = {}
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*"] if remote_token else ["127.0.0.1", "localhost", "[::1]", "testserver"],
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

    def get_job_manager() -> JobManager:
        if app.state.job_manager is None:
            app.state.job_manager = JobManager(get_service().store)
        return app.state.job_manager

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

    def apply_index_headers(response: HTMLResponse) -> HTMLResponse:
        response.headers["Cache-Control"] = "no-store"
        connect_scheme = "wss:" if app.state.secure_cookie else "ws:"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            f"img-src 'self' data:; connect-src 'self' {connect_scheme}; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if app.state.secure_cookie:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    def authenticated_response() -> HTMLResponse:
        response = HTMLResponse((static_dir / "index.html").read_text(encoding="utf-8"))
        response.set_cookie(
            "adbgath_session",
            session_token,
            httponly=True,
            samesite="strict",
            secure=app.state.secure_cookie,
            max_age=12 * 60 * 60,
        )
        return apply_index_headers(response)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        if not app.state.remote_token or request.cookies.get("adbgath_session") == session_token:
            return authenticated_response()
        login = """<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>ADB-Gath sign in</title><link rel='stylesheet' href='/static/styles.css'></head><body><main class='login-shell'><form class='login-panel' method='post' action='/login'><strong>ADB-Gath</strong><small>Defensive ADB Toolkit</small><h1>Remote workspace sign in</h1><p>Enter the operator token configured when this server was started.</p><label><span>Operator token</span><input type='password' name='token' minlength='24' required autocomplete='current-password'></label><button class='primary' type='submit'>Sign in</button></form></main></body></html>"""
        return apply_index_headers(HTMLResponse(login, status_code=401))

    @app.post("/login", response_class=HTMLResponse)
    async def login(request: Request) -> HTMLResponse:
        if not app.state.remote_token:
            raise HTTPException(status_code=404, detail="Remote authentication is disabled.")
        client = request.client.host if request.client else "unknown"
        now = asyncio.get_running_loop().time()
        attempts = [value for value in app.state.login_attempts.get(client, []) if now - value < 60]
        if len(attempts) >= 5:
            raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
        form = await request.form()
        supplied = str(form.get("token", ""))
        if not secrets.compare_digest(supplied, app.state.remote_token):
            attempts.append(now)
            app.state.login_attempts[client] = attempts
            raise HTTPException(status_code=403, detail="Invalid operator token.")
        app.state.login_attempts.pop(client, None)
        return authenticated_response()

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
            "long_running_actions": sorted(LONG_RUNNING_ACTIONS),
            "actions": sorted(WEB_ACTIONS),
            "operations": operation_catalog(),
            "projects": service_instance.store.list_projects(),
            "snapshots": service_instance.store.list_snapshots(),
            "groups": service_instance.store.list_groups(),
            "jobs": service_instance.store.list_jobs(25),
        }

    @app.get("/api/devices")
    async def devices(request: Request) -> dict[str, Any]:
        require_session(request)
        return {"ok": True, "data": get_service().devices()}

    @app.post("/api/execute")
    async def execute(request: Request, body: ExecuteRequest) -> dict[str, Any]:
        require_session(request)
        if body.action not in WEB_ACTIONS:
            raise HTTPException(status_code=400, detail="Unsupported action.")
        if body.action in DESTRUCTIVE_ACTIONS and body.confirmation != "AUTHORIZED":
            raise HTTPException(
                status_code=409,
                detail="Destructive action requires the confirmation value AUTHORIZED.",
            )
        try:
            payload = validate_operation_payload(body.action, body.payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        result = await asyncio.to_thread(get_service().dispatch, body.action, payload)
        if hasattr(result, "to_dict"):
            result = result.to_dict()
        return {"ok": True, "data": result}

    @app.get("/api/operations")
    async def operations(request: Request) -> dict[str, Any]:
        require_session(request)
        return {"ok": True, "data": operation_catalog()}

    @app.get("/api/projects")
    async def projects(request: Request) -> dict[str, Any]:
        require_session(request)
        return {"ok": True, "data": get_service().store.list_projects()}

    @app.get("/api/findings")
    async def findings(request: Request, project_id: str | None = None) -> dict[str, Any]:
        require_session(request)
        return {"ok": True, "data": get_service().store.list_findings(project_id)}

    @app.get("/api/snapshots")
    async def snapshots(request: Request, project_id: str | None = None) -> dict[str, Any]:
        require_session(request)
        return {"ok": True, "data": get_service().store.list_snapshots(project_id)}

    @app.get("/api/jobs")
    async def jobs(request: Request) -> dict[str, Any]:
        require_session(request)
        return {"ok": True, "data": get_job_manager().list()}

    @app.post("/api/jobs")
    async def create_job(request: Request, body: ExecuteRequest) -> dict[str, Any]:
        require_session(request)
        if body.action not in WEB_ACTIONS:
            raise HTTPException(status_code=400, detail="Unsupported action.")
        if body.action in DESTRUCTIVE_ACTIONS and body.confirmation != "AUTHORIZED":
            raise HTTPException(
                status_code=409, detail="Destructive action requires the confirmation value AUTHORIZED."
            )
        try:
            payload = validate_operation_payload(body.action, body.payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        def execute_job(cancel_event, progress):
            if cancel_event.is_set():
                return {"cancelled": True}
            progress(10)
            result = get_service().dispatch(body.action, payload)
            progress(90)
            if hasattr(result, "to_dict"):
                result = result.to_dict()
            return result

        job = get_job_manager().submit(body.action, payload, execute_job)
        return {"ok": True, "data": job}

    @app.get("/api/jobs/{job_id}")
    async def get_job(request: Request, job_id: str) -> dict[str, Any]:
        require_session(request)
        try:
            data = get_job_manager().get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"ok": True, "data": data}

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(request: Request, job_id: str) -> dict[str, Any]:
        require_session(request)
        try:
            data = get_job_manager().cancel(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"ok": True, "data": data}

    @app.get("/api/artifacts")
    async def artifacts(request: Request) -> dict[str, Any]:
        require_session(request)
        root = get_service().workspace
        data = []
        for item in sorted(
            root.rglob("*"), key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True
        ):
            if not item.is_file() or item.name == "adbgath.db" or "-wal" in item.name or "-shm" in item.name:
                continue
            data.append(
                {"path": str(item), "name": item.name, "size": item.stat().st_size, "modified": item.stat().st_mtime}
            )
            if len(data) >= 500:
                break
        return {"ok": True, "data": data}

    @app.post("/api/upload")
    async def upload(request: Request, file: Annotated[UploadFile, File(...)]) -> dict[str, Any]:
        require_session(request)
        service_instance = get_service()
        filename = Path(file.filename or "upload.bin").name
        if not filename or filename in {".", ".."}:
            raise HTTPException(status_code=400, detail="Invalid filename.")
        uploads = service_instance.workspace / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        target = ensure_within(collision_safe_path(uploads, filename), uploads)
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
        return {"ok": True, "path": str(target), "name": target.name, "size": written, "sha256": sha256_file(target)}

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
        scheme = "https" if app.state.secure_cookie else "http"
        allowed_origins = {
            f"{scheme}://{websocket.headers.get('host')}",
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
    remote_token: str | None = None,
    tls_cert: str | Path | None = None,
    tls_key: str | Path | None = None,
) -> None:
    loopback = host in {"127.0.0.1", "localhost", "::1"}
    if not loopback:
        if not remote_token or len(remote_token) < 24:
            raise AdbgathError("Remote mode requires --remote-token with at least 24 characters.")
        if not tls_cert or not tls_key:
            raise AdbgathError("Remote mode requires --tls-cert and --tls-key; plaintext remote access is refused.")
        certificate = Path(tls_cert).expanduser().resolve()
        private_key = Path(tls_key).expanduser().resolve()
        if not certificate.is_file() or not private_key.is_file():
            raise AdbgathError("The TLS certificate or private key does not exist.")
    else:
        certificate = Path(tls_cert).expanduser().resolve() if tls_cert else None
        private_key = Path(tls_key).expanduser().resolve() if tls_key else None
    import uvicorn

    scheme = "https" if certificate and private_key else "http"
    shown_host = host if host not in {"::1", "0.0.0.0"} else ("[::1]" if host == "::1" else "HOSTNAME")
    url = f"{scheme}://{shown_host}:{port}"
    print(f"ADB-Gath web UI: {url}")
    print("Remote access is disabled by default; no arbitrary shell endpoint is exposed.")
    if open_browser and loopback:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    uvicorn.run(
        create_app(workspace=workspace, remote_token=remote_token, secure_cookie=bool(certificate)),
        host=host,
        port=port,
        log_level="info",
        ssl_certfile=str(certificate) if certificate else None,
        ssl_keyfile=str(private_key) if private_key else None,
    )


def main() -> None:
    serve()


app = create_app()
