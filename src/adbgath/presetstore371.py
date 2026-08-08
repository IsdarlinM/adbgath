from __future__ import annotations

import json
import uuid
from typing import Any


def patch_auth_presets(module: Any) -> None:
    """Add per-user/per-workspace preset records to the server identity database."""
    if getattr(module.AuthStore, "_adbgath_371_presets_patched", False):
        return

    original_ensure_schema = module.AuthStore._ensure_schema

    def ensure_schema(self) -> None:
        original_ensure_schema(self)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS auth_presets (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    name TEXT NOT NULL COLLATE NOCASE,
                    action TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, workspace_id, name),
                    FOREIGN KEY(user_id) REFERENCES auth_users(id) ON DELETE CASCADE,
                    FOREIGN KEY(workspace_id) REFERENCES auth_workspaces(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_auth_presets_scope
                    ON auth_presets(user_id, workspace_id, updated_at DESC);
                """
            )

    def _scope_exists(self, conn, user_id: str, workspace_id: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM auth_workspaces WHERE id=? AND user_id=?",
            (workspace_id, user_id),
        ).fetchone()
        return row is not None

    def list_presets(self, user_id: str, workspace_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if not _scope_exists(self, conn, user_id, workspace_id):
                raise PermissionError("Workspace does not belong to the authenticated user.")
            rows = conn.execute(
                """
                SELECT id, name, action, payload_json, created_at, updated_at
                FROM auth_presets
                WHERE user_id=? AND workspace_id=?
                ORDER BY updated_at DESC, name COLLATE NOCASE
                LIMIT 100
                """,
                (user_id, workspace_id),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, json.JSONDecodeError):
                payload = {}
            result.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "action": row["action"],
                    "payload": payload if isinstance(payload, dict) else {},
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        return result

    def upsert_preset(
        self,
        user_id: str,
        workspace_id: str,
        *,
        name: str,
        action: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        clean_name = " ".join(str(name).strip().split())[:80]
        if not clean_name:
            raise ValueError("Preset name is required.")
        stamp = module._now_iso()
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if not _scope_exists(self, conn, user_id, workspace_id):
                raise PermissionError("Workspace does not belong to the authenticated user.")
            existing = conn.execute(
                "SELECT id, created_at FROM auth_presets WHERE user_id=? AND workspace_id=? AND name=? COLLATE NOCASE",
                (user_id, workspace_id, clean_name),
            ).fetchone()
            preset_id = existing["id"] if existing else f"pre_{uuid.uuid4().hex[:20]}"
            created_at = existing["created_at"] if existing else stamp
            if existing:
                conn.execute(
                    """
                    UPDATE auth_presets
                    SET name=?, action=?, payload_json=?, updated_at=?
                    WHERE id=? AND user_id=? AND workspace_id=?
                    """,
                    (clean_name, action, serialized, stamp, preset_id, user_id, workspace_id),
                )
            else:
                count = conn.execute(
                    "SELECT COUNT(*) FROM auth_presets WHERE user_id=? AND workspace_id=?",
                    (user_id, workspace_id),
                ).fetchone()[0]
                if int(count) >= 100:
                    raise ValueError("A workspace can contain at most 100 saved presets.")
                conn.execute(
                    """
                    INSERT INTO auth_presets(id,user_id,workspace_id,name,action,payload_json,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (preset_id, user_id, workspace_id, clean_name, action, serialized, created_at, stamp),
                )
        return next(item for item in self.list_presets(user_id, workspace_id) if item["id"] == preset_id)

    def delete_preset(self, user_id: str, workspace_id: str, preset_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if not _scope_exists(self, conn, user_id, workspace_id):
                raise PermissionError("Workspace does not belong to the authenticated user.")
            row = conn.execute(
                "SELECT id, name FROM auth_presets WHERE id=? AND user_id=? AND workspace_id=?",
                (preset_id, user_id, workspace_id),
            ).fetchone()
            if row is None:
                raise KeyError(preset_id)
            conn.execute(
                "DELETE FROM auth_presets WHERE id=? AND user_id=? AND workspace_id=?",
                (preset_id, user_id, workspace_id),
            )
        return {"id": row["id"], "name": row["name"], "deleted": True}

    module.AuthStore._ensure_schema = ensure_schema
    module.AuthStore.list_presets = list_presets
    module.AuthStore.upsert_preset = upsert_preset
    module.AuthStore.delete_preset = delete_preset
    module.AuthStore._adbgath_371_presets_patched = True
