from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from adbgath.cli import build_parser
from adbgath.core.migrations import CURRENT_SCHEMA_VERSION
from adbgath.core.storage import ProjectStore
from adbgath.models import CommandResult, Device
from adbgath.modules.wireless.broker import WirelessEventBroker
from adbgath.modules.wireless.qr import QrPairingCoordinator, build_adb_qr_payload, render_qr_svg
from adbgath.webapp import create_app


class QrWirelessStub:
    def __init__(self) -> None:
        self.instance = ""
        self.secret_seen = ""
        self.pair_endpoint = "192.168.10.7:37123"
        self.connect_endpoint = "192.168.10.7:41267"

    def discover(self, *, refresh: bool, detailed: bool):
        assert refresh and detailed
        if not self.instance:
            return {"services": [], "pairing_services": [], "connect_services": []}
        pair = {
            "instance": self.instance,
            "service": "_adb-tls-pairing._tcp",
            "service_type": "pairing",
            "host": "192.168.10.7",
            "port": 37123,
            "endpoint": self.pair_endpoint,
            "serial": "QR-DEVICE",
            "requires_pairing": True,
            "connectable": False,
        }
        connect = {
            "instance": "adb-QR-DEVICE-connect",
            "service": "_adb-tls-connect._tcp",
            "service_type": "connect",
            "host": "192.168.10.7",
            "port": 41267,
            "endpoint": self.connect_endpoint,
            "serial": "QR-DEVICE",
            "requires_pairing": False,
            "connectable": True,
        }
        return {"services": [pair, connect], "pairing_services": [pair], "connect_services": [connect]}

    def pair_secret(self, endpoint: str, secret: str, *, method: str):
        assert endpoint == self.pair_endpoint
        assert method == "qr"
        assert len(secret) == 12 and secret.isalnum()
        self.secret_seen = secret
        return CommandResult(
            ok=True,
            command=["adb", "pair", endpoint],
            stdout=f"Successfully paired to {endpoint}\n",
            metadata={"pairing_method": "qr", "stdin_redacted": True},
        )

    def connect(self, endpoint: str):
        assert endpoint == self.connect_endpoint
        return CommandResult(ok=True, command=["adb", "connect", endpoint], stdout=f"connected to {endpoint}\n")


class BrokerManagerStub:
    def __init__(self) -> None:
        self.services = [
            {
                "instance": "adb-LAB-connect",
                "service": "_adb-tls-connect._tcp",
                "endpoint": "192.168.10.9:42000",
                "connectable": True,
                "requires_pairing": False,
            }
        ]

    def discover(self, *, refresh: bool, detailed: bool):
        assert refresh and detailed
        return {"services": list(self.services)}


class BrokerAdbStub:
    @staticmethod
    def devices():
        return [Device(serial="192.168.10.9:42000", state="device", model="Pixel_Lab")]


def test_qr_payload_uses_aosp_adb_wifi_grammar():
    payload = build_adb_qr_payload("studio-AbC123xYz9", "A1b2C3d4E5f6")
    assert payload == "WIFI:T:ADB;S:studio-AbC123xYz9;P:A1b2C3d4E5f6;;"
    svg = render_qr_svg(payload)
    assert svg.startswith(b"<?xml") or b"<svg" in svg[:500]
    assert b"A1b2C3d4E5f6" not in svg


def test_qr_coordinator_pairs_and_connects_without_exposing_secret(tmp_path: Path):
    wireless = QrWirelessStub()
    coordinator = QrPairingCoordinator(wireless, workspace=tmp_path)
    public = coordinator.create(ttl_seconds=60, auto_connect=True, start=False)
    wireless.instance = public["instance"]
    session = coordinator._sessions[public["id"]]
    coordinator._run(session, True)

    result = coordinator.get(public["id"])
    assert result["state"] == "connected"
    assert result["terminal"] is True
    assert result["connect_endpoint"] == wireless.connect_endpoint
    assert result["secret_redacted"] is True
    assert session.secret == ""
    serialized = json.dumps(result)
    assert wireless.secret_seen not in serialized
    assert wireless.secret_seen not in " ".join(result["pair_result"]["command"])


def test_qr_session_can_complete_without_auto_connect(tmp_path: Path):
    wireless = QrWirelessStub()
    coordinator = QrPairingCoordinator(wireless, workspace=tmp_path)
    public = coordinator.create(ttl_seconds=60, auto_connect=False, start=False)
    wireless.instance = public["instance"]
    session = coordinator._sessions[public["id"]]
    coordinator._run(session, False)
    result = coordinator.get(public["id"])
    assert result["state"] == "completed"
    assert result["connect_result"] is None
    assert result["terminal"] is True


