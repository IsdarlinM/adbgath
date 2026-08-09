from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import adbgath
from adbgath.cli import build_parser
from adbgath.core.auth370 import AuthStore
from adbgath.errors import ValidationError
from adbgath.selfupdatesafety372 import _candidate_preflight
from adbgath.webapp import create_app


def _walk_help(parser: argparse.ArgumentParser, prefix: tuple[str, ...] = ()):
    yield prefix, parser.format_help()
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for name, child in action.choices.items():
            yield from _walk_help(child, (*prefix, name))


def _wait_job(client: TestClient, job_id: str, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200, response.text
        job = response.json()["data"]
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not reach a terminal state")


def test_372_version_and_import_chain_are_healthy():
    assert adbgath.__version__ == "3.7.2"
    store = AuthStore()
    with store._connect() as conn:
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='auth_presets'"
        ).fetchone()


def test_every_cli_help_path_formats_recursively_and_update_modes_parse():
    parser = build_parser()
    paths = list(_walk_help(parser))
    assert len(paths) >= 90
    seen: set[tuple[str, ...]] = set()
    for path, help_text in paths:
        assert path not in seen
        seen.add(path)
        assert "usage:" in help_text.lower(), " ".join(path) or "<root>"
    assert parser.parse_args(["update"]).mode == "auto"
    assert parser.parse_args(["update", "force"]).mode == "force"
    assert parser.parse_args(["update", "check"]).mode == "check"
    assert parser.parse_args(["wireless", "auto-connect"]).wireless_mode == "auto-connect"
    assert parser.parse_args(["web-user", "list"]).web_user_mode == "list"


def test_candidate_preflight_accepts_repo_package_and_rejects_broken_candidate(tmp_path: Path):
    source_root = Path(__file__).parents[1] / "src"
    healthy = _candidate_preflight(source_root)
    assert healthy["version"] == "3.7.2"
    assert healthy["routes"] > 0

    broken = tmp_path / "broken-stage"
    package = broken / "adbgath"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("raise RuntimeError('broken-candidate-372')\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="installed package was not modified"):
        _candidate_preflight(broken)


def test_presets_schema_and_scope_work_after_real_authstore_constructor(tmp_path: Path):
    store = AuthStore(tmp_path / "server")
    admin = store.create_initial_admin("admin372", "Admin-Password-372!")
    workspace = store.list_workspaces(admin["id"])[0]
    preset = store.upsert_preset(
        admin["id"], workspace["id"], name="Security posture", action="security", payload={"user": "current"}
    )
    assert store.list_presets(admin["id"], workspace["id"])[0]["id"] == preset["id"]
    assert store.delete_preset(admin["id"], workspace["id"], preset["id"])["deleted"] is True


def test_authenticated_web_surface_assets_and_long_running_jobs(service):
    app = create_app(service=service)
    with TestClient(app) as client:
        dashboard = client.get("/")
        assert dashboard.status_code == 200
        assert "3.7.2" in dashboard.text
        assert "Distributed Lab" in dashboard.text
        assert "Wireless" in dashboard.text
        assert "auth370WorkspaceSelect" in dashboard.text

        # Every API method/path pair must be unique after the compatibility patches.
        seen: set[tuple[str, str]] = set()
        for route in app.routes:
            path = str(getattr(route, "path", ""))
            if not path.startswith("/api/"):
                continue
            for method in (getattr(route, "methods", set()) or set()):
                pair = (method, path)
                assert pair not in seen, f"duplicate API route: {pair}"
                seen.add(pair)

        operations = client.get("/api/operations")
        assert operations.status_code == 200
        names = {item["name"] for item in operations.json()["data"]}
        for required in {"security", "mastg", "wireless_pair", "wireless_connect", "lab_status"}:
            assert required in names

        assert client.get("/api/bootstrap").status_code == 200
        assert client.get("/api/workspaces").status_code == 200
        assert client.get("/api/presets").status_code == 200

        for action in ("security", "mastg"):
            response = client.post(
                "/api/jobs",
                json={
                    "action": action,
                    "payload": {"device": "emulator-5554", "user": "current"},
                    "confirmation": None,
                },
            )
            assert response.status_code == 200, response.text
            job = _wait_job(client, response.json()["data"]["id"])
            assert job["status"] == "completed", job

        assets = set(re.findall(r"(?:src|href)=[\"'](/static/[^\"']+)[\"']", dashboard.text))
        assert assets
        for asset in sorted(assets):
            response = client.get(asset)
            assert response.status_code == 200, asset
