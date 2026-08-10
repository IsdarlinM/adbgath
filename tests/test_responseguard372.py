from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

from adbgath.responseguard372 import HtmlContentLengthGuard
from adbgath.webapp import create_app


def test_html_content_length_guard_repairs_stale_header():
    app = FastAPI()

    @app.get("/")
    async def broken_html():
        response = HTMLResponse("<html><body>short</body></html>")
        response.body = b"<html><body>this body is deliberately longer than the original content length</body></html>"
        return response

    app.add_middleware(HtmlContentLengthGuard)
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert int(response.headers["content-length"]) == len(response.content)
    assert b"deliberately longer" in response.content


def test_authenticated_remote_dashboard_has_exact_content_length(monkeypatch, tmp_path):
    monkeypatch.setenv("ADBGATH_SERVER_HOME", str(tmp_path / "server"))
    token = "r" * 24
    base_url = "http://device.example:50001"
    client = TestClient(
        create_app(
            workspace=tmp_path / "workspace",
            remote_token=token,
            secure_cookie=False,
        ),
        base_url=base_url,
    )

    setup_page = client.get("/")
    assert setup_page.status_code == 200
    assert b"Create the first administrator" in setup_page.content
    assert int(setup_page.headers["content-length"]) == len(setup_page.content)

    initialized = client.post(
        "/auth/setup",
        data={
            "username": "admin",
            "password": "Correct-Horse-Battery-Staple-372",
            "confirm_password": "Correct-Horse-Battery-Staple-372",
            "startup_token": token,
        },
        headers={
            "origin": base_url,
            "sec-fetch-site": "same-origin",
        },
        follow_redirects=False,
    )
    assert initialized.status_code == 303

    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert b"auth370WorkspaceSelect" in dashboard.content
    assert int(dashboard.headers["content-length"]) == len(dashboard.content)


def test_content_length_guard_does_not_buffer_api_routes():
    app = FastAPI()

    @app.get("/api/value")
    async def api_value():
        return {"ok": True}

    app.add_middleware(HtmlContentLengthGuard)
    response = TestClient(app).get("/api/value")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
