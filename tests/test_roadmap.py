from __future__ import annotations

import json
import threading
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from adbgath.core.diffing import diff_values
from adbgath.core.jobs import JobManager
from adbgath.core.operations import validate_operation_payload
from adbgath.core.reports import write_report
from adbgath.errors import CommandExecutionError
from adbgath.models import CommandResult
from adbgath.modules.apk import ApkInspector
from adbgath.service import AdbgathService
from adbgath.webapp import create_app


def finding() -> dict[str, object]:
    return {
        "rule_id": "ANDROID-TEST-001",
        "title": "Test finding",
        "severity": "high",
        "confidence": "high",
        "status": "open",
        "component": "com.example/.MainActivity",
        "description": "A controlled test finding.",
        "evidence": "android:exported=true",
        "impact": "External applications may reach the component.",
        "validation": "Validate on an authorized test device.",
        "false_positive": "Protected by an equivalent runtime authorization control.",
        "mitigation": "Disable export or require a signature permission.",
        "references": ["CWE-926", "OWASP MASVS"],
    }


def test_all_report_formats_include_pdf(tmp_path: Path):
    data = {"title": "ADB-Gath report", "project_id": "prj_test", "findings": [finding()]}
    extensions = {"json": ".json", "md": ".md", "html": ".html", "csv": ".csv", "sarif": ".sarif", "pdf": ".pdf"}
    for format_name, extension in extensions.items():
        target = tmp_path / f"report{extension}"
        write_report(data, target, format_name)
        assert target.is_file() and target.stat().st_size > 20
    assert (tmp_path / "report.pdf").read_bytes().startswith(b"%PDF")
    assert "Test finding" in (tmp_path / "report.html").read_text(encoding="utf-8")
    assert json.loads((tmp_path / "report.sarif").read_text(encoding="utf-8"))["version"] == "2.1.0"


def test_static_apk_attack_surface_analysis(tmp_path: Path):
    apk = tmp_path / "sample.apk"
    manifest = """<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.example.app">
    <permission android:name="com.example.WEAK" android:protectionLevel="normal"/>
    <application android:debuggable="true" android:allowBackup="true" android:usesCleartextTraffic="true">
      <activity android:name=".Exported" android:exported="true">
        <intent-filter><action android:name="android.intent.action.VIEW"/><data android:scheme="demo" android:host="open"/></intent-filter>
      </activity>
      <service android:name=".Implicit"><intent-filter><action android:name="demo.ACTION"/></intent-filter></service>
    </application></manifest>"""
    with zipfile.ZipFile(apk, "w") as archive:
        archive.writestr("AndroidManifest.xml", manifest)
        archive.writestr("assets/config.json", '{"api_key":"ABCDEFGHIJKLMNOPQRSTUVWX","url":"http://api.example.test"}')
        archive.writestr("classes.dex", b"android/webkit/WebView addJavascriptInterface setJavaScriptEnabled")
    result = ApkInspector().inspect(apk)
    rules = {item["rule_id"] for item in result["findings"]}
    assert {"ANDROID-APP-DEBUG-001", "ANDROID-APP-EXPORTED-001", "ANDROID-APP-NET-001"} <= rules
    assert result["manifest"]["deep_links"] == [{"scheme": "demo", "host": "open"}]
    assert len(result["manifest"]["custom_permissions"]) == 1


def test_split_apk_install_uses_install_multiple(service, fake_adb, tmp_path: Path):
    source = tmp_path / "splits"
    source.mkdir()
    (source / "base.apk").write_bytes(b"base")
    (source / "split_config.arm64_v8a.apk").write_bytes(b"split")
    result = service.install_apk_set("emulator-5554", source, user="0")
    assert result.ok
    command = fake_adb.calls[-1][0]
    assert command[0] == "install-multiple"
    assert "--user" in command and "0" in command


class ReplaceAdb:
    def __init__(self, root: Path, *, rollback_ok: bool = True) -> None:
        self.adb_path = root / "adb"
        self.adb_path.write_text("fake", encoding="utf-8")
        self.calls: list[list[str]] = []
        self.rollback_ok = rollback_ok
        self.install_count = 0

    def require_device(self, serial):
        return serial or "emulator-5554"

    def build(self, args, *, serial=None):
        return [str(self.adb_path), "-s", serial or "emulator-5554", *args]

    def run(self, args, *, serial=None, timeout=None, check=True, cwd=None):
        del timeout, check, cwd
        args = list(args)
        self.calls.append(args)
        if args[:4] == ["shell", "pm", "list", "users"]:
            return CommandResult(True, self.build(args, serial=serial), stdout="UserInfo{0:Owner:13}\n")
        if args[:3] == ["shell", "pm", "path"]:
            return CommandResult(True, self.build(args, serial=serial), stdout="package:/data/app/base.apk\n")
        if args[0] == "pull":
            destination = Path(args[-1])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"ORIGINAL")
            return CommandResult(True, self.build(args, serial=serial), stdout="pulled")
        if args[0] == "install":
            self.install_count += 1
            if self.install_count == 1:
                return CommandResult(False, self.build(args, serial=serial), stderr="UPDATE_INCOMPATIBLE", returncode=1)
            if self.install_count == 2:
                return CommandResult(False, self.build(args, serial=serial), stderr="INSTALL_FAILED", returncode=1)
            return CommandResult(
                self.rollback_ok,
                self.build(args, serial=serial),
                stderr="" if self.rollback_ok else "ROLLBACK_FAILED",
                returncode=0 if self.rollback_ok else 1,
            )
        if args[0] == "uninstall":
            return CommandResult(True, self.build(args, serial=serial), stdout="Success")
        return CommandResult(True, self.build(args, serial=serial))

    def version(self):
        return CommandResult(True, [str(self.adb_path), "version"], stdout="ADB 1.0.41")