def test_shared_broker_produces_initial_snapshot_and_events():
    manager = BrokerManagerStub()
    broker = WirelessEventBroker(manager, BrokerAdbStub(), interval=0.5)
    try:
        first = broker.start()
        assert first["running"] is True
        assert len(first["services"]) == 1
        assert len(first["devices"]) == 1
        sequence = first["sequence"]
        manager.services = []
        deadline = time.monotonic() + 3
        result = first
        while time.monotonic() < deadline:
            result = broker.wait(after_sequence=sequence, timeout=1)
            if any(item["type"] == "service.removed" for item in result["events"]):
                break
            sequence = result["sequence"]
        assert any(item["type"] == "service.removed" for item in result["events"])
    finally:
        broker.stop()


def test_formal_database_migration_creates_backup_and_inventory_table(tmp_path: Path):
    database = tmp_path / "adbgath.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE legacy_marker(value TEXT)")
    connection.execute("INSERT INTO legacy_marker(value) VALUES('preserve')")
    connection.commit()
    connection.close()

    store = ProjectStore(database)
    status = store.schema_status()
    assert status["database_version"] == CURRENT_SCHEMA_VERSION
    assert status["integrity"] == "ok"
    assert any(item["version"] == CURRENT_SCHEMA_VERSION for item in status["migrations"])
    assert list((tmp_path / "database-backups").glob("adbgath-pre-360-*.sqlite3"))
    with store.connect() as migrated:
        assert migrated.execute("SELECT value FROM legacy_marker").fetchone()[0] == "preserve"
        assert migrated.execute("SELECT name FROM sqlite_master WHERE name='inventory_states'").fetchone()


def test_incremental_inventory_ignores_capture_timestamp(service):
    first = service.inventory_capture("emulator-5554", name="before")
    second = service.inventory_capture("emulator-5554", name="after")
    assert first["digest"] == second["digest"]
    diff = service.inventory_diff(first["id"], second["id"])
    assert diff["packages"]["counts"] == {"added": 0, "removed": 0, "changed": 0}
    assert diff["diff"]["summary"] == {"added": 0, "removed": 0, "changed": 0}


def test_v340_cli_commands_parse():
    parser = build_parser()
    qr = parser.parse_args(["wireless", "qr", "--timeout", "180", "--no-auto-connect"])
    assert qr.wireless_mode == "qr" and qr.timeout == 180 and qr.no_auto_connect is True
    broker = parser.parse_args(["wireless", "broker", "status"])
    assert broker.wireless_mode == "broker" and broker.broker_mode == "status"
    inventory = parser.parse_args(["inventory", "diff", "before", "after"])
    assert inventory.mode == "diff"
    assert parser.parse_args(["schema"]).command == "schema"


def test_web_qr_endpoint_is_ephemeral_and_no_store(service):
    client = TestClient(create_app(service=service))
    client.get("/")
    denied = client.post(
        "/api/wireless/qr",
        json={"ttl_seconds": 60, "auto_connect": False, "confirmation": "NO"},
    )
    assert denied.status_code == 409
    created = client.post(
        "/api/wireless/qr",
        json={"ttl_seconds": 60, "auto_connect": False, "confirmation": "AUTHORIZED"},
    )
    assert created.status_code == 200
    body = created.json()
    session = body["data"]
    assert session["secret_redacted"] is True
    assert "secret" not in json.dumps(session).lower().replace("secret_redacted", "")
    svg = client.get(body["svg_url"])
    assert svg.status_code == 200
    assert svg.headers["cache-control"].startswith("no-store")
    assert svg.headers["content-type"].startswith("image/svg+xml")
    cancelled = client.post(f"/api/wireless/qr/{session['id']}/cancel", json={})
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["state"] == "cancelled"


def test_v340_web_controls_exist(service):
    client = TestClient(create_app(service=service))
    client.get("/")
    html = client.get("/wireless").text
    javascript = (Path(__file__).parents[1] / "src" / "adbgath" / "web" / "static" / "wireless340.js").read_text(encoding="utf-8")
    for identifier in [
        "id='wirelessQrCreateButton'",
        "id='wirelessQrImage'",
        "id='wirelessQrState'",
        "id='wirelessQrAuthorized'",
    ]:
        assert identifier in html
    assert "/api/wireless/qr" in javascript
    assert "/ws/wireless/qr/" in javascript
    assert "localStorage" not in javascript
