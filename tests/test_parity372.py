from __future__ import annotations

from typing import get_args

from fastapi.testclient import TestClient

from adbgath.cli import build_parser
from adbgath.core import operations
from adbgath.core.operations import validate_operation_payload
from adbgath.models import CommandResult
from adbgath.webapp import create_app


def _fields(action: str) -> dict[str, object]:
    return {field.name: field for field in operations.OPERATIONS[action].fields}


def test_secret_is_a_declared_operation_field_type():
    assert "secret" in get_args(operations.FieldType)


def test_update_modes_match_cli_and_web_catalog():
    parser = build_parser()
    assert parser.parse_args(["update"]).mode == "auto"
    assert parser.parse_args(["update", "force"]).mode == "force"
    assert parser.parse_args(["update", "check"]).mode == "check"

    mode = _fields("update")["mode"]
    assert mode.default == "auto"
    assert tuple(mode.choices) == ("auto", "force", "check", "plan", "install", "rollback")
    assert validate_operation_payload("update", {"mode": "force"})["mode"] == "force"


def test_install_set_web_fields_match_cli_switches():
    fields = _fields("install_set")
    assert {"source", "replace_existing", "grant_runtime_permissions"} <= set(fields)
    payload = validate_operation_payload(
        "install_set",
        {
            "source": "sample.apks",
            "replace_existing": False,
            "grant_runtime_permissions": True,
        },
    )
    assert payload["replace_existing"] is False
    assert payload["grant_runtime_permissions"] is True


def test_install_set_dispatch_forwards_web_switches(service, fake_adb, tmp_path):
    source = tmp_path / "base.apk"
    source.write_bytes(b"test-apk")

    result = service.dispatch(
        "install_set",
        {
            "device": "emulator-5554",
            "user": "0",
            "source": str(source),
            "replace_existing": False,
            "grant_runtime_permissions": True,
        },
    )

    assert result["ok"] is True
    command = fake_adb.calls[-1][0]
    assert command[0] == "install"
    assert "-r" not in command
    assert "-g" in command
    assert "--user" in command and "0" in command


def test_logs_capture_exposes_and_forwards_cli_filters(service, monkeypatch):
    fields = _fields("logs_capture")
    assert {"duration", "package", "pid", "regex", "filters", "output", "clear", "format"} <= set(fields)

    seen = {}

    def capture(serial, **kwargs):
        seen["serial"] = serial
        seen.update(kwargs)
        return CommandResult(True, ["adb", "logcat"], stdout="ok")

    monkeypatch.setattr(service, "logs_capture", capture)
    result = service.dispatch(
        "logs_capture",
        {
            "device": "emulator-5554",
            "duration": 12,
            "package": "com.example.app",
            "pid": 321,
            "regex": "token|exception",
            "filters": ["ActivityManager:I", "*:S"],
            "clear": True,
            "format": "brief",
        },
    )
    assert result["ok"] is True
    assert seen == {
        "serial": "emulator-5554",
        "output": None,
        "duration": 12,
        "package": "com.example.app",
        "pid": 321,
        "regex": "token|exception",
        "clear": True,
        "log_format": "brief",
        "filters": ["ActivityManager:I", "*:S"],
    }


def test_inventory_watch_has_bounded_web_equivalent(service, monkeypatch):
    operation = operations.OPERATIONS["inventory_watch"]
    assert operation.long_running is True
    fields = _fields("inventory_watch")
    assert fields["duration"].minimum == 1
    assert fields["duration"].default == 60

    seen = {}

    def watch(serial, *, interval, duration, user):
        seen.update(serial=serial, interval=interval, duration=duration, user=user)
        yield {"type": "baseline"}
        yield {"type": "change", "data": {"packages": {"counts": {"added": 1}}}}

    monkeypatch.setattr(service, "inventory_watch", watch)
    result = service.dispatch(
        "inventory_watch",
        {"device": "emulator-5554", "user": "current", "interval": 2, "duration": 5},
    )
    assert [item["type"] for item in result] == ["baseline", "change"]
    assert seen == {"serial": "emulator-5554", "interval": 2, "duration": 5, "user": "current"}


def test_web_operations_api_publishes_final_parity(service):
    with TestClient(create_app(service=service)) as client:
        response = client.get("/api/operations")
    assert response.status_code == 200
    catalog = {item["name"]: item for item in response.json()["data"]}
    assert "inventory_watch" in catalog
    assert {field["name"] for field in catalog["install_set"]["fields"]} >= {
        "source",
        "replace_existing",
        "grant_runtime_permissions",
    }
    update_mode = next(field for field in catalog["update"]["fields"] if field["name"] == "mode")
    assert update_mode["default"] == "auto"
    assert {"auto", "force"} <= set(update_mode["choices"])
