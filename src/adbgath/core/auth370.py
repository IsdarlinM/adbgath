from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
import uuid
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,63}$")
_ROLE_VALUES = frozenset({"user", "administrator"})
_SESSION_TTL_SECONDS = 12 * 60 * 60


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _now_ts() -> int:
    return int(time.time())


def default_server_root() -> Path:
    override = os.environ.get("ADBGATH_SERVER_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return (Path(os.environ["LOCALAPPDATA"]) / "adbgath" / "server").resolve()
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return (base / "adbgath" / "server").resolve()


def normalize_username(value: str) -> str:
    username = str(value or "").strip().lower()
    if not _USERNAME_RE.fullmatch(username):
        raise ValueError("Username must be 3-64 characters using lowercase letters, numbers, '.', '_' or '-'.")
    return username


def validate_password(value: str) -> str:
    password = str(value or "")
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters.")
    if len(password) > 1024:
        raise ValueError("Password is too long.")
    return password


def _hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)


def _session_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _safe_workspace_name(value: str) -> str:
    name = " ".join(str(value or "").strip().split())
    if not 1 <= len(name) <= 80:
        raise ValueError("Workspace name must be between 1 and 80 characters.")
    if any(ord(ch) < 32 for ch in name):
        raise ValueError("Workspace name contains unsupported control characters.")
    return name


@dataclass(frozen=True, slots=True)
class AuthSession:
    token: str
    user_id: str
    username: str
    role: str
    workspace_id: str
    workspace_name: str
    workspace_path: Path
    expires_at: int


