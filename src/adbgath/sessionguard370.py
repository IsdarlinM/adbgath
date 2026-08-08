from __future__ import annotations

from typing import Any


def patch_auth_sessions(module: Any) -> None:
    """Reject expired/disabled sessions before workspace selection mutates state."""
    if getattr(module.AuthStore, "_adbgath_370_session_guard_patched", False):
        return

    def select_workspace(self, token: str, workspace_id: str):
        digest = module._session_hash(token)
        now = module._now_ts()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            session = conn.execute(
                """
                SELECT s.user_id, s.expires_at, u.disabled
                FROM auth_sessions s
                JOIN auth_users u ON u.id=s.user_id
                WHERE s.token_hash=?
                """,
                (digest,),
            ).fetchone()
            if not session or bool(session["disabled"]) or int(session["expires_at"]) <= now:
                conn.execute("DELETE FROM auth_sessions WHERE token_hash=?", (digest,))
                conn.commit()
                raise KeyError("session")
            workspace = conn.execute(
                "SELECT id FROM auth_workspaces WHERE id=? AND user_id=?",
                (workspace_id, session["user_id"]),
            ).fetchone()
            if not workspace:
                raise PermissionError("Workspace does not belong to the authenticated user.")
            stamp = module._now_iso()
            conn.execute(
                "UPDATE auth_sessions SET active_workspace_id=?, last_seen_at=? WHERE token_hash=?",
                (workspace_id, now, digest),
            )
            conn.execute("UPDATE auth_workspaces SET last_used_at=? WHERE id=?", (stamp, workspace_id))
        resolved = self.resolve_session(token)
        if resolved is None:
            raise KeyError("session")
        return resolved

    module.AuthStore.select_workspace = select_workspace
    module.AuthStore._adbgath_370_session_guard_patched = True
