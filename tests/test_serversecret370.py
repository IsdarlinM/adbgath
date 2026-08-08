from __future__ import annotations

import base64
from pathlib import Path

from fastapi.testclient import TestClient

from adbgath.webapp import create_app


def test_server_secret_never_becomes_browser_compatibility_cookie(monkeypatch, tmp_path: Path, service):
    root = tmp_path / "server-auth"
    monkeypatch.setenv("ADBGATH_SERVER_HOME", str(root))
    app = create_app(service=service)
    with TestClient(app) as client:
        response = client.post(
            "/auth/setup",
            data={
                "username": "admin370",
                "password": "Admin-Password-370!",
                "confirm_password": "Admin-Password-370!",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        legacy = client.cookies.get("adbgath_session")
        auth_token = client.cookies.get("adbgath_auth")
        assert legacy and auth_token
        secret = (root / "server-secret.key").read_bytes()
        encoded_secret = base64.urlsafe_b64encode(secret).decode("ascii").rstrip("=")
        assert legacy != encoded_secret
        assert legacy != auth_token
        assert app.state.csrf_secret_370 == secret
        me = client.get("/api/auth/me").json()["data"]
        assert len(me["csrf"]) == 64
        assert me["csrf"] not in {legacy, encoded_secret, auth_token}


def test_session_and_csrf_remain_valid_across_web_restart(monkeypatch, tmp_path: Path, service):
    root = tmp_path / "server-auth"
    monkeypatch.setenv("ADBGATH_SERVER_HOME", str(root))
    first_app = create_app(service=service)
    with TestClient(first_app) as first:
        first.post(
            "/auth/setup",
            data={
                "username": "admin370",
                "password": "Admin-Password-370!",
                "confirm_password": "Admin-Password-370!",
            },
            follow_redirects=False,
        )
        auth_cookie = first.cookies.get("adbgath_auth")
        legacy_cookie = first.cookies.get("adbgath_session")
        csrf = first.get("/api/auth/me").json()["data"]["csrf"]

    second_app = create_app(service=service)
    with TestClient(second_app) as second:
        second.cookies.set("adbgath_auth", auth_cookie)
        second.cookies.set("adbgath_session", legacy_cookie)
        me = second.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["data"]["csrf"] == csrf
        created = second.post(
            "/api/workspaces",
            json={"name": "After restart"},
            headers={"X-ADBGATH-CSRF": csrf},
        )
        assert created.status_code == 200
