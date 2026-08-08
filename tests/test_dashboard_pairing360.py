from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from adbgath.webapp import create_app


def test_main_dashboard_exposes_both_pairing_workflows(tmp_path: Path):
    app = create_app(workspace=tmp_path)
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        html = response.text

        assert 'data-view="wireless-main"' in html
        assert 'id="view-wireless-main"' in html
        assert "PAIR WITHOUT CODE" in html
        assert "QR pairing" in html
        assert "PAIR WITH CODE" in html
        assert "Six-digit code" in html
        assert 'id="dashPairCode" type="password"' in html
        assert 'id="dashQrAuthorized" type="checkbox"' in html
        assert 'id="dashPairAuthorized" type="checkbox"' in html
        assert "/static/dashboardpairing360.css" in html
        assert "/static/dashboardpairing360.js" in html


def test_dashboard_pairing_assets_are_served(tmp_path: Path):
    app = create_app(workspace=tmp_path)
    with TestClient(app) as client:
        css = client.get("/static/dashboardpairing360.css")
        js = client.get("/static/dashboardpairing360.js")

    assert css.status_code == 200
    assert "wireless-main-grid" in css.text
    assert js.status_code == 200
    assert 'execute("wireless_pair"' in js.text
    assert 'request("/api/wireless/qr"' in js.text
    assert 'codeInput.value = ""' in js.text


def test_dashboard_reuses_existing_pairing_endpoints_without_secret_in_markup(tmp_path: Path):
    app = create_app(workspace=tmp_path)
    with TestClient(app) as client:
        html = client.get("/").text

    # The UI contains only empty input fields/placeholders. Pairing secrets are
    # supplied at runtime and are never embedded into the generated dashboard.
    assert "pairing_code" not in html
    assert "WIFI:T:ADB" not in html
    assert "000000" in html  # placeholder only
