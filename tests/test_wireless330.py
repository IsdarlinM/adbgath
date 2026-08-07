from __future__ import annotations

import subprocess
from pathlib import Path

from adbgath.adb import AdbClient
from adbgath.core.operations import OPERATIONS
from adbgath.modules.wireless import parse_mdns_output, parse_server_status
from adbgath.validation import parse_host_port, validate_pairing_code


def test_mdns_parser_separates_pairing_and_connection_ports():
    text = '''
tls {
  service {
    instance: "adb-ABC-pair"
    service: "_adb-tls-pairing._tcp"
    ipv4: "192.168.1.5"
    port: 37123
    product_model: "Pixel 8"
    serial: "ABC"
  }
}
tls {
  service {
    instance: "adb-ABC-connect"
    service: "_adb-tls-connect._tcp"
    ipv4: "192.168.1.5"
    port: 41267
    product_model: "Pixel 8"
    serial: "ABC"
  }
}
'''
    services = parse_mdns_output(text)
    pairing = next(item for item in services if item.requires_pairing)
    connection = next(item for item in services if item.connectable)
    assert pairing.endpoint == "192.168.1.5:37123"
    assert connection.endpoint == "192.168.1.5:41267"
    assert pairing.port != connection.port


def test_legacy_mdns_ipv6_and_server_status():
    services = parse_mdns_output(
        "adb-ABC-pair _adb-tls-pairing._tcp 192.168.1.5:37123\n"
        "adb-ABC-connect _adb-tls-connect._tcp [fe80::1234]:41267\n"
    )
    assert services[0].service_type == "pairing"
    assert services[1].endpoint == "[fe80::1234]:41267"
    status = parse_server_status('version: "37.0.0"\nmdns_enabled: true\nmdns_backend: "LIBADBMDNS"\n')
    assert status["mdns_enabled"] is True
    assert status["mdns_backend"] == "LIBADBMDNS"


def test_endpoint_and_pairing_code_validation():
    assert parse_host_port("pixel-lab.local:41267").endpoint == "pixel-lab.local:41267"
    assert parse_host_port("[fe80::1234]:41267").endpoint == "[fe80::1234]:41267"
    assert validate_pairing_code("123456") == "123456"


def test_operation_catalog_marks_pairing_secret_and_destructive():
    pairing = OPERATIONS["wireless_pair"]
    assert pairing.destructive is True
    code = next(field for field in pairing.fields if field.name == "pairing_code")
    assert code.field_type == "secret"


def test_adb_returncode_zero_textual_connect_failure_is_not_success(monkeypatch, tmp_path: Path):
    adb = tmp_path / "adb.exe"
    adb.write_text("fake", encoding="utf-8")

    def fake_run(command, **kwargs):
        del kwargs
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                "cannot connect to 172.18.9.245:42029: No connection could be made because "
                "the target machine actively refused it. (10061)\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = AdbClient(adb).run(["connect", "172.18.9.245:42029"], check=False)
    assert result.returncode == 0
    assert result.ok is False
    assert result.metadata["semantic_failure"] == "adb-textual-failure"


def test_pairing_code_is_stdin_only(monkeypatch, tmp_path: Path):
    adb = tmp_path / "adb.exe"
    adb.write_text("fake", encoding="utf-8")
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout="Successfully paired to 192.168.1.5:37123\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = AdbClient(adb).run_interactive(
        ["pair", "192.168.1.5:37123"], input_data="123456", check=False
    )
    assert result.ok is True
    assert "123456" not in result.command
    assert "123456" not in result.stdout
    assert observed["kwargs"]["input"] == "123456\n"
    assert observed["kwargs"]["shell"] is False
    assert result.metadata["stdin_redacted"] is True
