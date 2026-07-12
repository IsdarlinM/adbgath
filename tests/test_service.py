from __future__ import annotations

import json
from pathlib import Path

import pytest

from adbgath.errors import ValidationError


def test_devices_marks_root(service):
    devices = service.devices()
    assert devices[0]["serial"] == "emulator-5554"
    assert devices[0]["rooted"] is True


def test_users_and_packages(service):
    users = service.list_users(None)
    assert users == [{"id": "0", "name": "Owner"}, {"id": "10", "name": "Work"}]
    packages = service.list_packages(None, user="current", include_paths=True)
    assert packages[0]["name"] == "com.example.app"
    assert packages[0]["apk_paths"] == ["/data/app/com.example/base.apk"]


def test_app_summary(service):
    summary = service.app_summary(None, "com.example.app")
    assert summary["package"] == "com.example.app"
    assert "android.permission.INTERNET" in summary["granted_permissions"]


def test_security_audit_writes_json_and_markdown(service, tmp_path: Path):
    target = tmp_path / "report.json"
    report = service.security_audit(None, output=target)
    assert report["summary"]["high"] >= 3
    assert target.is_file()
    assert target.with_suffix(".md").is_file()
    stored = json.loads(target.read_text(encoding="utf-8"))
    assert stored["tool"] == "adbgath"


def test_pull_apks_creates_artifact(service, tmp_path: Path):
    result = service.pull_apks(None, packages=["com.example.app"], output=tmp_path / "apks")
    assert result.ok
    assert len(result.artifacts) == 1
    assert Path(result.artifacts[0]).read_bytes() == b"APK"


def test_log_capture_filters_regex(service, tmp_path: Path):
    result = service.logs_capture(None, output=tmp_path / "capture.log", duration=1, regex="exception")
    assert result.ok
    text = (tmp_path / "capture.log").read_text(encoding="utf-8")
    assert "exception" in text
    assert "hello" not in text


def test_state_changing_operations_require_explicit_device(service, tmp_path):
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"APK")
    with pytest.raises(ValidationError, match="explicit --device"):
        service.install_apks(None, [apk], user="0")
    with pytest.raises(ValidationError, match="explicit --device"):
        service.uninstall_packages(None, ["com.example.app"], user="0")


def test_list_all_apk_paths(service):
    paths = service.list_apk_paths("emulator-5554", user="0")
    assert paths[0]["name"] == "com.example.app"
    assert paths[0]["apk_paths"] == ["/data/app/com.example/base.apk"]
