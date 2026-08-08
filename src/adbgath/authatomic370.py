from __future__ import annotations

import shutil
import sqlite3
import uuid
from pathlib import Path
from typing import Any


def patch_auth_atomic(module: Any) -> None:
    """Make user/workspace creation transactional and cross-process safe."""
    if getattr(module.AuthStore, "_adbgath_370_atomic_creation_patched", False):
        return

    def _create_user_impl(
        self,
        username: str,
        password: str,
        *,
        role: str = "user",
        display_name: str | None = None,
        initial_workspace: str = "Default",
        imported_workspace: str | Path | None = None,
        require_empty: bool = False,
    ) -> dict[str, Any]:
        username = module.normalize_username(username)
        password = module.validate_password(password)
        if role not in module._ROLE_VALUES:
            raise ValueError("Role must be user or administrator.")
        display = " ".join(str(display_name or username).strip().split())[:100] or username
        workspace_name = module._safe_workspace_name(initial_workspace)
        user_id = f"usr_{uuid.uuid4().hex[:20]}"
        workspace_id = f"ws_{uuid.uuid4().hex[:20]}"
        salt = module.secrets.token_bytes(16)
        digest = module._hash_password(password, salt)
        stamp = module._now_iso()
        created_workspace: Path | None = None

        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                if require_empty and conn.execute("SELECT 1 FROM auth_users LIMIT 1").fetchone():
                    raise ValueError("Initial setup has already been completed.")
                if conn.execute(
                    "SELECT 1 FROM auth_users WHERE username=? COLLATE NOCASE",
                    (username,),
                ).fetchone():
                    raise ValueError(f"User '{username}' already exists.")

                if imported_workspace is None:
                    workspace_path = self._workspace_path(user_id, workspace_id)
                    created_workspace = Path(workspace_path)
                else:
                    workspace_path = Path(imported_workspace).expanduser().resolve()
                    workspace_path.mkdir(parents=True, exist_ok=True)

                conn.execute(
                    "INSERT INTO auth_users(id,username,display_name,role,password_salt,password_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    (user_id, username, display, role, salt, digest, stamp, stamp),
                )
                conn.execute(
                    "INSERT INTO auth_workspaces(id,user_id,name,path,is_default,created_at,last_used_at) VALUES(?,?,?,?,1,?,?)",
                    (workspace_id, user_id, workspace_name, str(workspace_path), stamp, stamp),
                )
        except sqlite3.IntegrityError as exc:
            if created_workspace is not None:
                shutil.rmtree(created_workspace, ignore_errors=True)
            raise ValueError(f"User '{username}' already exists.") from exc
        except Exception:
            if created_workspace is not None:
                shutil.rmtree(created_workspace, ignore_errors=True)
            raise
        return self.get_user(user_id)

    def create_user(
        self,
        username: str,
        password: str,
        *,
        role: str = "user",
        display_name: str | None = None,
        initial_workspace: str = "Default",
        imported_workspace: str | Path | None = None,
    ) -> dict[str, Any]:
        return _create_user_impl(
            self,
            username,
            password,
            role=role,
            display_name=display_name,
            initial_workspace=initial_workspace,
            imported_workspace=imported_workspace,
        )

    def create_initial_admin(
        self,
        username: str,
        password: str,
        *,
        imported_workspace: str | Path | None = None,
    ) -> dict[str, Any]:
        with self._setup_lock:
            return _create_user_impl(
                self,
                username,
                password,
                role="administrator",
                display_name=username,
                initial_workspace="Default",
                imported_workspace=imported_workspace,
                require_empty=True,
            )

    def create_workspace(self, user_id: str, name: str) -> dict[str, Any]:
        name = module._safe_workspace_name(name)
        workspace_id = f"ws_{uuid.uuid4().hex[:20]}"
        stamp = module._now_iso()
        created_workspace: Path | None = None
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                if not conn.execute(
                    "SELECT 1 FROM auth_users WHERE id=? AND disabled=0",
                    (user_id,),
                ).fetchone():
                    raise KeyError(user_id)
                if conn.execute(
                    "SELECT 1 FROM auth_workspaces WHERE user_id=? AND name=? COLLATE NOCASE",
                    (user_id, name),
                ).fetchone():
                    raise ValueError(f"Workspace '{name}' already exists.")
                workspace_path = self._workspace_path(user_id, workspace_id)
                created_workspace = Path(workspace_path)
                conn.execute(
                    "INSERT INTO auth_workspaces(id,user_id,name,path,is_default,created_at,last_used_at) VALUES(?,?,?,?,0,?,?)",
                    (workspace_id, user_id, name, str(workspace_path), stamp, stamp),
                )
        except sqlite3.IntegrityError as exc:
            if created_workspace is not None:
                shutil.rmtree(created_workspace, ignore_errors=True)
            raise ValueError(f"Workspace '{name}' already exists.") from exc
        except Exception:
            if created_workspace is not None:
                shutil.rmtree(created_workspace, ignore_errors=True)
            raise
        return self.get_workspace(user_id, workspace_id)

    module.AuthStore.create_user = create_user
    module.AuthStore.create_initial_admin = create_initial_admin
    module.AuthStore.create_workspace = create_workspace
    module.AuthStore._adbgath_370_atomic_creation_patched = True
