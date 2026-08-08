from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from adbgath.webapp import create_app


def test_remote_first_run_requires_startup_token(monkeypatch, tmp_path: Path, service):
    monkeypatch.setenv("ADBGATH_SERVER_HOME", str(tmp_path / "server-auth"))
    startup_token = "R" * 32
    app = create_app(service=service, remote_token=startup_token, secure_cookie=True)

    with TestClient(app, base_url="https://testserver") as client:
        first = client.get("/")
        assert first.status_code == 200
        assert "Create the first administrator" in first.text
        assert "Remote startup token" in first.text

        denied = client.post(
            "/auth/setup",
            data={
                "username": "admin370",
                "password": "Admin-Password-370!",
                "confirm_password": "Admin-Password-370!",
                "startup_token": "wrong-startup-token-value",
            },
            follow_redirects=False,
        )
        assert denied.status_code == 403
        assert "Invalid remote startup token" in denied.text
        assert app.state.auth_store.has_users() is False

        setup = client.post(
            "/auth/setup",
            data={
                "username": "admin370",
                "password": "Admin-Password-370!",
                "confirm_password": "Admin-Password-370!",
                "startup_token": startup_token,
            },
            follow_redirects=False,
        )
        assert setup.status_code == 303


def test_authenticated_370_user_can_open_remote_dashboard_without_legacy_token_page(monkeypatch, tmp_path: Path, service):
    monkeypatch.setenv("ADBGATH_SERVER_HOME", str(tmp_path / "server-auth"))
    startup_token = "R" * 32
    app = create_app(service=service, remote_token=startup_token, secure_cookie=True)

    with TestClient(app, base_url="https://testserver") as client:
        setup = client.post(
            "/auth/setup",
            data={
                "username": "admin370",
                "password": "Admin-Password-370!",
                "confirm_password": "Admin-Password-370!",
                "startup_token": startup_token,
            },
            follow_redirects=False,
        )
        assert setup.status_code == 303

        dashboard = client.get("/")
        assert dashboard.status_code == 200
        assert "Operations overview" in dashboard.text
        assert "Remote workspace sign in" not in dashboard.text
        assert client.cookies.get("adbgath_session") == app.state.session_token
        assert client.get("/api/bootstrap").status_code == 200


def test_remote_auth_session_and_compatibility_cookie_survive_restart(monkeypatch, tmp_path: Path, service):
    monkeypatch.setenv("ADBGATH_SERVER_HOME", str(tmp_path / "server-auth"))
    startup_token = "R" * 32
    first_app = create_app(service=service, remote_token=startup_token, secure_cookie=True)

    with TestClient(first_app, base_url="https://testserver") as first:
        setup = first.post(
            "/auth/setup",
            data={
                "username": "admin370",
                "password": "Admin-Password-370!",
                "confirm_password": "Admin-Password-370!",
                "startup_token": startup_token,
            },
            follow_redirects=False,
        )
        assert setup.status_code == 303
        first.get("/")
        auth_cookie = first.cookies.get("adbgath_auth")
        legacy_cookie = first.cookies.get("adbgath_session")
        assert auth_cookie and legacy_cookie

    second_app = create_app(service=service, remote_token=startup_token, secure_cookie=True)
    assert second_app.state.session_token == legacy_cookie
    with TestClient(second_app, base_url="https://testserver") as second:
        second.cookies.set("adbgath_auth", auth_cookie, secure=True)
        second.cookies.set("adbgath_session", legacy_cookie, secure=True)
        dashboard = second.get("/")
        assert dashboard.status_code == 200
        assert "Remote workspace sign in" not in dashboard.text
        assert second.get("/api/bootstrap").status_code == 200
