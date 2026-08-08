from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from adbgath.webapp import create_app


def test_dashboard_integrates_distributed_lab_and_advanced_wireless(tmp_path: Path):
    app = create_app(workspace=tmp_path)
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'data-view="lab-main"' in html
    assert 'id="view-lab-main"' in html
    assert 'href="/lab"' not in html
    assert 'id="toggleAdvancedWireless"' in html
    assert 'id="advancedWirelessPanel"' in html
    assert 'href="/wireless"' not in html
    assert '/static/lab360.css' in html
    assert '/static/integratedweb360.css' in html
    assert '/static/lab360.js' in html
    assert '/static/integratedweb360.js' in html


def test_legacy_lab_and_wireless_urls_redirect_into_dashboard_views(tmp_path: Path):
    app = create_app(workspace=tmp_path)
    with TestClient(app, follow_redirects=False) as client:
        lab = client.get("/lab")
        wireless = client.get("/wireless")

    assert lab.status_code == 302
    assert lab.headers["location"] == "/?view=lab-main"
    assert wireless.status_code == 302
    assert wireless.headers["location"] == "/?view=wireless-main&advanced=1"


def test_integrated_assets_are_served_and_lab_script_is_isolated(tmp_path: Path):
    app = create_app(workspace=tmp_path)
    with TestClient(app) as client:
        css = client.get("/static/integratedweb360.css")
        js = client.get("/static/integratedweb360.js")
        lab_js = client.get("/static/lab360.js")

    assert css.status_code == 200
    assert "wireless-advanced-panel" in css.text
    assert "integrated-lab-grid" in css.text
    assert js.status_code == 200
    assert 'view === "wireless-main"' in js.text
    assert 'window.adbgathLabRefresh' in lab_js.text
    assert "(() =>" in lab_js.text
    assert "const $ =" not in lab_js.text


def test_main_dashboard_retains_single_shell_navigation(tmp_path: Path):
    app = create_app(workspace=tmp_path)
    with TestClient(app) as client:
        html = client.get("/").text

    assert html.count('class="sidebar"') == 1
    assert html.count('class="topbar"') == 1
    assert "Distributed Lab" in html
    assert "Advanced wireless controls" in html
    assert "Projects & Jobs" in html
