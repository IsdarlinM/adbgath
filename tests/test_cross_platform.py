from __future__ import annotations

import re
from pathlib import Path

import pytest

from adbgath.errors import AdbgathError, ValidationError
from adbgath.service import WEB_ACTIONS
from adbgath.webapp import serve

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_web_frontend_and_backend_action_parity():
    javascript = (PROJECT_ROOT / "src/adbgath/web/static/app.js").read_text(encoding="utf-8")
    action_block = javascript.split("const ACTIONS = {", 1)[1].split("\n};", 1)[0]
    frontend_actions = set(re.findall(r"^  ([a-z_]+): \{", action_block, flags=re.MULTILINE))
    assert frontend_actions == set(WEB_ACTIONS)


def test_web_server_rejects_non_loopback_binding():
    with pytest.raises(AdbgathError, match="loopback"):
        serve(host="192.0.2.1", open_browser=False)


def test_logcat_rejects_invalid_format_and_regex(service):
    with pytest.raises(ValidationError, match="format"):
        service.logs_capture(None, duration=1, log_format="unknown")
    with pytest.raises(ValidationError, match="regular expression"):
        service.logs_capture(None, duration=1, regex="[")


def test_windows_installer_bootstraps_dependencies_and_user_path():
    installer = (PROJECT_ROOT / "installers/windows/install.ps1").read_text(encoding="utf-8")
    required_fragments = {
        "Python.Python.3.12",
        "platform-tools-latest-windows.zip",
        "Add-UserPath $PlatformRoot",
        "Add-UserPath $BinRoot",
        'SetEnvironmentVariable("ADB_PATH"',
        'SetEnvironmentVariable("ADBGATH_HOME"',
        "adbgath.cmd",
        "adbgath-web.cmd",
        "Get-AuthenticodeSignature",
    }
    for fragment in required_fragments:
        assert fragment in installer


def test_repository_does_not_ship_platform_binaries():
    forbidden = {".exe", ".dll", ".so", ".dylib", ".apk", ".pcap"}
    tracked_sources = [path for path in PROJECT_ROOT.rglob("*") if path.is_file() and "dist" not in path.parts]
    assert not [path for path in tracked_sources if path.suffix.lower() in forbidden]
