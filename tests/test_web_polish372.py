from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from adbgath.webapp import create_app


STATIC = Path(__file__).parents[1] / "src" / "adbgath" / "web" / "static"


def test_dashboard_loads_final_372_assets_after_existing_ux(service):
    with TestClient(create_app(service=service)) as client:
        page = client.get("/")
        css = client.get("/static/ux372.css")
        js = client.get("/static/ux372.js")
    assert page.status_code == 200
    assert css.status_code == 200
    assert js.status_code == 200
    assert page.text.count('/static/ux372.css') == 1
    assert page.text.count('/static/ux372.js') == 1
    assert page.text.index('/static/presets371.js') < page.text.index('/static/ux372.js')


def test_final_workspace_ux_adds_job_and_artifact_filters_and_copy_path():
    source = (STATIC / "ux372.js").read_text(encoding="utf-8")
    for marker in [
        "ux372JobStatus",
        "ux372JobSearch",
        "ux372ArtifactSearch",
        "COPY PATH",
        "decorateJobs",
        "decorateArtifacts",
        "sessionStorage",
    ]:
        assert marker in source


def test_security_jobs_stay_in_security_view_and_render_completed_results():
    source = (STATIC / "ux372.js").read_text(encoding="utf-8")
    assert 'event.target?.closest?.("#runSecurity, #runMastg")' in source
    assert "event.stopImmediatePropagation()" in source
    assert 'switchView("security")' in source
    assert 'job.action === "security"' in source
    assert 'job.action === "mastg"' in source
    assert "renderFindings(report)" in source
    assert "TERMINAL_JOB_STATES" in source


def test_final_ux_is_theme_based_responsive_and_has_no_native_dialogs():
    javascript = (STATIC / "ux372.js").read_text(encoding="utf-8")
    css = (STATIC / "ux372.css").read_text(encoding="utf-8")
    assert "alert(" not in javascript
    assert "prompt(" not in javascript
    assert "var(--panel)" in css
    assert "var(--accent)" in css
    assert "@media (max-width: 760px)" in css
