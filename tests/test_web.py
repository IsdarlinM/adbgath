from __future__ import annotations

from fastapi.testclient import TestClient

from adbgath.webapp import create_app


def test_web_bootstrap_and_allowed_action(service):
    client = TestClient(create_app(service=service))
    root = client.get("/")
    assert root.status_code == 200
    assert "ADB<span>GATH" in root.text
    assert "Content-Security-Policy" in root.headers

    bootstrap = client.get("/api/bootstrap")
    assert bootstrap.status_code == 200
    assert bootstrap.json()["version"] == "3.0.0"

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
