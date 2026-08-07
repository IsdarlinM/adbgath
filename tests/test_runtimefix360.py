from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from adbgath.models import Device
from adbgath.modules.wireless.manager import WirelessManager
from adbgath.runtimefix360 import _hidden_process_kwargs
from adbgath.webapp import create_app


class _Store:
    def __init__(self, known=None):
        self.known = list(known or [])

    def list_wireless_devices(self):
        return list(self.known)


class _NativeAutoAdb:
    def __init__(self):
        self.calls = 0

    def devices(self):
        self.calls += 1
        if self.calls < 2:
            return []
        return [Device(serial="10.0.0.28:43005", state="device")]


class _NoConnectAdb:
    def __init__(self):
        self.run_calls = []

    def devices(self):
        return []

    def run(self, args, **kwargs):
        self.run_calls.append((args, kwargs))
        raise AssertionError("Untrusted auto-connect must not call adb connect")


def test_web_bootstrap_defers_adb_probe(tmp_path: Path):
    app = create_app(workspace=tmp_path)
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        bootstrap = client.get("/api/bootstrap").json()
    assert bootstrap["ok"] is True
    assert bootstrap["devices"] == []
    assert bootstrap["doctor"]["adb_probe_deferred"] is True


def test_wireless_auto_connect_accepts_native_adb_mdns_connection(tmp_path: Path):
    manager = WirelessManager(_NativeAutoAdb(), _Store(), home=tmp_path)
    manager.discover = lambda **_: {
        "connect_services": [
            {
                "endpoint": "10.0.0.28:43005",
                "instance": "adb-test",
                "serial": "",
            }
        ]
    }
    result = manager.auto_connect()
    assert result["native_autoconnect"] is True
    assert result["attempted"] == 0
    assert result["connected"] == 1
    assert result["results"][0]["method"] == "adb-native-mdns"


def test_wireless_auto_connect_does_not_force_unknown_mdns_service(tmp_path: Path):
    adb = _NoConnectAdb()
    manager = WirelessManager(adb, _Store(), home=tmp_path)
    manager.discover = lambda **_: {
        "connect_services": [
            {
                "endpoint": "10.0.0.28:43005",
                "instance": "adb-unknown",
                "serial": "",
            }
        ]
    }
    result = manager.auto_connect()
    assert result["attempted"] == 0
    assert result["connected"] == 0
    assert result["skipped"][0]["endpoint"] == "10.0.0.28:43005"
    assert adb.run_calls == []


@pytest.mark.skipif(os.name != "nt", reason="Windows-specific subprocess flag")
def test_windows_adb_processes_use_create_no_window():
    flags = _hidden_process_kwargs().get("creationflags", 0)
    assert flags & subprocess.CREATE_NO_WINDOW
    grouped = _hidden_process_kwargs(process_group=True).get("creationflags", 0)
    assert grouped & subprocess.CREATE_NO_WINDOW
    assert grouped & subprocess.CREATE_NEW_PROCESS_GROUP
