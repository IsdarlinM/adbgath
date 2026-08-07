from __future__ import annotations

from adbgath.cli import build_parser


def test_update_defaults_to_auto() -> None:
    args = build_parser().parse_args(["update"])
    assert args.command == "update"
    assert args.mode == "auto"


def test_update_force_is_supported() -> None:
    args = build_parser().parse_args(["update", "force"])
    assert args.command == "update"
    assert args.mode == "force"


def test_update_advanced_modes_remain_supported() -> None:
    parser = build_parser()
    for mode in ("check", "plan", "install", "rollback"):
        args = parser.parse_args(["update", mode])
        assert args.mode == mode