class AuthStore:
    """Server-level identity/session/workspace registry, separate from user evidence databases."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or default_server_root()).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "server.db"
        self.user_root = self.root / "users"
        self.user_root.mkdir(parents=True, exist_ok=True)
        self._setup_lock = threading.RLock()
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _migrate(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS auth_users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user','administrator')),
                    password_salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL,
                    disabled INTEGER NOT NULL DEFAULT 0 CHECK(disabled IN (0,1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_workspaces (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    is_default INTEGER NOT NULL DEFAULT 0 CHECK(is_default IN (0,1)),
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    UNIQUE(user_id, name COLLATE NOCASE)
                );
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
                    active_workspace_id TEXT NOT NULL REFERENCES auth_workspaces(id) ON DELETE CASCADE,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_auth_workspaces_user ON auth_workspaces(user_id);
                """
            )

    def has_users(self) -> bool:
        with self._connect() as conn:
            return bool(conn.execute("SELECT 1 FROM auth_users LIMIT 1").fetchone())

    def _workspace_path(self, user_id: str, workspace_id: str) -> Path:
        root = (self.user_root / user_id / "workspaces").resolve()
        root.mkdir(parents=True, exist_ok=True)
        path = (root / workspace_id).resolve()
        if root != path and root not in path.parents:
            raise ValueError("Workspace path escaped the user data root.")
        path.mkdir(parents=True, exist_ok=True)
        return path

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
        username = normalize_username(username)
        password = validate_password(password)
        if role not in _ROLE_VALUES:
            raise ValueError("Role must be user or administrator.")
        display = " ".join(str(display_name or username).strip().split())[:100] or username
        user_id = f"usr_{uuid.uuid4().hex[:20]}"
        workspace_id = f"ws_{uuid.uuid4().hex[:20]}"
        workspace_name = _safe_workspace_name(initial_workspace)
        if imported_workspace is None:
            workspace_path = self._workspace_path(user_id, workspace_id)
        else:
            workspace_path = Path(imported_workspace).expanduser().resolve()
            workspace_path.mkdir(parents=True, exist_ok=True)
        salt = secrets.token_bytes(16)
        digest = _hash_password(password, salt)
        stamp = _now_iso()
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO auth_users(id,username,display_name,role,password_salt,password_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                    (user_id, username, display, role, salt, digest, stamp, stamp),
                )
                conn.execute(
                    "INSERT INTO auth_workspaces(id,user_id,name,path,is_default,created_at,last_used_at) VALUES(?,?,?,?,1,?,?)",
                    (workspace_id, user_id, workspace_name, str(workspace_path), stamp, stamp),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"User '{username}' already exists.") from exc
        return self.get_user(user_id)

    def create_initial_admin(self, username: str, password: str, *, imported_workspace: str | Path | None = None) -> dict[str, Any]:
        with self._setup_lock:
            if self.has_users():
                raise ValueError("Initial setup has already been completed.")
            return self.create_user(
                username,
                password,
                role="administrator",
                display_name=username,
                initial_workspace="Default",
                imported_workspace=imported_workspace,
            )

    def get_user(self, user_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id,username,display_name,role,disabled,created_at,updated_at FROM auth_users WHERE id=?",
                (user_id,),
            ).fetchone()
        if not row:
            raise KeyError(user_id)
        return dict(row)

    def find_user(self, username: str) -> dict[str, Any]:
        normalized = normalize_username(username)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id,username,display_name,role,disabled,created_at,updated_at FROM auth_users WHERE username=? COLLATE NOCASE",
                (normalized,),
            ).fetchone()
        if not row:
            raise KeyError(normalized)
        return dict(row)

    def list_users(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id,username,display_name,role,disabled,created_at,updated_at FROM auth_users ORDER BY username"
            ).fetchall()
        return [dict(row) for row in rows]

    def set_user_disabled(self, user_id: str, disabled: bool) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT role FROM auth_users WHERE id=?", (user_id,)).fetchone()
            if not row:
                raise KeyError(user_id)
            if disabled and row["role"] == "administrator":
                enabled_admins = conn.execute(
                    "SELECT COUNT(*) FROM auth_users WHERE role='administrator' AND disabled=0"
                ).fetchone()[0]
                if enabled_admins <= 1:
                    raise ValueError("The last enabled administrator cannot be disabled.")
            conn.execute(
                "UPDATE auth_users SET disabled=?, updated_at=? WHERE id=?",
                (1 if disabled else 0, _now_iso(), user_id),
            )
            if disabled:
                conn.execute("DELETE FROM auth_sessions WHERE user_id=?", (user_id,))
        return self.get_user(user_id)

    def reset_password(self, user_id: str, password: str) -> None:
        password = validate_password(password)
        salt = secrets.token_bytes(16)
        digest = _hash_password(password, salt)
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE auth_users SET password_salt=?, password_hash=?, updated_at=? WHERE id=?",
                (salt, digest, _now_iso(), user_id),
            )
            if cur.rowcount != 1:
                raise KeyError(user_id)
            conn.execute("DELETE FROM auth_sessions WHERE user_id=?", (user_id,))

    def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        try:
            normalized = normalize_username(username)
        except ValueError:
            normalized = "invalid-user"
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM auth_users WHERE username=? COLLATE NOCASE", (normalized,)).fetchone()
        if row:
            salt = bytes(row["password_salt"])
            expected = bytes(row["password_hash"])
        else:
            salt = b"\x00" * 16
            expected = b"\x00" * 32
        supplied = _hash_password(str(password or ""), salt)
        if not row or not hmac.compare_digest(supplied, expected) or bool(row["disabled"]):
            return None
        return {key: row[key] for key in ("id", "username", "display_name", "role", "disabled", "created_at", "updated_at")}

    def list_workspaces(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id,name,path,is_default,created_at,last_used_at FROM auth_workspaces WHERE user_id=? ORDER BY is_default DESC, name COLLATE NOCASE",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_workspace(self, user_id: str, name: str) -> dict[str, Any]:
        name = _safe_workspace_name(name)
        workspace_id = f"ws_{uuid.uuid4().hex[:20]}"
        path = self._workspace_path(user_id, workspace_id)
        stamp = _now_iso()
        try:
            with self._connect() as conn:
                if not conn.execute("SELECT 1 FROM auth_users WHERE id=? AND disabled=0", (user_id,)).fetchone():
                    raise KeyError(user_id)
                conn.execute(
                    "INSERT INTO auth_workspaces(id,user_id,name,path,is_default,created_at,last_used_at) VALUES(?,?,?,?,0,?,?)",
                    (workspace_id, user_id, name, str(path), stamp, stamp),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Workspace '{name}' already exists.") from exc
        return self.get_workspace(user_id, workspace_id)

    def get_workspace(self, user_id: str, workspace_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id,name,path,is_default,created_at,last_used_at FROM auth_workspaces WHERE id=? AND user_id=?",
                (workspace_id, user_id),
            ).fetchone()
        if not row:
            raise KeyError(workspace_id)
        data = dict(row)
        data["path"] = str(Path(data["path"]).expanduser().resolve())
        return data

    def create_session(self, user_id: str, *, ttl_seconds: int = _SESSION_TTL_SECONDS) -> AuthSession:
        with self._connect() as conn:
            user = conn.execute("SELECT * FROM auth_users WHERE id=? AND disabled=0", (user_id,)).fetchone()
            if not user:
                raise KeyError(user_id)
            workspace = conn.execute(
                "SELECT * FROM auth_workspaces WHERE user_id=? ORDER BY is_default DESC, created_at LIMIT 1",
                (user_id,),
            ).fetchone()
            if not workspace:
                raise ValueError("User has no workspace.")
            token = secrets.token_urlsafe(48)
            now = _now_ts()
            expires = now + max(300, min(int(ttl_seconds), 7 * 24 * 3600))
            conn.execute(
                "INSERT INTO auth_sessions(token_hash,user_id,active_workspace_id,created_at,expires_at,last_seen_at) VALUES(?,?,?,?,?,?)",
                (_session_hash(token), user_id, workspace["id"], now, expires, now),
            )
        return AuthSession(
            token=token,
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            workspace_id=workspace["id"],
            workspace_name=workspace["name"],
            workspace_path=Path(workspace["path"]).expanduser().resolve(),
            expires_at=expires,
        )

    def resolve_session(self, token: str | None, *, touch: bool = True) -> AuthSession | None:
        if not token:
            return None
        now = _now_ts()
        digest = _session_hash(token)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT s.user_id,s.active_workspace_id,s.expires_at,u.username,u.role,u.disabled,
                       w.name AS workspace_name,w.path AS workspace_path
                FROM auth_sessions s
                JOIN auth_users u ON u.id=s.user_id
                JOIN auth_workspaces w ON w.id=s.active_workspace_id AND w.user_id=s.user_id
                WHERE s.token_hash=?
                """,
                (digest,),
            ).fetchone()
            if not row or row["disabled"] or int(row["expires_at"]) <= now:
                conn.execute("DELETE FROM auth_sessions WHERE token_hash=?", (digest,))
                return None
            if touch:
                conn.execute("UPDATE auth_sessions SET last_seen_at=? WHERE token_hash=?", (now, digest))
        return AuthSession(
            token=token,
            user_id=row["user_id"],
            username=row["username"],
            role=row["role"],
            workspace_id=row["active_workspace_id"],
            workspace_name=row["workspace_name"],
            workspace_path=Path(row["workspace_path"]).expanduser().resolve(),
            expires_at=int(row["expires_at"]),
        )

    def select_workspace(self, token: str, workspace_id: str) -> AuthSession:
        digest = _session_hash(token)
        with self._connect() as conn:
            session = conn.execute("SELECT user_id FROM auth_sessions WHERE token_hash=?", (digest,)).fetchone()
            if not session:
                raise KeyError("session")
            workspace = conn.execute(
                "SELECT id FROM auth_workspaces WHERE id=? AND user_id=?",
                (workspace_id, session["user_id"]),
            ).fetchone()
            if not workspace:
                raise PermissionError("Workspace does not belong to the authenticated user.")
            stamp = _now_iso()
            conn.execute(
                "UPDATE auth_sessions SET active_workspace_id=?, last_seen_at=? WHERE token_hash=?",
                (workspace_id, _now_ts(), digest),
            )
            conn.execute("UPDATE auth_workspaces SET last_used_at=? WHERE id=?", (stamp, workspace_id))
        resolved = self.resolve_session(token)
        if resolved is None:
            raise KeyError("session")
        return resolved

    def revoke_session(self, token: str | None) -> None:
        if not token:
            return
        with self._connect() as conn:
            conn.execute("DELETE FROM auth_sessions WHERE token_hash=?", (_session_hash(token),))

    def cleanup_sessions(self) -> int:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM auth_sessions WHERE expires_at<=?", (_now_ts(),))
            return int(cur.rowcount or 0)
