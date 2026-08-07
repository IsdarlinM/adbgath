from __future__ import annotations

import argparse
import time
import webbrowser
from pathlib import Path
from typing import Any


def _subcommands(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    raise RuntimeError("CLI subcommand registry was not found")


def _service(module: Any, args: argparse.Namespace):
    from .adb import AdbClient
    adb = AdbClient(args.adb_path) if getattr(args, "adb_path", None) else None
    return module.AdbgathService(adb, workspace=getattr(args, "workspace", None))


def patch_cli(module: Any) -> None:
    if getattr(module, "_adbgath_340_patched", False):
        return
    original_build = module.build_parser
    original_run = module.run

    def build_parser():
        parser = original_build()
        commands = _subcommands(parser)
        wireless = commands.get("wireless")
        if wireless:
            sub = next((a for a in wireless._actions if isinstance(a, argparse._SubParsersAction)), None)
            if sub and "qr" not in sub.choices:
                qr = sub.add_parser("qr", help="Pair Android Wireless Debugging using an ephemeral AOSP-compatible QR code.")
                qr.add_argument("--timeout", type=int, default=120)
                qr.add_argument("--output")
                qr.add_argument("--open", action="store_true")
                qr.add_argument("--keep", action="store_true")
                qr.add_argument("--no-auto-connect", action="store_true")
                broker = sub.add_parser("broker", help="Manage the shared wireless event broker.")
                broker.add_argument("broker_mode", choices=["status", "start", "stop"], default="status", nargs="?")
        inventory = commands.get("inventory")
        if inventory and not any(getattr(a, "dest", None) == "mode" for a in inventory._actions):
            inventory.add_argument("mode", nargs="?", choices=["export", "capture", "list", "diff", "watch"], default="export")
            inventory.add_argument("before", nargs="?")
            inventory.add_argument("after", nargs="?")
            inventory.add_argument("--name")
            inventory.add_argument("--limit", type=int, default=100)
            inventory.add_argument("--interval", type=int, default=10)
            inventory.add_argument("--duration", type=int, default=0)
        if "schema" not in commands:
            parser._subparsers._group_actions[0].add_parser("schema", help="Show SQLite migration and integrity status.")
        return parser

    def run(args):
        if args.command == "schema":
            return _service(module, args).store.schema_status()
        if args.command == "wireless" and args.wireless_mode in {"qr", "broker"}:
            service = _service(module, args)
            if args.wireless_mode == "broker":
                return {
                    "start": service.wireless_broker_start,
                    "stop": service.wireless_broker_stop,
                    "status": service.wireless_broker_status,
                }[args.broker_mode]()
            session = service.wireless_qr_create(
                ttl_seconds=args.timeout,
                auto_connect=not args.no_auto_connect,
            )
            target = service.qr_pairing.write_svg(session["id"], args.output)
            if args.open:
                webbrowser.open(target.as_uri())
            try:
                sequence = session["sequence"]
                while not session["terminal"]:
                    session = service.qr_pairing.wait(session["id"], after_sequence=sequence, timeout=2)
                    sequence = session["sequence"]
                return {**session, "qr_path": str(target)}
            finally:
                if not args.keep:
                    Path(target).unlink(missing_ok=True)
        if args.command == "inventory" and getattr(args, "mode", "export") != "export":
            service = _service(module, args)
            if args.mode == "capture":
                return service.inventory_capture(args.device, name=args.name, user=args.user)
            if args.mode == "list":
                return service.inventory_list(args.device, limit=args.limit)
            if args.mode == "diff":
                if not args.before or not args.after:
                    raise module.AdbgathError("inventory diff requires BEFORE and AFTER identifiers")
                return service.inventory_diff(args.before, args.after)
            if args.mode == "watch":
                return list(service.inventory_watch(args.device, interval=args.interval, duration=args.duration, user=args.user))
        return original_run(args)

    module.build_parser = build_parser
    module.run = run
    module._adbgath_340_patched = True
