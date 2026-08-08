from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request


def _session(request: Request):
    session = getattr(request.state, "auth370", None)
    if session is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return session


def _sanitize_payload(module: Any, action: str, payload: Any) -> dict[str, Any]:
    if action not in module.OPERATIONS:
        raise ValueError("Unsupported preset operation.")
    if not isinstance(payload, dict):
        raise ValueError("Preset payload must be a JSON object.")

    fields = {field.name: field for field in module.OPERATIONS[action].fields}
    unknown = sorted(set(payload) - set(fields))
    if unknown:
        raise ValueError(f"Unsupported preset fields for {action}: {', '.join(unknown)}")

    clean: dict[str, Any] = {}
    for name, value in payload.items():
        field = fields[name]
        if field.field_type == "secret":
            continue
        if value is None:
            continue
        if field.field_type == "boolean":
            if not isinstance(value, bool):
                raise ValueError(f"{field.label} must be true or false")
        elif field.field_type == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{field.label} must be a number")
            if field.minimum is not None and value < field.minimum:
                raise ValueError(f"{field.label} must be at least {field.minimum}")
            if field.maximum is not None and value > field.maximum:
                raise ValueError(f"{field.label} must be at most {field.maximum}")
        elif field.field_type == "list":
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"{field.label} must be a list of strings")
            value = [item for item in (entry.strip() for entry in value) if item]
        else:
            if not isinstance(value, str):
                raise ValueError(f"{field.label} must be text")
            value = value.strip()
        if field.choices and value not in field.choices:
            raise ValueError(f"{field.label} must be one of: {', '.join(field.choices)}")
        clean[name] = value
    return clean


def patch_webapp(module: Any) -> None:
    if getattr(module, "_adbgath_371_web_presets_patched", False):
        return
    original_create_app = module.create_app

    def create_app(*, workspace=None, service=None, remote_token=None, secure_cookie=False):
        app = original_create_app(
            workspace=workspace,
            service=service,
            remote_token=remote_token,
            secure_cookie=secure_cookie,
        )
        auth = getattr(app.state, "auth_store", None)
        if auth is None:
            return app

        @app.get("/api/presets")
        async def list_presets(request: Request):
            session = _session(request)
            return {
                "ok": True,
                "data": auth.list_presets(session.user_id, session.workspace_id),
            }

        @app.post("/api/presets")
        async def save_preset(request: Request, body: dict[str, Any]):
            session = _session(request)
            name = str(body.get("name", ""))
            action = str(body.get("action", ""))
            try:
                payload = _sanitize_payload(module, action, body.get("payload", {}))
                saved = auth.upsert_preset(
                    session.user_id,
                    session.workspace_id,
                    name=name,
                    action=action,
                    payload=payload,
                )
            except (ValueError, PermissionError) as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return {"ok": True, "data": saved}

        @app.delete("/api/presets/{preset_id}")
        async def delete_preset(request: Request, preset_id: str):
            session = _session(request)
            try:
                result = auth.delete_preset(session.user_id, session.workspace_id, preset_id)
            except PermissionError as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Preset not found in the active workspace.") from exc
            return {"ok": True, "data": result}

        return app

    module.create_app = create_app
    module._adbgath_371_web_presets_patched = True
