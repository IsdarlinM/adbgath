from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from adbgath.cli import build_parser, run
from adbgath.core.operations import OPERATIONS
from adbgath.errors import AdbgathError


STATIC = Path(__file__).parents[1] / "src" / "adbgath" / "web" / "static"


def _root_choices(parser: argparse.ArgumentParser) -> set[str]:
    action = next(item for item in parser._actions if isinstance(item, argparse._SubParsersAction))
    return set(action.choices)


def test_public_cli_surface_has_no_redundant_top_level_commands():
    choices = _root_choices(build_parser())
    assert not ({"connect", "disconnect", "pair", "collect", "ls", "pull", "logcat"} & choices)
    assert {"wireless", "evidence", "list", "download", "logs"} <= choices


def test_all_extended_cli_modes_parse_with_representative_arguments():
    parser = build_parser()
    cases = [
        ["devices", "--fast", "--no-details"],
        ["metrics", "summary"], ["metrics", "list", "--limit", "10"], ["metrics", "clear"],
        ["wireless", "status", "--no-discover"], ["wireless", "discover", "--legacy"],
        ["wireless", "pair", "127.0.0.1:37123"], ["wireless", "connect", "127.0.0.1:5555"],
        ["wireless", "disconnect", "127.0.0.1:5555"], ["wireless", "auto-connect"],
        ["wireless", "diagnose", "--fix", "--persist"], ["wireless", "known"],
        ["wireless", "forget", "device-id"], ["wireless", "alias", "device-id", "Pixel-Lab"],
        ["wireless", "tcpip", "--port", "5555"], ["wireless", "watch", "--interval", "1", "--duration", "1"],
        ["wireless", "qr", "--timeout", "60", "--no-auto-connect"], ["wireless", "broker", "status"],
        ["inventory", "export"], ["inventory", "capture", "--name", "before"],
        ["inventory", "list", "--limit", "5"], ["inventory", "diff", "before", "after"],
        ["inventory", "watch", "--interval", "1", "--duration", "1"], ["schema"],
        ["artifact-store", "status"], ["artifact-store", "import", "--path", "evidence.txt"],
        ["artifact-store", "list"], ["artifact-store", "verify"],
        ["artifact-store", "materialize", "--digest", "a" * 64, "--output", "out.bin"],
        ["artifact-store", "migrate", "--path", "legacy"], ["artifact-store", "gc", "--apply"],
        ["correlate", "com.example.app", "--apk", "app.apk"],
        ["policy", "show"], ["policy", "check", "--role", "viewer", "--action", "devices"],
        ["policy", "set", "--role", "viewer", "--action", "devices", "--effect", "allow", "--approved"],
        ["policy", "delete", "--role", "viewer", "--action", "devices", "--approved"],
        ["audit", "list", "--limit", "10"], ["audit", "verify"],
        ["sbom", "--format", "cyclonedx", "--output", "sbom.json"],
        ["governance", "holds"], ["governance", "hold", "--project-id", "p", "--reason", "retain"],
        ["governance", "release", "--project-id", "p"],
        ["governance", "seal", "--path", "in", "--output", "out"],
        ["governance", "unseal", "--path", "in", "--output", "out"],
        ["plugin", "list"], ["plugin", "run", "demo", "--allow-permission", "read_device"],
        ["plugin", "keygen", "--private-key", "key", "--public-key", "key.pub"],
        ["plugin", "sign", "--manifest", "manifest.json", "--plugin-file", "plugin.py", "--private-key", "key", "--output", "sig.json"],
        ["plugin", "verify", "--bundle", "sig.json", "--plugin-file", "plugin.py", "--public-key", "key.pub"],
        ["plugin", "publisher-list"], ["plugin", "publisher-add", "publisher", "--public-key", "key.pub"],
        ["plugin", "publisher-revoke", "publisher"],
        ["plugin", "verify-trusted", "--bundle", "sig.json", "--plugin-file", "plugin.py", "--publisher", "publisher"],
        ["lab", "status"], ["lab", "agents"], ["lab", "pools"], ["lab", "pki-init", "--dir", "pki"],
        ["lab", "controller-cert", "--dir", "pki", "--host", "127.0.0.1"],
        ["lab", "agent-enroll", "agent-1", "--pki-dir", "pki", "--controller", "https://127.0.0.1:9443"],
        ["lab", "pool-create", "phones"], ["lab", "pool-add", "phones", "agent-1", "SERIAL"],
        ["lab", "jobs", "--limit", "10"],
        ["lab", "job-submit", "--agent", "agent-1", "--action", "devices", "--payload", "{}"],
        ["lab", "pool-submit", "--pool", "phones", "--action", "devices", "--payload", "{}"],
        ["lab", "job-cancel", "job_1"],
        ["lab", "controller", "--cert", "cert.pem", "--key", "key.pem", "--ca", "ca.pem"],
        ["lab", "agent-run", "--config", "agent.json", "--once"],
        ["update"], ["update", "force"], ["update", "check"], ["update", "plan"],
        ["update", "install", "--archive", "source.zip", "--checksum", "a" * 64], ["update", "rollback"],
        ["web-user", "list"], ["web-user", "add", "analyst", "--role", "user", "--password-env", "PW"],
        ["web-user", "reset-password", "analyst", "--password-env", "PW"],
        ["web-user", "disable", "analyst"], ["web-user", "enable", "analyst"],
        ["web-workspace", "list", "analyst"], ["web-workspace", "create", "analyst", "Assessment"],
    ]
    for argv in cases:
        parsed = parser.parse_args(argv)
        assert parsed.command is not None, argv


