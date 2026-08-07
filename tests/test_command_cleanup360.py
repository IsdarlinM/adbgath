from __future__ import annotations

import argparse

from adbgath import cli
from adbgath.core.operations import OPERATIONS


def _root_subparsers(parser: argparse.ArgumentParser) -> argparse._SubParsersAction:
    return next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))


def _parse(argv: list[str]):
    parser = cli.build_parser()
    return parser.parse_args(cli.normalize_legacy_args(argv))


def test_public_cli_has_one_canonical_route_per_capability():
    parser = cli.build_parser()
    choices = _root_subparsers(parser).choices
    for redundant in ("connect", "disconnect", "pair", "collect", "ls", "pull", "logcat"):
        assert redundant not in choices
    for canonical in ("wireless", "evidence", "list", "download", "logs"):
        assert canonical in choices


def test_global_preconnect_is_hidden_from_public_help_but_kept_for_compatibility():
    parser = cli.build_parser()
    action = next(item for item in parser._actions if getattr(item, "dest", None) == "connect_target")
    assert action.help is argparse.SUPPRESS
    assert "--connect" not in parser.format_help()


def test_legacy_wireless_commands_normalize_to_wireless_namespace():
    assert cli.normalize_legacy_args(["connect", "10.0.0.28:43005"]) == [
        "wireless", "connect", "10.0.0.28:43005"
    ]
    assert cli.normalize_legacy_args(["disconnect", "10.0.0.28:43005"]) == [
        "wireless", "disconnect", "10.0.0.28:43005"
    ]
    assert cli.normalize_legacy_args(["pair", "10.0.0.28:37123"]) == [
        "wireless", "pair", "10.0.0.28:37123"
    ]


def test_legacy_aliases_normalize_to_single_canonical_commands():
    assert cli.normalize_legacy_args(["ls", "packages"]) == ["list", "packages"]
    assert cli.normalize_legacy_args(["pull", "com.example.app"]) == ["download", "com.example.app"]
    assert cli.normalize_legacy_args(["logcat", "capture"]) == ["logs", "capture"]
    assert cli.normalize_legacy_args(["collect", "--output", "evidence"]) == [
        "evidence", "--output", "evidence"
    ]
    assert cli.normalize_legacy_args(["-C"]) == ["evidence"]


def test_legacy_and_canonical_wireless_parse_to_same_command():
    legacy = _parse(["connect", "10.0.0.28:43005"])
    canonical = _parse(["wireless", "connect", "10.0.0.28:43005"])
    assert legacy.command == canonical.command == "wireless"
    assert legacy.wireless_mode == canonical.wireless_mode == "connect"
    assert legacy.target == canonical.target == "10.0.0.28:43005"


def test_web_operation_catalog_removes_duplicate_routes():
    for redundant in ("connect", "disconnect", "collect"):
        assert redundant not in OPERATIONS
    for canonical in ("wireless_connect", "wireless_disconnect", "wireless_pair", "evidence"):
        assert canonical in OPERATIONS
