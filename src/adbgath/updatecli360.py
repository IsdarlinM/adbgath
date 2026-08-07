from __future__ import annotations

import argparse
from typing import Any


def _commands(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    raise RuntimeError("CLI subcommand registry was not found")


def patch_update_cli(module: Any) -> None:
    if getattr(module, "_adbgath_update_cli_360_patched", False):
        return
    original_build = module.build_parser

    def build_parser():
        parser = original_build()
        update = _commands(parser).get("update")
        if update is not None:
            for action in update._actions:
                if getattr(action, "dest", None) == "mode":
                    action.choices = ["auto", "force", "check", "plan", "install", "rollback"]
                    action.default = "auto"
                    action.help = (
                        "auto updates to the latest main commit; force reinstalls it even when already current; "
                        "check/plan/install/rollback keep the advanced updater workflow"
                    )
                    break
            update.description = (
                "Update ADB-Gath from the immutable current GitHub main commit. "
                "The managed updater preserves workspace, configuration, Platform-Tools and bundletool."
            )
        return parser

    module.build_parser = build_parser
    module._adbgath_update_cli_360_patched = True
