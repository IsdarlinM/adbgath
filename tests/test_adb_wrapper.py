from __future__ import annotations

import subprocess
from pathlib import Path

from adbgath.adb import AdbClient


def test_adb_run_uses_argument_array_and_never_shell(monkeypatch, tmp_path: Path):
    adb = tmp_path / "adb.exe"
    adb.write_text("fake", encoding="utf-8")
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = AdbClient(adb)
    result = client.run(["shell", "getprop", "ro.product.model"], serial="emulator-5554")
    assert result.ok
    assert observed["command"] == [str(adb.resolve()), "-s", "emulator-5554", "shell", "getprop", "ro.product.model"]
    assert observed["kwargs"]["shell"] is False
