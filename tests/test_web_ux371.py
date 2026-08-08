from __future__ import annotations

from pathlib import Path

from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

import adbgath
from adbgath.webapp import create_app
from adbgath.webux371 import _upgrade_html


STATIC = Path(__file__).parents[1] / "src" / "adbgath" / "web" / "static"


def test_371_version_and_dashboard_assets(service):
    assert adbgath.__version__ == "3.7.1"
    with TestClient(create_app(service=service)) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "3.7.1" in page.text
        assert page.text.count('/static/ux371.css') == 1
        assert page.text.count('/static/ux371.js') == 1
        assert page.text.count('id="ux371PresetDialog"') == 1
        assert page.text.count('id="ux371ConfirmDialog"') == 1
        assert page.text.index('/static/app.js') < page.text.index('/static/ux371.js')
        assert page.text.index('/static/app370.js') < page.text.index('/static/ux371.js')


def test_371_ux_upgrade_is_idempotent():
    source = """<!doctype html><html><head></head><body><select id=\"presetSelect\"></select><div id=\"toast\" class=\"toast\"></div><script src=\"/static/app.js\"></script></body></html>"""
    first = _upgrade_html(HTMLResponse(source))
    second = _upgrade_html(first)
    text = second.body.decode("utf-8")
    assert text.count('/static/ux371.css') == 1
    assert text.count('/static/ux371.js') == 1
    assert text.count('id="ux371PresetDialog"') == 1
    assert text.count('id="ux371ConfirmDialog"') == 1


def test_371_preset_ux_uses_custom_dialogs_and_never_native_prompt_or_alert():
    javascript = (STATIC / "ux371.js").read_text(encoding="utf-8")
    assert "window.prompt" not in javascript
    assert "prompt(" not in javascript
    assert "alert(" not in javascript
    assert "ux371PresetDialog" in javascript
    assert "ux371ConfirmDialog" in javascript
    assert "showModal" in javascript
    assert "Delete saved preset?" in javascript
    assert "Clear device log buffer?" in javascript
    assert "Cancel background job?" in javascript


def test_371_presets_are_scoped_and_secrets_are_excluded():
    javascript = (STATIC / "ux371.js").read_text(encoding="utf-8")
    assert "adbgath.operationPresets.v2" in javascript
    assert "username.toLowerCase()" in javascript
    assert "workspaceId" in javascript
    assert 'field.field_type === "secret"' in javascript
    assert 'input.type = "password"' in javascript
    assert "localStorage.removeItem(LEGACY_PRESET_KEY)" in javascript
    assert "Secret fields are never stored" in javascript


def test_371_job_polling_stops_at_terminal_state_and_supports_multiple_jobs():
    javascript = (STATIC / "ux371.js").read_text(encoding="utf-8")
    assert "const watchedJobs = new Set()" in javascript
    assert "TERMINAL_JOB_STATES" in javascript
    assert "watchedJobs.delete(jobId)" in javascript
    assert "if (watchedJobs.size)" in javascript
    assert "setTimeout(pollWatchedJobs" in javascript
    assert "setInterval(" not in javascript
    assert "document.hidden ? 3500 : 1200" in javascript


def test_371_command_center_has_inline_validation_busy_states_and_copy_output():
    javascript = (STATIC / "ux371.js").read_text(encoding="utf-8")
    css = (STATIC / "ux371.css").read_text(encoding="utf-8")
    for marker in [
        "ux371-field-error",
        "ux371-invalid",
        'aria-busy',
        "Output copied",
        "navigator.clipboard.writeText",
    ]:
        assert marker in javascript or marker in css
    assert ".ux371-dialog::backdrop" in css
    assert "var(--accent)" in css
    assert "prefers-reduced-motion" in css


def test_371_auth_pages_show_patch_version(monkeypatch, tmp_path, service):
    monkeypatch.setenv("ADBGATH_SERVER_HOME", str(tmp_path / "fresh-auth"))
    with TestClient(create_app(service=service)) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "ADB-GATH 3.7.1" in page.text
        assert "/static/ux371.js" not in page.text
        assert "ux371PresetDialog" not in page.text
