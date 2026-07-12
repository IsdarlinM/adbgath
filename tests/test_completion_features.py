from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import pytest

import adbgath.service as service_module
from adbgath.core.files import sha256_file
from adbgath.core.operations import validate_operation_payload


def test_frida_session_history_redacts_saved_logs(service, monkeypatch):
    monkeypatch.setattr(
        service_module.shutil,
        "which",
        lambda name: f"/usr/bin/{name}" if name in {"frida", "frida-ps"} else None,
    )

    def completed(command, **kwargs):
        del kwargs
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="token=super-secret-value\nmessage: {event: tls-handshake}\n",
            stderr="",
        )

    monkeypatch.setattr(service_module.subprocess, "run", completed)
    result = service.frida(
        "emulator-5554",
        "attach",
        "com.example.app",
        "tls-observer",
        redact=True,
    )
    assert result.ok
    assert len(result.artifacts) == 3
    history = service.frida_history()
    assert history[0]["status"] == "completed"
    assert history[0]["script_name"] == "tls-observer"
    assert history[0]["metadata"]["script"]["version"] == "1.0.0"
    stored = Path(history[0]["stdout_path"]).read_text(encoding="utf-8")
    assert "super-secret-value" not in stored
    assert "<REDACTED>" in stored
    session_document = json.loads(Path(result.artifacts[-1]).read_text(encoding="utf-8"))
    assert session_document["id"] == history[0]["id"]


def test_frida_script_syntax_validation(service, tmp_path: Path, monkeypatch):
    script = tmp_path / "invalid.js"
    script.write_text("function broken( {", encoding="utf-8")
    monkeypatch.setattr(
        service_module.shutil,
        "which",
        lambda name: "/usr/bin/frida" if name == "frida" else ("/usr/bin/node" if name == "node" else None),
    )

    def checked(command, **kwargs):
        del kwargs
        if command[0].endswith("node"):
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="SyntaxError")
        raise AssertionError("Frida must not run after script validation fails")

    monkeypatch.setattr(service_module.subprocess, "run", checked)
    with pytest.raises(Exception, match="syntax validation failed"):
        service.frida("emulator-5554", "attach", "com.example.app", script)


def test_project_export_zip_contains_metadata_and_workspace_artifacts(service):
    project = service.store.create_project("Export", scope="authorized test")
    session = service.store.create_session(project["id"], device_serial="emulator-5554")
    artifact = service.workspace / "projects" / project["id"] / "report.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text('{"ok":true}', encoding="utf-8")
    service.store.save_artifact(
        path=str(artifact),
        sha256=sha256_file(artifact),
        size=artifact.stat().st_size,
        media_type="application/json",
        project_id=project["id"],
        session_id=session["id"],
    )
    outside = service.workspace.parent / "outside.txt"
    outside.write_text("not exportable", encoding="utf-8")
    service.store.save_artifact(
        path=str(outside),
        sha256=sha256_file(outside),
        size=outside.stat().st_size,
        media_type="text/plain",
        project_id=project["id"],
    )

    result = service.export_project_bundle(project["id"])
    target = Path(result["artifact"])
    assert target.is_file()
    assert result["sha256"] == sha256_file(target)
    with zipfile.ZipFile(target) as archive:
        names = set(archive.namelist())
        assert {"project.json", "sessions.json", "findings.json", "snapshots.json", "export-manifest.json"} <= names
        assert any(name.endswith("report.json") for name in names)
        manifest = json.loads(archive.read("export-manifest.json"))
        assert manifest["tool_version"] == "3.2.9"
        assert manifest["included"][0]["sha256"] == sha256_file(artifact)
        assert any(item["reason"] == "outside workspace" for item in manifest["skipped"])


def test_numeric_operation_bounds_are_enforced():
    assert validate_operation_payload("frida", {"mode": "history", "limit": 100})["limit"] == 100
    with pytest.raises(ValueError, match="at most 1000"):
        validate_operation_payload("frida", {"mode": "history", "limit": 1001})


def test_frontend_completion_controls_are_present():
    root = Path(__file__).parents[1] / "src" / "adbgath" / "web" / "static"
    html = (root / "index.html").read_text(encoding="utf-8")
    javascript = (root / "app.js").read_text(encoding="utf-8")
    for identifier in [
        'id="presetSelect"',
        'id="packagePageLabel"',
        'id="pauseLogs"',
        'id="bookmarkLog"',
        'id="exportLogs"',
        'id="severityChart"',
    ]:
        assert identifier in html
    assert "MAX_LOG_LINES = 5000" in javascript
    assert "adbgath.operationPresets.v1" in javascript
    assert "uploadFiles(event.dataTransfer.files)" in javascript
