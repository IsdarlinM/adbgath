from __future__ import annotations

from fastapi.testclient import TestClient

from adbgath.service import WEB_ACTIONS
from adbgath.webapp import create_app


def test_web_bootstrap_and_allowed_action(service):
    client = TestClient(create_app(service=service))
    root = client.get("/")
    assert root.status_code == 200
    assert "ADB-Gath" in root.text
    assert "Defensive ADB Toolkit" in root.text
    assert "Content-Security-Policy" in root.headers

    bootstrap = client.get("/api/bootstrap")
    assert bootstrap.status_code == 200
    body = bootstrap.json()
    assert body["version"] == "3.2.9"
    assert {item["name"] for item in body["operations"]} == set(WEB_ACTIONS)

    result = client.post("/api/execute", json={"action": "packages", "payload": {}})
    assert result.status_code == 200
    assert result.json()["data"][0]["name"] == "com.example.app"


def test_web_rejects_destructive_action_without_confirmation(service):
    client = TestClient(create_app(service=service))
    client.get("/")
    response = client.post(
        "/api/execute",
        json={"action": "uninstall", "payload": {"packages": ["com.example.app"], "user": "0"}},
    )
    assert response.status_code == 409


def test_web_rejects_unknown_action(service):
    client = TestClient(create_app(service=service))
    client.get("/")
    response = client.post("/api/execute", json={"action": "shell", "payload": {}})
    assert response.status_code == 400


def test_web_bootstrap_starts_without_adb(monkeypatch, tmp_path):
    from adbgath.adb import AdbClient
    from adbgath.errors import DependencyError

    def missing_adb(_explicit):
        raise DependencyError("ADB intentionally unavailable for test.")

    monkeypatch.setattr(AdbClient, "_locate_adb", staticmethod(missing_adb))
    client = TestClient(create_app(workspace=tmp_path / "workspace"))
    assert client.get("/").status_code == 200

    response = client.get("/api/bootstrap")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["devices"] == []
    assert body["doctor"]["ok"] is False
    checks = {item["name"]: item for item in body["doctor"]["checks"]}
    assert checks["adb"]["ok"] is False
    assert checks["adb-version"]["ok"] is False

    devices = client.get("/api/devices")
    assert devices.status_code == 400
    assert "ADB intentionally unavailable" in devices.json()["error"]
