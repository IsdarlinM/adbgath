from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import inspect
import os
import threading
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .core.auth370 import AuthSession, AuthStore
from .core.jobs import JobManager

AUTH_COOKIE = "adbgath_auth"
LEGACY_COOKIE = "adbgath_session"
SESSION_SECONDS = 12 * 60 * 60
_current_session: ContextVar[AuthSession | None] = ContextVar("adbgath_auth_session_370", default=None)


def _escape(value: Any) -> str:
    import html
    return html.escape(str(value if value is not None else ""), quote=True)


def _legacy_workspace(workspace: str | Path | None) -> Path | None:
    candidate = Path(
        workspace
        or os.environ.get("ADBGATH_WORKSPACE", "")
        or (Path.home() / "adbgath-workspace")
    ).expanduser().resolve()
    if not candidate.exists():
        return None
    try:
        meaningful = (candidate / "adbgath.db").is_file() or any(candidate.iterdir())
    except OSError:
        meaningful = False
    return candidate if meaningful else None


class TenantServiceProxy:
    """Resolve business logic from the authenticated workspace context."""

    def __init__(self, service_class, *, template_service=None) -> None:
        self._service_class = service_class
        self._template_adb = getattr(template_service, "adb", None) if template_service is not None else None
        self._services: dict[str, Any] = {}
        self._lock = threading.RLock()

    def for_path(self, workspace: str | Path):
        path = str(Path(workspace).expanduser().resolve())
        with self._lock:
            service = self._services.get(path)
            if service is None:
                service = self._service_class(self._template_adb, workspace=path)
                self._services[path] = service
            return service

    def current(self):
        session = _current_session.get()
        if session is None:
            raise RuntimeError("No authenticated workspace is bound to the current request.")
        return self.for_path(session.workspace_path)

    def __getattr__(self, name: str):
        return getattr(self.current(), name)


class TenantJobRegistry:
    def __init__(self) -> None:
        self._managers: dict[str, JobManager] = {}
        self._lock = threading.RLock()

    def for_service(self, service) -> JobManager:
        key = str(service.workspace)
        with self._lock:
            manager = self._managers.get(key)
            if manager is None:
                manager = JobManager(service.store)
                self._managers[key] = manager
            return manager


LOGIN_HTML = """<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><meta name='color-scheme' content='dark'><title>ADB-Gath // Sign in</title><link rel='stylesheet' href='/static/styles.css'><link rel='stylesheet' href='/static/theme360.css'><link rel='stylesheet' href='/static/auth370.css'></head><body><div class='noise'></div><main class='auth370-shell'><form class='auth370-panel' method='post' action='/auth/login'><span class='tag'>ADB-GATH 3.7.0</span><h1>Sign in</h1><p>Authenticate to access your isolated Android assessment workspaces.</p>{error}<label><span>Username</span><input name='username' minlength='3' maxlength='64' autocomplete='username' required autofocus></label><label><span>Password</span><input name='password' type='password' minlength='12' maxlength='1024' autocomplete='current-password' required></label><button class='primary' type='submit'>Sign in</button></form></main></body></html>"""

SETUP_HTML = """<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><meta name='color-scheme' content='dark'><title>ADB-Gath // First-run setup</title><link rel='stylesheet' href='/static/styles.css'><link rel='stylesheet' href='/static/theme360.css'><link rel='stylesheet' href='/static/auth370.css'></head><body><div class='noise'></div><main class='auth370-shell'><form class='auth370-panel' method='post' action='/auth/setup'><span class='tag'>ADB-GATH 3.7.0</span><h1>Create the first administrator</h1><p>Passwords are stored with scrypt. The server never stores plaintext session tokens.</p>{legacy}{error}<label><span>Administrator username</span><input name='username' minlength='3' maxlength='64' pattern='[A-Za-z0-9_.-]{{3,64}}' autocomplete='username' required autofocus></label><label><span>Password</span><input name='password' type='password' minlength='12' maxlength='1024' autocomplete='new-password' required></label><label><span>Confirm password</span><input name='confirm_password' type='password' minlength='12' maxlength='1024' autocomplete='new-password' required></label><button class='primary' type='submit'>Initialize secure workspace</button></form></main></body></html>"""

