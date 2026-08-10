from __future__ import annotations

import subprocess

import pytest

from adbgath.adb import AdbClient
from adbgath.errors import CommandExecutionError


def _client(tmp_path):
    adb = tmp_path / "adb"
    adb.write_text("fake", encoding="utf-8")
    return AdbClient(adb)


def test_adb_text_process_oserror_is_command_error(monkeypatch, tmp_path):
    client = _client(tmp_path)

    def fail(*args, **kwargs):
        raise OSError("exec failed")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(CommandExecutionError, match="Unable to start ADB command") as caught:
        client.run(["version"])
    assert caught.value.returncode == 126


def test_adb_binary_process_oserror_is_command_error(monkeypatch, tmp_path):
    client = _client(tmp_path)

    def fail(*args, **kwargs):
        raise OSError("exec failed")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(CommandExecutionError, match="Unable to start ADB binary command"):
        client.run_binary(["exec-out", "screencap", "-p"])


def test_adb_stream_process_oserror_is_command_error(monkeypatch, tmp_path):
    client = _client(tmp_path)

    def fail(*args, **kwargs):
        raise OSError("exec failed")

    monkeypatch.setattr(subprocess, "Popen", fail)
    iterator = client.stream(["logcat"])
    with pytest.raises(CommandExecutionError, match="Unable to start ADB stream"):
        next(iterator)
