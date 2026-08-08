from __future__ import annotations

import argparse
import getpass
import os
from typing import Any

from .core.auth370 import AuthStore


def _root_subparsers(parser: argparse.ArgumentParser) -> argparse._SubParsersAction:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    raise RuntimeError("CLI subcommand registry was not found")


def _password(env_name: str | None, *, confirm: bool = True) -> str:
    if env_name:
        value = os.environ.get(env_name)
        if value is None:
            raise ValueError(f"Environment variable {env_name} is not set.")
        return value
    first = getpass.getpass("Password: ")
    if confirm:
        second = getpass.getpass("Confirm password: ")
        if first != second:
            raise ValueError("Passwords do not match.")
    return first


def patch_cli(module: Any) -> None:
    if getattr(module, "_adbgath_370_auth_cli_patched", False):
        return
    original_build = module.build_parser
    original_run = module.run

    def build_parser():
        parser = original_build()
        root = _root_subparsers(parser)
        if "web-user" not in root.choices:
            command = root.add_parser("web-user", help="Manage ADB-Gath Web users and administrator access.")
            sub = command.add_subparsers(dest="web_user_mode", required=True)
            sub.add_parser("list", help="List Web users.")
            add = sub.add_parser("add", help="Create a Web user with an isolated default workspace.")
            add.add_argument("username")
            add.add_argument("--display-name")
            add.add_argument("--role", choices=["user", "administrator"], default="user")
            add.add_argument("--password-env", help="Read the initial password from this environment variable instead of prompting.")
            reset = sub.add_parser("reset-password", help="Reset a Web user's password and revoke existing sessions.")
            reset.add_argument("username")
            reset.add_argument("--password-env")
            disable = sub.add_parser("disable", help="Disable a Web user and revoke existing sessions.")
            disable.add_argument("username")
            enable = sub.add_parser("enable", help="Enable a Web user.")
            enable.add_argument("username")

        if "web-workspace" not in root.choices:
            command = root.add_parser("web-workspace", help="Inspect or create per-user Web workspaces.")
            sub = command.add_subparsers(dest="web_workspace_mode", required=True)
            listing = sub.add_parser("list", help="List workspaces owned by a Web user.")
            listing.add_argument("username")
            create = sub.add_parser("create", help="Create an additional workspace for a Web user.")
            create.add_argument("username")
            create.add_argument("name")
        return parser

    def run(args):
        try:
            if args.command == "web-user":
                store = AuthStore()
                mode = args.web_user_mode
                if mode == "list":
                    return store.list_users()
                user = store.find_user(args.username) if mode != "add" else None
                if mode == "add":
                    if not store.has_users() and args.role != "administrator":
                        raise ValueError("The first Web user must be created with --role administrator.")
                    return store.create_user(
                        args.username,
                        _password(args.password_env),
                        role=args.role,
                        display_name=args.display_name,
                    )
                if mode == "reset-password":
                    store.reset_password(user["id"], _password(args.password_env))
                    return {"ok": True, "username": user["username"], "sessions_revoked": True}
                if mode == "disable":
                    return store.set_user_disabled(user["id"], True)
                if mode == "enable":
                    return store.set_user_disabled(user["id"], False)
            if args.command == "web-workspace":
                store = AuthStore()
                user = store.find_user(args.username)
                if args.web_workspace_mode == "list":
                    return store.list_workspaces(user["id"])
                if args.web_workspace_mode == "create":
                    return store.create_workspace(user["id"], args.name)
        except KeyError as exc:
            raise module.AdbgathError(f"Web user or workspace was not found: {exc.args[0]}") from exc
        except ValueError as exc:
            raise module.AdbgathError(str(exc)) from exc
        return original_run(args)

    module.build_parser = build_parser
    module.run = run
    module._adbgath_370_auth_cli_patched = True