USERS_VIEW = r'''
<section id="view-users370" class="view">
  <div class="integrated-section-head"><div><span class="tag">SERVER ACCESS</span><h2>Users and workspace isolation</h2><p>Create server users. Every account gets its own workspace namespace and cannot select another user's workspace.</p></div><span class="integrated-status-badge">ADMINISTRATOR</span></div>
  <div class="split-layout auth370-admin-grid">
    <article class="panel"><div class="panel-head"><div><span class="tag">CREATE USER</span><h3>New server account</h3></div></div><div class="form-grid"><label><span>Username</span><input id="auth370NewUsername" autocomplete="off"></label><label><span>Display name</span><input id="auth370NewDisplay" autocomplete="off"></label><label><span>Role</span><select id="auth370NewRole"><option value="user">User</option><option value="administrator">Administrator</option></select></label><label><span>Initial password</span><input id="auth370NewPassword" type="password" minlength="12" autocomplete="new-password"></label></div><div class="execute-row"><button id="auth370CreateUser" class="primary">Create user</button></div></article>
    <article class="panel"><div class="panel-head"><div><span class="tag">ACCOUNTS</span><h3>Server users</h3></div><button id="auth370RefreshUsers" class="secondary">Refresh</button></div><div id="auth370UserList" class="data-list empty-state">Loading users…</div></article>
  </div>
</section>
'''

WORKSPACE_DIALOG = r'''
<dialog id="auth370WorkspaceDialog" class="auth370-dialog"><form method="dialog"><div class="panel-head"><div><span class="tag">WORKSPACE</span><h3>Create workspace</h3></div><button value="cancel" class="text-button">CLOSE</button></div><label><span>Name</span><input id="auth370WorkspaceName" maxlength="80" autocomplete="off" placeholder="Mobile assessment"></label><div class="execute-row"><button id="auth370WorkspaceCreate" type="button" class="primary">Create and select</button></div></form></dialog>
'''


def _auth_page(template: str, *, error: str = "", legacy: Path | None = None) -> HTMLResponse:
    error_html = f"<div class='auth370-error'>{_escape(error)}</div>" if error else ""
    legacy_html = ""
    if legacy is not None:
        legacy_html = f"<div class='auth370-notice'>Existing 3.6 workspace detected at <code>{_escape(legacy)}</code>. It will be assigned to the first administrator without moving its files.</div>"
    html = template.format(error=error_html, legacy=legacy_html)
    response = HTMLResponse(html)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response


def _set_auth_cookies(response, *, app, session: AuthSession) -> None:
    response.set_cookie(AUTH_COOKIE, session.token, httponly=True, secure=app.state.secure_cookie, samesite="strict", max_age=SESSION_SECONDS, path="/")
    response.set_cookie(LEGACY_COOKIE, app.state.session_token, httponly=True, secure=app.state.secure_cookie, samesite="strict", max_age=SESSION_SECONDS, path="/")


def _clear_auth_cookies(response) -> None:
    response.delete_cookie(AUTH_COOKIE, path="/")
    response.delete_cookie(LEGACY_COOKIE, path="/")


def _inject_dashboard(response: Any, *, session: AuthSession, workspaces: list[dict[str, Any]]):
    if getattr(response, "status_code", 500) != 200 or not hasattr(response, "body"):
        return response
    try:
        html = response.body.decode("utf-8")
    except Exception:
        return response
    workspace_options = "".join(
        f'<option value="{_escape(item["id"])}"{" selected" if item["id"] == session.workspace_id else ""}>{_escape(item["name"])}</option>'
        for item in workspaces
    )
    controls = f'''<div class="device-control auth370-workspace-control"><label for="auth370WorkspaceSelect">WORKSPACE</label><div class="auth370-workspace-row"><select id="auth370WorkspaceSelect">{workspace_options}</select><button id="auth370WorkspaceAdd" class="icon-button" title="Create workspace" type="button">+</button></div></div><div class="auth370-account"><span>{_escape(session.username)}</span><small>{_escape(session.role)}</small><button id="auth370Logout" class="text-button" type="button">SIGN OUT</button></div>'''
    if "auth370WorkspaceSelect" not in html:
        html = html.replace('<div class="top-actions">', '<div class="top-actions">' + controls, 1)
    if session.role == "administrator" and 'data-view="users370"' not in html:
        html = html.replace("</nav>", '<button class="nav-item" data-view="users370"><span>♙</span>Users</button></nav>', 1)
        marker = '<section id="view-artifacts" class="view">'
        html = html.replace(marker, USERS_VIEW + "\n      " + marker, 1)
    if "auth370WorkspaceDialog" not in html:
        html = html.replace('<div id="toast" class="toast"></div>', WORKSPACE_DIALOG + '\n  <div id="toast" class="toast"></div>', 1)
    if "/static/auth370.css" not in html:
        html = html.replace('<link rel="stylesheet" href="/static/theme360.css">', '<link rel="stylesheet" href="/static/theme360.css">\n  <link rel="stylesheet" href="/static/auth370.css">', 1)
    if "/static/app370.js" not in html:
        html = html.replace("</body>", '  <script src="/static/app370.js" defer></script>\n</body>', 1)
    html = html.replace("3.6.0", "3.7.0")
    response.body = html.encode("utf-8")
    response.headers["content-length"] = str(len(response.body))
    return response


