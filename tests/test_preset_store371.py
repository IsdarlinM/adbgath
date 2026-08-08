from __future__ import annotations

from pathlib import Path

import pytest

from adbgath.core.auth370 import AuthStore


def test_presets_are_isolated_by_user_and_workspace(tmp_path: Path):
    store = AuthStore(tmp_path / "server")
    admin = store.create_initial_admin("admin371", "Admin-Password-371!")
    analyst = store.create_user("analyst371", "Analyst-Password-371!")
    admin_ws = store.list_workspaces(admin["id"])[0]["id"]
    analyst_ws = store.list_workspaces(analyst["id"])[0]["id"]

    left = store.upsert_preset(
        admin["id"], admin_ws,
        name="Posture audit", action="security", payload={"output": "admin.json"},
    )
    right = store.upsert_preset(
        analyst["id"], analyst_ws,
        name="Posture audit", action="security", payload={"output": "analyst.json"},
    )

    assert left["id"] != right["id"]
    assert store.list_presets(admin["id"], admin_ws)[0]["payload"] == {"output": "admin.json"}
    assert store.list_presets(analyst["id"], analyst_ws)[0]["payload"] == {"output": "analyst.json"}

    replaced = store.upsert_preset(
        admin["id"], admin_ws,
        name="posture AUDIT", action="security", payload={"output": "updated.json"},
    )
    assert replaced["id"] == left["id"]
    assert len(store.list_presets(admin["id"], admin_ws)) == 1
    assert replaced["payload"] == {"output": "updated.json"}

    with pytest.raises(KeyError):
        store.delete_preset(analyst["id"], analyst_ws, left["id"])
    assert store.list_presets(admin["id"], admin_ws)[0]["id"] == left["id"]
