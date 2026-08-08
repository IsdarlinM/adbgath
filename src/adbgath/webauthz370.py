from __future__ import annotations

import asyncio
import inspect
from typing import Any

from fastapi import HTTPException, Request

ADMIN_ONLY_ACTIONS = frozenset(
    {
        "update",
        "policy",
        "plugins",
        "plugin_keygen",
        "plugin_sign",
        "plugin_publisher",
        "lab_agent_enroll",
        "lab_pool_manage",
        "lab_job_submit",
        "lab_pool_submit",
        "lab_job_cancel",
    }
)


def _session(request: Request):
    session = getattr(request.state, "auth370", None)
    if session is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return session


def _require_action_role(request: Request, action: str) -> None:
    session = _session(request)
    if action in ADMIN_ONLY_ACTIONS and session.role != "administrator":
        raise HTTPException(status_code=403, detail=f"Administrator role required for Web operation: {action}")


def patch_webapp(module: Any) -> None:
    """Bind administrative Web operations to the authenticated server role."""
    if getattr(module, "_adbgath_370_web_authorization_patched", False):
        return
    original_create_app = module.create_app

    def create_app(*, workspace=None, service=None, remote_token=None, secure_cookie=False):
        app = original_create_app(
            workspace=workspace,
            service=service,
            remote_token=remote_token,
            secure_cookie=secure_cookie,
        )

        # Replace the generic execute endpoint so validation and server-role checks
        # are both explicit and produce stable text errors for the browser.
        for route in list(app.router.routes):
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", set()) or set()
            if path == "/api/execute" and "POST" in methods:
                app.router.routes.remove(route)

        @app.post("/api/execute")
        async def execute_370(request: Request, body: dict[str, Any]):
            _session(request)
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
            _require_action_role(request, action)
            operation = module.OPERATIONS[action]
            if operation.destructive and confirmation != "AUTHORIZED":
                raise HTTPException(status_code=409, detail="Destructive action requires AUTHORIZED confirmation.")
            try:
                normalized = module.validate_operation_payload(action, payload)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            result = await asyncio.to_thread(app.state.service.dispatch, action, normalized)
            if hasattr(result, "to_dict"):
                result = result.to_dict()
            return {"ok": True, "data": result}

        # The 3.7 jobs endpoint is already tenant-aware. Wrap its POST endpoint to
        # apply the same server-administration role boundary before queueing work.
        for route in list(app.router.routes):
            if getattr(route, "path", None) != "/api/jobs" or "POST" not in (getattr(route, "methods", set()) or set()):
                continue
            original_job = route.endpoint

            async def authorized_job(request: Request, body: dict[str, Any], _original=original_job):
                action = body.get("action") if isinstance(body, dict) else None
                if isinstance(action, str):
                    _require_action_role(request, action)
                result = _original(request, body)
                if inspect.isawaitable(result):
                    result = await result
                return result

            route.endpoint = authorized_job
            if hasattr(route, "dependant"):
                route.dependant.call = authorized_job
            break

        # Rebind the integrated Distributed Lab role claim to the authenticated
        # Web identity. A normal Web user cannot self-assert the administrator
        # lab role simply by modifying JSON in DevTools.
        for route in list(app.router.routes):
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", set()) or set()
            if path in {"/api/lab/job", "/api/lab/policy/check"} and "POST" in methods:
                app.router.routes.remove(route)

        @app.post("/api/lab/job")
        async def lab_job_370(request: Request, body: dict[str, Any]):
            session = _session(request)
            requested_role = str(body.get("role", "operator"))
            if requested_role == "administrator" and session.role != "administrator":
                raise HTTPException(status_code=403, detail="Administrator Web role required to request administrator Lab authority.")
            try:
                result = app.state.service.lab_job_submit(
                    agent=str(body.get("agent", "")),
                    action=str(body.get("action", "")),
                    payload=dict(body.get("payload") or {}),
                    role=requested_role,
                    actor=f"web:{session.username}",
                    approved=bool(body.get("approved", False)),
                )
            except (ValueError, KeyError, module.AdbgathError) as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return {"ok": True, "data": result}

        @app.post("/api/lab/policy/check")
        async def lab_policy_370(request: Request, body: dict[str, Any]):
            session = _session(request)
            requested_role = str(body.get("role", "viewer"))
            if requested_role == "administrator" and session.role != "administrator":
                raise HTTPException(status_code=403, detail="Administrator Web role required to evaluate administrator Lab authority.")
            result = app.state.service.policy_operation(
                "check",
                role=requested_role,
                action=str(body.get("action", "")),
                approved=bool(body.get("approved", False)),
            )
            return {"ok": True, "data": result}

        return app

    module.create_app = create_app
    module._adbgath_370_web_authorization_patched = True