def _json_error(message: str, status: int) -> JSONResponse:
    return JSONResponse(status_code=status, content={"ok": False, "error": message})


def _csrf_token(app: Any, session: AuthSession) -> str:
    key = str(app.state.session_token).encode("utf-8")
    return hmac.new(key, session.token.encode("utf-8"), hashlib.sha256).hexdigest()


def patch_webapp(module: Any) -> None:
    if getattr(module, "_adbgath_370_auth_patched", False):
        return
    original_create_app = module.create_app

    def create_app(*, workspace=None, service=None, remote_token=None, secure_cookie=False):
        app = original_create_app(workspace=workspace, service=service, remote_token=remote_token, secure_cookie=secure_cookie)
        auth = AuthStore()
        proxy = TenantServiceProxy(module.AdbgathService, template_service=service)
        jobs = TenantJobRegistry()
        app.state.auth_store = auth
        app.state.service = proxy
        app.state.job_manager = None
        app.state.legacy_workspace_370 = _legacy_workspace(workspace)

        for route in list(app.router.routes):
            if getattr(route, "path", None) == "/login":
                app.router.routes.remove(route)

        root_route = next(
            route for route in app.routes
            if getattr(route, "path", None) == "/" and "GET" in (getattr(route, "methods", set()) or set())
        )
        original_root = root_route.endpoint

        async def root_370(request: Request):
            if not auth.has_users():
                return _auth_page(SETUP_HTML, legacy=app.state.legacy_workspace_370)
            session = getattr(request.state, "auth370", None)
            if session is None:
                return _auth_page(LOGIN_HTML)
            result = original_root(request)
            if inspect.isawaitable(result):
                result = await result
            return _inject_dashboard(result, session=session, workspaces=auth.list_workspaces(session.user_id))

        root_route.endpoint = root_370
        if hasattr(root_route, "dependant"):
            root_route.dependant.call = root_370

        @app.middleware("http")
        async def auth_context_370(request: Request, call_next):
            path = request.url.path
            public = path.startswith("/static/") or path in {"/", "/auth/setup", "/auth/login", "/favicon.ico"}
            token = request.cookies.get(AUTH_COOKIE)
            session = auth.resolve_session(token)
            request.state.auth370 = session
            if not public and session is None:
                if path.startswith("/api/"):
                    return _json_error("Authentication required.", 401)
                return RedirectResponse(url="/", status_code=302)
            if session is not None and path.startswith("/api/") and request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
                supplied = request.headers.get("x-adbgath-csrf", "")
                if not hmac.compare_digest(supplied, _csrf_token(app, session)):
                    return _json_error("CSRF validation failed. Reload the workspace and retry.", 403)
            ctx = _current_session.set(session)
            try:
                return await call_next(request)
            finally:
                _current_session.reset(ctx)

        @app.post("/auth/setup")
        async def auth_setup(request: Request):
            if auth.has_users():
                return RedirectResponse(url="/", status_code=303)
            form = await request.form()
            username = str(form.get("username", ""))
            password = str(form.get("password", ""))
            confirm = str(form.get("confirm_password", ""))
            if password != confirm:
                return _auth_page(SETUP_HTML, error="Passwords do not match.", legacy=app.state.legacy_workspace_370)
            try:
                user = auth.create_initial_admin(username, password, imported_workspace=app.state.legacy_workspace_370)
                session = auth.create_session(user["id"])
            except ValueError as exc:
                return _auth_page(SETUP_HTML, error=str(exc), legacy=app.state.legacy_workspace_370)
            response = RedirectResponse(url="/", status_code=303)
            _set_auth_cookies(response, app=app, session=session)
            return response

        @app.post("/auth/login")
        async def auth_login(request: Request):
            if not auth.has_users():
                return RedirectResponse(url="/", status_code=303)
            client = request.client.host if request.client else "unknown"
            now = asyncio.get_running_loop().time()
            attempts = [stamp for stamp in app.state.login_attempts.get(client, []) if now - stamp < 60]
            if len(attempts) >= 5:
                return _auth_page(LOGIN_HTML, error="Too many login attempts. Try again in one minute.")
            form = await request.form()
            user = auth.authenticate(str(form.get("username", "")), str(form.get("password", "")))
            if user is None:
                attempts.append(now)
                app.state.login_attempts[client] = attempts
                return _auth_page(LOGIN_HTML, error="Invalid username or password.")
            app.state.login_attempts.pop(client, None)
            session = auth.create_session(user["id"])
            response = RedirectResponse(url="/", status_code=303)
            _set_auth_cookies(response, app=app, session=session)
            return response

        @app.post("/api/auth/logout")
        async def auth_logout(request: Request):
            auth.revoke_session(request.cookies.get(AUTH_COOKIE))
            response = JSONResponse({"ok": True})
            _clear_auth_cookies(response)
            return response

        def require_auth(request: Request) -> AuthSession:
            session = getattr(request.state, "auth370", None)
            if session is None:
                raise HTTPException(status_code=401, detail="Authentication required.")
            return session

        def require_admin(request: Request) -> AuthSession:
            session = require_auth(request)
            if session.role != "administrator":
                raise HTTPException(status_code=403, detail="Administrator role required.")
            return session

        @app.get("/api/auth/me")
        async def auth_me(request: Request):
            session = require_auth(request)
            return {"ok": True, "data": {
                "user": auth.get_user(session.user_id),
                "workspace": {"id": session.workspace_id, "name": session.workspace_name, "path": str(session.workspace_path)},
                "workspaces": auth.list_workspaces(session.user_id),
                "expires_at": session.expires_at,
                "csrf": _csrf_token(app, session),
            }}

        @app.get("/api/auth/users")
        async def auth_users(request: Request):
            require_admin(request)
            return {"ok": True, "data": auth.list_users()}

        @app.post("/api/auth/users")
        async def auth_user_create(request: Request, body: dict[str, Any]):
            require_admin(request)
            try:
                user = auth.create_user(
                    str(body.get("username", "")), str(body.get("password", "")),
                    role=str(body.get("role", "user")), display_name=str(body.get("display_name", "")) or None,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return {"ok": True, "data": user}

        @app.post("/api/auth/users/{user_id}/disabled")
        async def auth_user_disabled(request: Request, user_id: str, body: dict[str, Any]):
            session = require_admin(request)
            if session.user_id == user_id and bool(body.get("disabled", True)):
                raise HTTPException(status_code=409, detail="You cannot disable your current administrator session.")
            try:
                user = auth.set_user_disabled(user_id, bool(body.get("disabled", True)))
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="User not found.") from exc
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return {"ok": True, "data": user}

        @app.post("/api/auth/users/{user_id}/password")
        async def auth_user_password(request: Request, user_id: str, body: dict[str, Any]):
            require_admin(request)
            try:
                auth.reset_password(user_id, str(body.get("password", "")))
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="User not found.") from exc
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return {"ok": True}

        @app.get("/api/workspaces")
        async def workspace_list(request: Request):
            session = require_auth(request)
            return {"ok": True, "data": auth.list_workspaces(session.user_id)}

        @app.post("/api/workspaces")
        async def workspace_create(request: Request, body: dict[str, Any]):
            session = require_auth(request)
            try:
                data = auth.create_workspace(session.user_id, str(body.get("name", "")))
                selected = auth.select_workspace(session.token, data["id"])
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return {"ok": True, "data": {"workspace": data, "active_workspace_id": selected.workspace_id}}

        @app.post("/api/workspaces/{workspace_id}/select")
        async def workspace_select(request: Request, workspace_id: str):
            session = require_auth(request)
            try:
                selected = auth.select_workspace(session.token, workspace_id)
            except PermissionError as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc
            except KeyError as exc:
                raise HTTPException(status_code=401, detail="Session expired.") from exc
            return {"ok": True, "data": {"id": selected.workspace_id, "name": selected.workspace_name, "path": str(selected.workspace_path)}}

        for route in list(app.router.routes):
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", set()) or set()
            if path in {"/api/jobs", "/api/jobs/{job_id}", "/api/jobs/{job_id}/cancel"} and methods:
                app.router.routes.remove(route)

        def job_context(request: Request):
            session = require_auth(request)
            service_instance = proxy.for_path(session.workspace_path)
            return session, service_instance, jobs.for_service(service_instance)

        @app.get("/api/jobs")
        async def jobs_list_370(request: Request):
            _, _, manager = job_context(request)
            return {"ok": True, "data": manager.list()}

        @app.post("/api/jobs")
        async def jobs_create_370(request: Request, body: dict[str, Any]):
            _, service_instance, manager = job_context(request)
            action = body.get("action")
            payload = body.get("payload", {})
            confirmation = body.get("confirmation")
            if not isinstance(action, str) or not action:
                raise HTTPException(status_code=422, detail="action must be a non-empty string")
            if not isinstance(payload, dict):
                raise HTTPException(status_code=422, detail="payload must be a JSON object")
            if confirmation is not None and not isinstance(confirmation, str):
                raise HTTPException(status_code=422, detail="confirmation must be text or null")
            if action not in module.WEB_ACTIONS:
                raise HTTPException(status_code=400, detail="Unsupported action.")
            operation = module.OPERATIONS[action]
            if not operation.long_running:
                raise HTTPException(status_code=400, detail="Only catalogued long-running actions may be persisted as jobs.")
            if operation.destructive and confirmation != "AUTHORIZED":
                raise HTTPException(status_code=409, detail="Destructive action requires AUTHORIZED confirmation.")
            try:
                normalized = module.validate_operation_payload(action, payload)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

            def execute_job(cancel_event, progress):
                if cancel_event.is_set():
                    return {"cancelled": True}
                progress(10)
                adb = service_instance.adb
                cancellation = adb.cancellation(cancel_event) if hasattr(adb, "cancellation") else contextlib.nullcontext()
                with cancellation:
                    result = service_instance.dispatch(action, normalized)
                progress(90)
                return result.to_dict() if hasattr(result, "to_dict") else result

            return {"ok": True, "data": manager.submit(action, normalized, execute_job)}

        @app.get("/api/jobs/{job_id}")
        async def jobs_get_370(request: Request, job_id: str):
            _, _, manager = job_context(request)
            try:
                data = manager.get(job_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Job not found in the active workspace.") from exc
            return {"ok": True, "data": data}

        @app.post("/api/jobs/{job_id}/cancel")
        async def jobs_cancel_370(request: Request, job_id: str):
            _, _, manager = job_context(request)
            try:
                data = manager.cancel(job_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Job not found in the active workspace.") from exc
            return {"ok": True, "data": data}

        for route in list(app.routes):
            path = str(getattr(route, "path", "") or "")
            if not path.startswith("/ws/"):
                continue
            original_ws = route.endpoint

            async def tenant_websocket(*args, _original=original_ws, **kwargs):
                websocket = next((item for item in args if isinstance(item, WebSocket)), kwargs.get("websocket"))
                if websocket is None:
                    raise RuntimeError("WebSocket endpoint did not receive a WebSocket object")
                session = auth.resolve_session(websocket.cookies.get(AUTH_COOKIE))
                if session is None:
                    with contextlib.suppress(Exception):
                        await websocket.close(code=4401)
                    return None
                ctx = _current_session.set(session)
                try:
                    result = _original(*args, **kwargs)
                    if inspect.isawaitable(result):
                        result = await result
                    return result
                except WebSocketDisconnect:
                    return None
                finally:
                    _current_session.reset(ctx)

            route.endpoint = tenant_websocket
            if hasattr(route, "dependant"):
                route.dependant.call = tenant_websocket

        return app

    module.create_app = create_app
    module._adbgath_370_auth_patched = True
