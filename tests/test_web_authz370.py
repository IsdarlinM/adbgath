from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from adbgath.webapp import create_app


def _setup_admin(client: TestClient):
    password = "Admin-Password-370!"
    response = client.post(
        "/auth/setup",
        data={"username": "admin370", "password": password, "confirm_password": password},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return client.get("/api/auth/me").json()["data"]


def test_normal_user_cannot_run_server_administration_or_claim_lab_admin(monkeypatch, tmp_path: Path, service):
    monkeypatch.setenv("ADBGATH_SERVER_HOME", str(tmp_path / "server-auth"))
    app = create_app(service=service)
    with TestClient(app) as admin:
        admin_me = _setup_admin(admin)
        admin_headers = {"X-ADBGATH-CSRF": admin_me["csrf"]}
        created = admin.post(
            "/api/auth/users",
            json={"username": "analyst370", "password": "Analyst-Password-370!", "role": "user"},
            headers=admin_headers,
        )
        assert created.status_code == 200

    with TestClient(app) as analyst:
        login = analyst.post(
            "/auth/login",
            data={"username": "analyst370", "password": "Analyst-Password-370!"},
            follow_redirects=False,
        )
        assert login.status_code == 303
        me = analyst.get("/api/auth/me").json()["data"]
        headers = {"X-ADBGATH-CSRF": me["csrf"]}

        update = analyst.post(
            "/api/execute",
            json={"action": "update", "payload": {"mode": "check"}, "confirmation": "AUTHORIZED"},
            headers=headers,
        )
        assert update.status_code == 403
        assert "Administrator role" in update.json()["detail"]

        lab_role = analyst.post(
            "/api/lab/policy/check",
            json={"role": "administrator", "action": "devices", "approved": False},
            headers=headers,
        )
        assert lab_role.status_code == 403


def test_normal_user_can_still_run_workspace_scoped_assessment_job(monkeypatch, tmp_path: Path, service):
    monkeypatch.setenv("ADBGATH_SERVER_HOME", str(tmp_path / "server-auth"))
    app = create_app(service=service)
    with TestClient(app) as admin:
        admin_me = _setup_admin(admin)
        created = admin.post(
            "/api/auth/users",
            json={"username": "analyst370", "password": "Analyst-Password-370!", "role": "user"},
            headers={"X-ADBGATH-CSRF": admin_me["csrf"]},
        )
        assert created.status_code == 200

    with TestClient(app) as analyst:
        analyst.post(
            "/auth/login",
            data={"username": "analyst370", "password": "Analyst-Password-370!"},
            follow_redirects=False,
        )
        me = analyst.get("/api/auth/me").json()["data"]
        response = analyst.post(
            "/api/jobs",
            json={"action": "security", "payload": {"device": "emulator-5554", "user": "current"}, "confirmation": None},
            headers={"X-ADBGATH-CSRF": me["csrf"]},
        )
        assert response.status_code == 200, response.text