def test_replace_preserves_installed_app_without_uninstall_permission(tmp_path: Path):
    adb = ReplaceAdb(tmp_path)
    service = AdbgathService(adb, workspace=tmp_path / "workspace")
    apk = tmp_path / "replacement.apk"
    apk.write_bytes(b"NEW")
    with pytest.raises(CommandExecutionError, match="preserved"):
        service.replace_app("emulator-5554", "com.example.app", apk, user="0", allow_uninstall=False)
    assert not any(call[0] == "uninstall" for call in adb.calls)


def test_replace_attempts_rollback_after_fallback_failure(tmp_path: Path):
    adb = ReplaceAdb(tmp_path)
    service = AdbgathService(adb, workspace=tmp_path / "workspace")
    apk = tmp_path / "replacement.apk"
    apk.write_bytes(b"NEW")
    with pytest.raises(CommandExecutionError, match="Rollback succeeded"):
        service.replace_app("emulator-5554", "com.example.app", apk, user="0", allow_uninstall=True)
    installs = [call for call in adb.calls if call[0] in {"install", "install-multiple"}]
    assert len(installs) == 3
    assert any("backup" in argument for argument in installs[-1] for argument in [str(argument)])


def test_evidence_manifest_hashes_redaction_and_project_links(service, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ADBGATH_MANIFEST_HMAC_KEY", "controlled-test-key")
    project = service.store.create_project("Evidence test", scope="com.example.app")
    session = service.store.create_session(project["id"], device_serial="emulator-5554", package_name="com.example.app")
    result = service.capture_evidence(
        "emulator-5554",
        package="com.example.app",
        output=tmp_path / "evidence",
        project_id=project["id"],
        session_id=session["id"],
    )
    manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    assert manifest["tool_version"] == "3.2.9"
    assert manifest["artifacts"]
    assert Path(result["signature"]).is_file()
    assert (tmp_path / "evidence" / "screenshot.png").read_bytes().startswith(b"\x89PNG")
    assert service.store.list_artifacts(project["id"])


def test_project_snapshot_and_diff_workflow(service, tmp_path: Path):
    project = service.store.create_project("Diff", scope="emulator-5554")
    first = service.create_snapshot("emulator-5554", "before", project_id=project["id"])
    second = service.create_snapshot("emulator-5554", "after", project_id=project["id"])
    output = tmp_path / "diff.json"
    result = service.compare_snapshots(first["id"], second["id"], output=output)
    assert result["diff"]["summary"] == {"added": 0, "removed": 0, "changed": 0}
    assert output.is_file()
    direct = diff_values({"a": 1}, {"a": 2, "b": 3})
    assert direct["summary"] == {"added": 1, "removed": 0, "changed": 1}


def test_job_manager_persists_progress_and_completion(service):
    manager = JobManager(service.store, max_workers=1)

    def work(cancel_event: threading.Event, progress):
        assert not cancel_event.is_set()
        progress(50)
        return {"ok": True}

    job = manager.submit("inventory", {}, work)
    deadline = time.time() + 3
    while time.time() < deadline:
        current = manager.get(job["id"])
        if current["status"] == "completed":
            break
        time.sleep(0.02)
    assert current["status"] == "completed"
    assert current["progress"] == 100
    assert current["result"] == {"ok": True}


def test_strict_operation_payload_validation():
    assert validate_operation_payload("reports", {"project_id": "prj", "format": "pdf"})["format"] == "pdf"
    with pytest.raises(ValueError, match="Unsupported fields"):
        validate_operation_payload("devices", {"shell": "id"})
    with pytest.raises(ValueError, match="one of"):
        validate_operation_payload("reports", {"project_id": "prj", "format": "exe"})


def test_remote_web_requires_operator_login(service):
    token = "A" * 32
    client = TestClient(
        create_app(service=service, remote_token=token, secure_cookie=True), base_url="https://testserver"
    )
    login_page = client.get("/")
    assert login_page.status_code == 401
    assert "Remote workspace sign in" in login_page.text
    assert client.get("/api/bootstrap").status_code == 403
    denied = client.post("/login", data={"token": "wrong-token-value-123456789"})
    assert denied.status_code == 403
    accepted = client.post("/login", data={"token": token})
    assert accepted.status_code == 200
    assert accepted.cookies.get("adbgath_session")
    assert client.get("/api/bootstrap").status_code == 200
