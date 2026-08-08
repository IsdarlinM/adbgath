from __future__ import annotations

from pathlib import Path

from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

import adbgath
from adbgath.webapp import create_app
from adbgath.webapp370 import LOGIN_HTML, SETUP_HTML
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
        assert page.text.count('/static/presets371.js') == 1
        assert page.text.count('id="ux371PresetDialog"') == 1
        assert page.text.count('id="ux371ConfirmDialog"') == 1
        assert page.text.index('/static/app.js') < page.text.index('/static/ux371.js')
        assert page.text.index('/static/app370.js') < page.text.index('/static/ux371.js')
        assert page.text.index('/static/ux371.js') < page.text.index('/static/presets371.js')


def test_371_ux_upgrade_is_idempotent():
    source = """<!doctype html><html><head></head><body><select id=\"presetSelect\"></select><div id=\"toast\" class=\"toast\"></div><script src=\"/static/app.js\"></script></body></html>"""
    first = _upgrade_html(HTMLResponse(source))
    second = _upgrade_html(first)
    text = second.body.decode("utf-8")
    assert text.count('/static/ux371.css') == 1
    assert text.count('/static/ux371.js') == 1
    assert text.count('/static/presets371.js') == 1
    assert text.count('id="ux371PresetDialog"') == 1
    assert text.count('id="ux371ConfirmDialog"') == 1


def test_371_preset_ux_uses_custom_dialogs_and_never_native_prompt_or_alert():
    javascript = (STATIC / "ux371.js").read_text(encoding="utf-8")
    presets = (STATIC / "presets371.js").read_text(encoding="utf-8")
    for source in (javascript, presets):
        assert "window.prompt" not in source
        assert "prompt(" not in source
        assert "alert(" not in source
    assert "ux371PresetDialog" in javascript
    assert "ux371ConfirmDialog" in javascript
    assert "showModal" in javascript
    assert "Delete saved preset?" in presets
    assert "Clear device log buffer?" in javascript
    assert "Cancel background job?" in javascript


def test_371_presets_use_authenticated_server_workspace_and_exclude_secrets():
    javascript = (STATIC / "ux371.js").read_text(encoding="utf-8")
    presets = (STATIC / "presets371.js").read_text(encoding="utf-8")
    assert "localStorage" not in javascript
    assert 'input.type = "password"' in javascript
    assert 'field.field_type === "secret"' in presets
    assert 'api("/api/presets")' in presets
    assert 'api("/api/presets", {' in presets
    assert 'method:"DELETE"' in presets
    assert "authenticated ADB-Gath workspace" in presets
    assert "detachLegacyStorage" in presets
    assert "restoreLegacyStorage" in presets


def test_371_server_preset_api_is_workspace_scoped_and_strips_secret_fields(service):
    with TestClient(create_app(service=service)) as client:
        workspaces = client.get("/api/workspaces").json()["data"]
        assert len(workspaces) == 1
        original_id = workspaces[0]["id"]

        saved = client.post(
            "/api/presets",
            json={
                "name": "Wireless authorized lab",
                "action": "wireless_pair",
                "payload": {
                    "target": "192.168.1.5:37123",
                    "pairing_code": "123456",
                },
            },
        )
        assert saved.status_code == 200
        preset = saved.json()["data"]
        assert preset["payload"] == {"target": "192.168.1.5:37123"}
        assert "123456" not in saved.text

        created = client.post("/api/workspaces", json={"name": "Second assessment"})
        assert created.status_code == 200
        second_id = created.json()["data"]["active_workspace_id"]
        assert second_id != original_id
        assert client.get("/api/presets").json()["data"] == []

        selected = client.post(f"/api/workspaces/{original_id}/select", json={})
        assert selected.status_code == 200
        original_presets = client.get("/api/presets").json()["data"]
        assert [item["id"] for item in original_presets] == [preset["id"]]

        deleted = client.delete(f"/api/presets/{preset['id']}")
        assert deleted.status_code == 200
        assert client.get("/api/presets").json()["data"] == []


def test_371_job_polling_stops_at_terminal_state_and_supports_multiple_jobs():
    javascript = (STATIC / "ux371.js").read_text(encoding="utf-8")
    assert "const watchedJobs = new Set()" in javascript
    assert "TERMINAL_JOB_STATES" in javascript
    assert "let jobPollRunning = false" in javascript
    assert "scheduleJobPoll" in javascript
    assert "watchedJobs.delete(jobId)" in javascript
    assert "if (!job)" in javascript
    assert "setTimeout(() =>" in javascript
    assert "setInterval(" not in javascript
    assert "document.hidden ? 3500 : 1200" in javascript
    assert 'document.addEventListener("visibilitychange"' in javascript


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


def test_371_auth_pages_show_patch_version_without_dashboard_assets():
    for template in (LOGIN_HTML, SETUP_HTML):
        response = _upgrade_html(HTMLResponse(template.format(error="", legacy="")))
        text = response.body.decode("utf-8")
        assert "ADB-GATH 3.7.1" in text
        assert "/static/ux371.js" not in text
        assert "/static/presets371.js" not in text
        assert "ux371PresetDialog" not in text
