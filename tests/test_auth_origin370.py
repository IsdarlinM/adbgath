from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from adbgath.webapp import create_app


def test_cross_origin_first_run_setup_is_rejected(monkeypatch, tmp_path: Path, service):
    monkeypatch.setenv("ADBGATH_SERVER_HOME", str(tmp_path / "server-auth"))
    app = create_app(service=service)
    with TestClient(app) as client:
        response = client.post(
            "/auth/setup",
            data={
                "username": "admin370",
                "password": "Admin-Password-370!",
                "confirm_password": "Admin-Password-370!",
            },
            headers={"Origin": "https://attacker.invalid"},
        )
    assert response.status_code == 403
    assert "Cross-origin" in response.json()["error"]
