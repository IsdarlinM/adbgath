from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from adbgath.webapp import create_app


def setup_admin(client: TestClient, *, username: str = "admin370", password: str = "Admin-Password-370!"):
    first = client.get("/")
    assert first.status_code == 200
    assert "Create the first administrator" in first.text
    created = client.post(
        "/auth/setup",
        data={"username": username, "password": password, "confirm_password": password},
        follow_redirects=False,
    )
    assert created.status_code == 303
    assert "adbgath_auth" in created.headers.get("set-cookie", "")
    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert 'id="auth370WorkspaceSelect"' in dashboard.text
    assert 'data-view="users370"' in dashboard.text
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    return me.json()["data"]


def csrf_headers(client: TestClient) -> dict[str, str]:
    data = client.get("/api/auth/me").json()["data"]
    return {"X-ADBGATH-CSRF": data["csrf"]}


def wait_job(client: TestClient, job_id: str, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        job = response.json()["data"]
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish")


def test_web_requires_authentication_and_csrf(monkeypatch, tmp_path: Path, service):
    monkeypatch.setenv("ADBGATH_SERVER_HOME", str(tmp_path / "server-auth"))
    app = create_app(service=service)
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/bootstrap").status_code == 401
        setup_admin(anonymous)
        denied = anonymous.post("/api/workspaces", json={"name": "No CSRF"})
        assert denied.status_code == 403
        assert "CSRF" in denied.json()["error"]
        allowed = anonymous.post(
            "/api/workspaces",
            json={"name": "Mobile Research"},
            headers=csrf_headers(anonymous),
        )
        assert allowed.status_code == 200
        current = anonymous.get("/api/auth/me").json()["data"]
        assert current["workspace"]["name"] == "Mobile Research"
        bootstrap = anonymous.get("/api/bootstrap")
        assert bootstrap.status_code == 200
        assert Path(bootstrap.json()["workspace"]).resolve() == Path(current["workspace"]["path"]).resolve()


def test_security_and_mastg_buttons_job_contract_no_longer_returns_422(monkeypatch, tmp_path: Path, service):
    monkeypatch.setenv("ADBGATH_SERVER_HOME", str(tmp_path / "server-auth"))
    app = create_app(service=service)
    with TestClient(app) as client:
        setup_admin(client)
        headers = csrf_headers(client)
        for action in ("security", "mastg"):
            response = client.post(
                "/api/jobs",
                json={"action": action, "payload": {"device": "emulator-5554", "user": "current"}, "confirmation": None},
                headers=headers,
            )
            assert response.status_code == 200, response.text
            job = wait_job(client, response.json()["data"]["id"])
            assert job["status"] == "completed", job


def test_users_and_jobs_are_isolated_between_accounts(monkeypatch, tmp_path: Path, service):
    monkeypatch.setenv("ADBGATH_SERVER_HOME", str(tmp_path / "server-auth"))
    app = create_app(service=service)
    with TestClient(app) as admin_client:
        admin_me = setup_admin(admin_client)
        admin_headers = csrf_headers(admin_client)
        create_user = admin_client.post(
            "/api/auth/users",
            json={
                "username": "analyst370",
                "display_name": "Analyst 370",
                "role": "user",
                "password": "Analyst-Password-370!",
            },
            headers=admin_headers,
        )
        assert create_user.status_code == 200, create_user.text
        admin_job = admin_client.post(
            "/api/jobs",
            json={"action": "security", "payload": {"device": "emulator-5554", "user": "current"}, "confirmation": None},
            headers=admin_headers,
        )
        assert admin_job.status_code == 200
        admin_job_id = admin_job.json()["data"]["id"]
        admin_workspace_id = admin_me["workspace"]["id"]

        with TestClient(app) as analyst:
            login = analyst.post(
                "/auth/login",
                data={"username": "analyst370", "password": "Analyst-Password-370!"},
                follow_redirects=False,
            )
            assert login.status_code == 303
            analyst_me = analyst.get("/api/auth/me").json()["data"]
            analyst_headers = {"X-ADBGATH-CSRF": analyst_me["csrf"]}
            assert analyst_me["user"]["role"] == "user"
            assert analyst_me["workspace"]["path"] != admin_me["workspace"]["path"]
            assert analyst.get("/api/auth/users").status_code == 403
            cross = analyst.post(
                f"/api/workspaces/{admin_workspace_id}/select",
                json={},
                headers=analyst_headers,
            )
            assert cross.status_code == 403
            assert analyst.get(f"/api/jobs/{admin_job_id}").status_code == 404

            analyst_job = analyst.post(
                "/api/jobs",
                json={"action": "mastg", "payload": {"device": "emulator-5554", "user": "current"}, "confirmation": None},
                headers=analyst_headers,
            )
            assert analyst_job.status_code == 200, analyst_job.text
            assert wait_job(analyst, analyst_job.json()["data"]["id"])["status"] == "completed"


def test_logout_revokes_session(monkeypatch, tmp_path: Path, service):
    monkeypatch.setenv("ADBGATH_SERVER_HOME", str(tmp_path / "server-auth"))
    app = create_app(service=service)
    with TestClient(app) as client:
        setup_admin(client)
        response = client.post("/api/auth/logout", json={}, headers=csrf_headers(client))
        assert response.status_code == 200
        assert client.get("/api/auth/me").status_code == 401


def test_370_frontend_contains_readable_422_and_csrf_compatibility_layer():
    root = Path(__file__).parents[1] / "src" / "adbgath" / "web" / "static"
    script = (root / "app370.js").read_text(encoding="utf-8")
    assert "readableDetail" in script
    assert "[object Object]" not in script
    assert "X-ADBGATH-CSRF" in script
    assert "window.fetch = authenticatedFetch" in script
    assert 'submitJob370(action' in script
