from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from adbgath.webapp import create_app


def _assert_theme_is_last_stylesheet(html: str) -> None:
    marker = '/static/theme360.css'
    assert marker in html
    assert html.count(marker) == 1
    theme_index = html.index(marker)
    last_stylesheet = html.rfind('rel="stylesheet"')
    assert theme_index >= last_stylesheet


def test_all_first_party_web_pages_load_unified_theme(tmp_path: Path):
    app = create_app(workspace=tmp_path)
    with TestClient(app) as client:
        dashboard = client.get('/')
        wireless = client.get('/wireless')
        lab = client.get('/lab')

    assert dashboard.status_code == 200
    assert wireless.status_code == 200
    assert lab.status_code == 200
    _assert_theme_is_last_stylesheet(dashboard.text)
    _assert_theme_is_last_stylesheet(wireless.text)
    _assert_theme_is_last_stylesheet(lab.text)


def test_unified_theme_uses_dashboard_green_tokens_and_wraps_environment_values(tmp_path: Path):
    app = create_app(workspace=tmp_path)
    with TestClient(app) as client:
        response = client.get('/static/theme360.css')

    assert response.status_code == 200
    css = response.text
    assert '--accent: #69f8bb' in css
    assert '--accent-strong: #9effd8' in css
    assert '--wireless-accent: var(--accent)' in css
    assert '.lab-badge strong { color: var(--accent); }' in css
    assert 'white-space: normal' in css
    assert 'overflow-wrap: anywhere' in css


def test_advanced_wireless_keeps_functional_assets_with_unified_theme(tmp_path: Path):
    app = create_app(workspace=tmp_path)
    with TestClient(app) as client:
        html = client.get('/wireless').text

    assert '/static/styles.css' in html
    assert '/static/wireless.css' in html
    assert '/static/wireless340.css' in html
    assert '/static/theme360.css' in html
    assert 'PAIR BY QR' in html
    assert 'PAIR BY CODE' in html
