from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from adbgath.core.auth370 import AuthStore, _session_hash


def test_expired_session_cannot_mutate_active_workspace_or_last_used(tmp_path: Path):
    store = AuthStore(tmp_path / "server")
    admin = store.create_initial_admin("admin370", "Admin-Password-370!")
    session = store.create_session(admin["id"])
    original = session.workspace_id
    extra = store.create_workspace(admin["id"], "Extra")

    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE auth_sessions SET expires_at=0 WHERE token_hash=?",
            (_session_hash(session.token),),
        )
        before = conn.execute(
            "SELECT last_used_at FROM auth_workspaces WHERE id=?",
            (extra["id"],),
        ).fetchone()[0]

    with pytest.raises(KeyError, match="session"):
        store.select_workspace(session.token, extra["id"])

    with sqlite3.connect(store.db_path) as conn:
        assert conn.execute(
            "SELECT active_workspace_id FROM auth_sessions WHERE token_hash=?",
            (_session_hash(session.token),),
        ).fetchone() is None
        after = conn.execute(
            "SELECT last_used_at FROM auth_workspaces WHERE id=?",
            (extra["id"],),
        ).fetchone()[0]

    assert after == before
    assert original != extra["id"]
