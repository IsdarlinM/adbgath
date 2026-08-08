from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from adbgath.core.auth370 import AuthStore


def test_auth_store_hashes_passwords_and_session_tokens(tmp_path: Path):
    store = AuthStore(tmp_path / "server")
    password = "Correct-Horse-370!"
    user = store.create_initial_admin("admin370", password)
    assert store.authenticate("admin370", password)["id"] == user["id"]
    assert store.authenticate("admin370", "wrong-password-370") is None

    session = store.create_session(user["id"])
    database = store.db_path.read_bytes()
    assert password.encode() not in database
    assert session.token.encode() not in database

    with sqlite3.connect(store.db_path) as conn:
        row = conn.execute(
            "SELECT length(password_salt), length(password_hash) FROM auth_users WHERE id=?",
            (user["id"],),
        ).fetchone()
        token_hash = conn.execute("SELECT token_hash FROM auth_sessions").fetchone()[0]
    assert row == (16, 32)
    assert len(token_hash) == 64
    assert token_hash != session.token


def test_sessions_can_be_revoked_and_password_reset_revokes_all_sessions(tmp_path: Path):
    store = AuthStore(tmp_path / "server")
    user = store.create_initial_admin("administrator", "Initial-Password-370!")
    first = store.create_session(user["id"])
    second = store.create_session(user["id"])
    assert store.resolve_session(first.token) is not None
    assert store.resolve_session(second.token) is not None

    store.reset_password(user["id"], "Replacement-Password-370!")
    assert store.resolve_session(first.token) is None
    assert store.resolve_session(second.token) is None
    assert store.authenticate("administrator", "Initial-Password-370!") is None
    assert store.authenticate("administrator", "Replacement-Password-370!") is not None


def test_workspace_selection_is_strictly_scoped_to_owner(tmp_path: Path):
    store = AuthStore(tmp_path / "server")
    admin = store.create_initial_admin("admin370", "Admin-Password-370!")
    analyst = store.create_user("analyst370", "Analyst-Password-370!")
    admin_session = store.create_session(admin["id"])
    analyst_session = store.create_session(analyst["id"])
    extra = store.create_workspace(admin["id"], "Private Admin Evidence")

    selected = store.select_workspace(admin_session.token, extra["id"])
    assert selected.workspace_id == extra["id"]
    assert selected.workspace_path.is_dir()

    with pytest.raises(PermissionError):
        store.select_workspace(analyst_session.token, extra["id"])

    analyst_paths = {item["path"] for item in store.list_workspaces(analyst["id"])}
    admin_paths = {item["path"] for item in store.list_workspaces(admin["id"])}
    assert analyst_paths.isdisjoint(admin_paths)


def test_last_enabled_administrator_cannot_be_disabled(tmp_path: Path):
    store = AuthStore(tmp_path / "server")
    admin = store.create_initial_admin("admin370", "Admin-Password-370!")
    with pytest.raises(ValueError, match="last enabled administrator"):
        store.set_user_disabled(admin["id"], True)

    second = store.create_user("backupadmin", "Backup-Admin-370!", role="administrator")
    disabled = store.set_user_disabled(second["id"], True)
    assert disabled["disabled"] == 1


def test_workspace_name_and_username_validation(tmp_path: Path):
    store = AuthStore(tmp_path / "server")
    with pytest.raises(ValueError):
        store.create_initial_admin("x", "Admin-Password-370!")
    admin = store.create_initial_admin("valid-admin", "Admin-Password-370!")
    with pytest.raises(ValueError):
        store.create_workspace(admin["id"], "")
    with pytest.raises(ValueError):
        store.create_user("valid-user", "short")


def test_duplicate_records_do_not_leave_orphan_workspace_directories(tmp_path: Path):
    store = AuthStore(tmp_path / "server")
    admin = store.create_initial_admin("admin370", "Admin-Password-370!")
    store.create_user("analyst370", "Analyst-Password-370!")
    store.create_workspace(admin["id"], "Evidence")

    before = {path for path in store.user_root.rglob("ws_*") if path.is_dir()}
    with pytest.raises(ValueError, match="already exists"):
        store.create_user("analyst370", "Another-Password-370!")
    with pytest.raises(ValueError, match="already exists"):
        store.create_workspace(admin["id"], "Evidence")
    after = {path for path in store.user_root.rglob("ws_*") if path.is_dir()}
    assert after == before


def test_initial_admin_setup_is_serialized_across_store_instances(tmp_path: Path):
    root = tmp_path / "server"
    stores = [AuthStore(root), AuthStore(root)]
    barrier = threading.Barrier(2)
    successes: list[str] = []
    failures: list[Exception] = []

    def create(store: AuthStore, username: str) -> None:
        try:
            barrier.wait(timeout=3)
            user = store.create_initial_admin(username, "Admin-Password-370!")
            successes.append(user["username"])
        except Exception as exc:
            failures.append(exc)

    threads = [
        threading.Thread(target=create, args=(stores[0], "admin-one")),
        threading.Thread(target=create, args=(stores[1], "admin-two")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert len(successes) == 1
    assert len(failures) == 1
    assert "Initial setup has already been completed" in str(failures[0])
    assert len(stores[0].list_users()) == 1
