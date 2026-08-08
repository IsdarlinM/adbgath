from __future__ import annotations

from adbgath.cli import build_parser


def test_370_web_admin_commands_parse():
    parser = build_parser()
    add = parser.parse_args(["web-user", "add", "analyst370", "--role", "user", "--password-env", "TEST_PASSWORD"])
    assert add.command == "web-user"
    assert add.web_user_mode == "add"
    assert add.username == "analyst370"
    assert add.role == "user"

    listing = parser.parse_args(["web-user", "list"])
    assert listing.web_user_mode == "list"

    workspace = parser.parse_args(["web-workspace", "create", "analyst370", "Mobile Lab"])
    assert workspace.command == "web-workspace"
    assert workspace.web_workspace_mode == "create"
    assert workspace.name == "Mobile Lab"
