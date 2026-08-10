from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from adbgath import cli, webapp
from adbgath.errors import ValidationError
from adbgath.remotesetup370 import patch_webapp as patch_remote_setup
from adbgath.webapp import create_app
from adbgath.websocketcleanup360 import patch_webapp as patch_ws_cleanup
from adbgath.websocketexpiry370 import patch_webapp as patch_ws_expiry


class _AuthStub:
    def has_users(self):
        return False

    def resolve_session(self, *args, **kwargs):
        return None


def _mounted_app(tmp_path, *, mount_path="/static"):
    static = tmp_path / "static"
    static.mkdir(parents=True, exist_ok=True)
    app = FastAPI()
    app.state.auth_store = _AuthStub()
    app.state.remote_token = "r" * 24
    app.state.login_attempts = {}
    app.state.legacy_workspace_370 = None
    app.mount(mount_path, StaticFiles(directory=static), name="assets")
    return app


def test_remote_setup_ignores_starlette_mount_without_endpoint(tmp_path):
    app = _mounted_app(tmp_path)
    mount = next(route for route in app.routes if getattr(route, "path", None) == "/static")
    assert not hasattr(mount, "endpoint")

    module = SimpleNamespace(create_app=lambda **kwargs: app)
    patch_remote_setup(module)
    assert module.create_app(remote_token="r" * 24) is app


def test_websocket_wrappers_ignore_non_endpoint_mounts(tmp_path):
    cleanup_app = _mounted_app(tmp_path / "cleanup", mount_path="/ws/assets")
    cleanup_module = SimpleNamespace(create_app=lambda **kwargs: cleanup_app, LOGGER=None)
    patch_ws_cleanup(cleanup_module)
    assert cleanup_module.create_app() is cleanup_app

    expiry_app = _mounted_app(tmp_path / "expiry", mount_path="/ws/assets")
    expiry_module = SimpleNamespace(create_app=lambda **kwargs: expiry_app)
    patch_ws_expiry(expiry_module)
    assert expiry_module.create_app() is expiry_app


@pytest.mark.parametrize("secure_cookie", [False, True])
def test_final_remote_app_constructs_with_static_mount(monkeypatch, tmp_path, secure_cookie):
    monkeypatch.setenv("ADBGATH_SERVER_HOME", str(tmp_path / "server"))
    app = create_app(
        workspace=tmp_path / "workspace",
        remote_token="r" * 24,
        secure_cookie=secure_cookie,
    )
    assert app.title == "adbgath Web"
    assert any(getattr(route, "path", None) == "/static" for route in app.routes)
    assert any(getattr(route, "path", None) == "/" for route in app.routes)


@pytest.mark.parametrize("insecure_http", [False, True])
def test_real_remote_serve_builds_full_app_without_mount_crash(monkeypatch, tmp_path, insecure_http):
    captured = {}

    def fake_run(app, **kwargs):
        captured["app"] = app
        captured["kwargs"] = kwargs

    import uvicorn

    monkeypatch.setenv("ADBGATH_SERVER_HOME", str(tmp_path / "server"))
    monkeypatch.setattr(uvicorn, "run", fake_run)
    webapp.serve(
        host="0.0.0.0",
        port=50001,
        open_browser=False,
        workspace=tmp_path / "workspace",
        remote_token="r" * 24,
        insecure_http=insecure_http,
        tls_dir=tmp_path / "tls",
    )

    app = captured["app"]
    assert app.title == "adbgath Web"
    assert any(getattr(route, "path", None) == "/static" for route in app.routes)
    if insecure_http:
        assert captured["kwargs"]["ssl_certfile"] is None
        assert app.state.secure_cookie is False
    else:
        assert captured["kwargs"]["ssl_certfile"]
        assert captured["kwargs"]["ssl_keyfile"]
        assert app.state.secure_cookie is True


def test_malformed_lab_nested_payload_returns_422(service):
    client = TestClient(create_app(service=service))
    client.get("/")
    response = client.post(
        "/api/lab/job",
        json={
            "agent": "missing-agent",
            "action": "devices",
            "payload": ["not", "an", "object"],
            "role": "viewer",
        },
    )
    assert response.status_code == 422
    body = response.json()
    message = str(body.get("error") or body.get("detail") or "")
    assert "payload must be a JSON object" in message


def test_cli_unexpected_exception_is_contained_without_traceback(monkeypatch, capsys):
    def explode(_args):
        raise AttributeError("simulated route bug")

    monkeypatch.setattr(cli, "run", explode)
    rc = cli.main(["--no-banner", "devices"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "Unexpected internal error (AttributeError): simulated route bug" in captured.err
    assert "Traceback" not in captured.err
    assert "--verbose" in captured.err


def test_cli_expected_os_error_is_contained(monkeypatch, capsys):
    def explode(_args):
        raise OSError("simulated filesystem failure")

    monkeypatch.setattr(cli, "run", explode)
    rc = cli.main(["--no-banner", "devices"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "Error: simulated filesystem failure" in captured.err
    assert "Traceback" not in captured.err


def test_inventory_numeric_errors_are_validation_errors(service):
    with pytest.raises(ValidationError, match="Inventory list limit"):
        service.inventory_list(limit="not-a-number")

    iterator = service.inventory_watch("emulator-5554", interval="bad", duration=10)
    with pytest.raises(ValidationError, match="Inventory watch interval"):
        next(iterator)


def test_inventory_diff_rejects_missing_identifiers(service):
    with pytest.raises(ValidationError, match="requires both before and after"):
        service.inventory_diff("", "missing")


def test_wireless_qr_numeric_errors_are_validation_errors(service):
    with pytest.raises(ValidationError, match="QR lifetime"):
        service.wireless_qr_create(ttl_seconds="invalid")
