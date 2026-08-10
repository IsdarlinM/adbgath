from __future__ import annotations

import pytest

from adbgath.errors import CommandExecutionError
from adbgath.models import CommandResult


def _malformed_pid_adb(service, monkeypatch):
    original = service.adb.run

    def run(args, **kwargs):
        if list(args)[:2] == ["shell", "pidof"]:
            return CommandResult(ok=True, command=["adb", *args], stdout="not-a-pid\n")
        return original(args, **kwargs)

    monkeypatch.setattr(service.adb, "run", run)


def test_log_capture_malformed_pid_is_command_error(service, monkeypatch):
    _malformed_pid_adb(service, monkeypatch)
    with pytest.raises(CommandExecutionError, match="invalid process identifier"):
        service.logs_capture("emulator-5554", package="com.example.app", duration=1)


def test_log_stream_malformed_pid_is_command_error(service, monkeypatch):
    _malformed_pid_adb(service, monkeypatch)
    iterator = service.logs_stream("emulator-5554", package="com.example.app")
    with pytest.raises(CommandExecutionError, match="invalid process identifier"):
        next(iterator)