def test_operation_catalog_has_unique_valid_fields_and_defaults():
    assert OPERATIONS
    for name, operation in OPERATIONS.items():
        assert name == operation.name
        field_names = [field.name for field in operation.fields]
        assert len(field_names) == len(set(field_names)), name
        for field in operation.fields:
            assert field.field_type in {"text", "textarea", "select", "boolean", "number", "list", "file", "secret"}
            if field.choices and field.default is not None:
                assert field.default in field.choices, f"{name}.{field.name}"
            if field.minimum is not None and field.maximum is not None:
                assert field.minimum <= field.maximum, f"{name}.{field.name}"


def test_lab_user_json_errors_are_clean_adbgath_errors(tmp_path: Path):
    parser = build_parser()
    malformed = parser.parse_args(["lab", "job-submit", "--agent", "a", "--action", "devices", "--payload", "{"])
    with pytest.raises(AdbgathError, match="--payload must be valid JSON"):
        run(malformed)

    wrong_type = parser.parse_args(["lab", "pool-submit", "--pool", "p", "--action", "devices", "--payload", "[]"])
    with pytest.raises(AdbgathError, match="--payload must be a JSON object"):
        run(wrong_type)

    missing = parser.parse_args(["lab", "agent-run", "--config", str(tmp_path / "missing.json"), "--once"])
    with pytest.raises(AdbgathError, match="Unable to read Lab agent config"):
        run(missing)

    incomplete = tmp_path / "agent.json"
    incomplete.write_text('{"agent_id":"a"}', encoding="utf-8")
    bad_config = parser.parse_args(["lab", "agent-run", "--config", str(incomplete), "--once"])
    with pytest.raises(AdbgathError, match="missing required fields"):
        run(bad_config)


def test_authenticated_preset_buttons_are_capture_guarded_from_legacy_native_handlers():
    source = (STATIC / "presets371.js").read_text(encoding="utf-8")
    assert 'event.target?.closest?.("#savePreset")' in source
    assert 'event.target?.closest?.("#loadPreset")' in source
    assert 'event.target?.closest?.("#deletePreset")' in source
    assert "event.stopImmediatePropagation()" in source
    assert "openSaveDialog()" in source
    assert "loadSelectedPresetServer()" in source
    assert "deleteSelectedPresetServer()" in source


def test_enhanced_web_layers_use_custom_dialogs_not_native_alerts_or_prompts():
    for filename in ("ux371.js", "presets371.js", "app370.js", "dashboardpairing360.js", "integratedweb360.js", "lab360.js"):
        source = (STATIC / filename).read_text(encoding="utf-8")
        assert "alert(" not in source, filename
        assert "window.alert" not in source, filename
        assert "prompt(" not in source, filename
        assert "window.prompt" not in source, filename
