from __future__ import annotations

import argparse
from typing import Any

# Public CLI surface: one canonical route for each capability.
_REMOVED_TOP_LEVEL = {"connect", "disconnect", "pair", "collect"}
_HIDDEN_ALIASES = {"ls", "pull", "logcat"}
_CANONICAL = {
    "connect": ("wireless", "connect"),
    "disconnect": ("wireless", "disconnect"),
    "pair": ("wireless", "pair"),
    "collect": ("evidence",),
    "ls": ("list",),
    "pull": ("download",),
    "logcat": ("logs",),
}
_WEB_REDUNDANT = {"connect", "disconnect", "collect"}
_GLOBAL_OPTIONS_WITH_VALUE = {
    "--adb-path",
    "--workspace",
    "--device",
    "-D",
    "-s",
    "--user",
    "--profile",
    "-u",
    "--connect",  # hidden compatibility option; use `wireless connect` for new scripts
    "--output",
    "-o",
    "--file",
    "-f",
}


def _root_subparsers(parser: argparse.ArgumentParser) -> argparse._SubParsersAction:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    raise RuntimeError("CLI subcommand registry was not found")


def _command_index(argv: list[str]) -> int | None:
    """Return the first command token while skipping known global options safely."""
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--":
            return index + 1 if index + 1 < len(argv) else None
        if token in _GLOBAL_OPTIONS_WITH_VALUE:
            index += 2
            continue
        if any(token.startswith(f"{name}=") for name in _GLOBAL_OPTIONS_WITH_VALUE if name.startswith("--")):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        return index
    return None


def patch_operations(module: Any) -> None:
    """Remove duplicate Web operation entries while keeping service internals intact."""
    if getattr(module, "_adbgath_command_cleanup_360_patched", False):
        return
    for name in _WEB_REDUNDANT:
        module.OPERATIONS.pop(name, None)
    module.WEB_ACTIONS = frozenset(module.OPERATIONS)
    module._adbgath_command_cleanup_360_patched = True


def patch_cli(module: Any) -> None:
    """Expose only canonical commands while preserving hidden legacy compatibility."""
    if getattr(module, "_adbgath_command_cleanup_360_patched", False):
        return

    original_build = module.build_parser
    original_normalize = module.normalize_legacy_args

    def normalize_legacy_args(argv: list[str]) -> list[str]:
        normalized = list(original_normalize(list(argv)))
        index = _command_index(normalized)
        if index is None:
            return normalized
        replacement = _CANONICAL.get(normalized[index])
        if replacement:
            return normalized[:index] + list(replacement) + normalized[index + 1 :]
        return normalized

    def build_parser() -> argparse.ArgumentParser:
        parser = original_build()
        subparsers = _root_subparsers(parser)

        # Remove duplicate public command routes. Legacy spellings are translated
        # by normalize_legacy_args before argparse sees them.
        for name in _REMOVED_TOP_LEVEL | _HIDDEN_ALIASES:
            subparsers.choices.pop(name, None)

        # argparse stores help pseudo-actions separately from the choice map.
        subparsers._choices_actions = [
            action for action in subparsers._choices_actions if action.dest not in _REMOVED_TOP_LEVEL
        ]
        for action in subparsers._choices_actions:
            if action.dest in {"list", "download", "logs"}:
                action.metavar = action.dest

        # Keep the historical pre-connect option accepted for old scripts, but
        # remove it from the public help. New workflows use `wireless connect`.
        for action in parser._actions:
            if getattr(action, "dest", None) == "connect_target":
                action.help = argparse.SUPPRESS
                break

        return parser

    module.normalize_legacy_args = normalize_legacy_args
    module.build_parser = build_parser
    module._adbgath_command_cleanup_360_patched = True
