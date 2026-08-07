from __future__ import annotations

import argparse
import getpass
import sys
import time
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


def _pairing_code() -> str:
    if sys.stdin.isatty():
        return getpass.getpass("Pairing code: ").strip()
    return sys.stdin.readline().strip()


def patch_cli(module: Any) -> None:
    original_build_parser = module.build_parser
    original_run = module.run

    def build_parser() -> argparse.ArgumentParser:
        parser = original_build_parser()
        commands = _subcommands(parser)

        devices = commands["devices"]
        if not any(getattr(action, "dest", None) == "fast" for action in devices._actions):
            devices.add_argument("--fast", action="store_true", help="Skip secondary device probes.")
            devices.add_argument("--no-details", action="store_true", help="Do not probe root details.")
            devices.add_argument("--watch", action="store_true", help="Watch device state for a bounded duration.")
            devices.add_argument("--interval", type=int, default=2)
            devices.add_argument("--duration", type=int, default=30)

        if "pair" not in commands:
            pair = parser._subparsers._group_actions[0].add_parser(
                "pair", help="Pair Android Wireless Debugging using the six-digit code workflow."
            )
            pair.add_argument("target", help="Temporary pairing HOST:PORT shown by Android.")

        if "wireless" not in commands:
            wireless = parser._subparsers._group_actions[0].add_parser(
                "wireless", help="Discover, pair, connect, diagnose, and manage Wireless Debugging."
            )
            sub = wireless.add_subparsers(dest="wireless_mode", required=True)
            status = sub.add_parser("status")
            status.add_argument("--no-discover", action="store_true")
            discover = sub.add_parser("discover")
            discover.add_argument("--legacy", action="store_true", help="Use legacy adb mdns services output.")
            pair = sub.add_parser("pair")
            pair.add_argument("target", help="Temporary pairing HOST:PORT.")
            connect = sub.add_parser("connect")
            connect.add_argument("target", help="Post-pairing connection HOST:PORT.")
            disconnect = sub.add_parser("disconnect")
            disconnect.add_argument("target")
            sub.add_parser("auto-connect")
            diagnose = sub.add_parser("diagnose")
            diagnose.add_argument("--fix", action="store_true")
            diagnose.add_argument("--persist", action="store_true")
            sub.add_parser("known")
            forget = sub.add_parser("forget")
            forget.add_argument("identifier")
            alias = sub.add_parser("alias")
            alias.add_argument("identifier")
            alias.add_argument("alias")
            tcpip = sub.add_parser("tcpip")
            tcpip.add_argument("--port", type=int, default=5555)
            watch = sub.add_parser("watch")
            watch.add_argument("--interval", type=int, default=3)
            watch.add_argument("--duration", type=int, default=0)

        if "metrics" not in commands:
            metrics = parser._subparsers._group_actions[0].add_parser(
                "metrics", help="Review local ADB performance metrics."
            )
            metrics.add_argument("mode", nargs="?", choices=["summary", "list", "clear"], default="summary")
            metrics.add_argument("--limit", type=int, default=200)
        return parser

    def run(args: argparse.Namespace):
        command = args.command
        if command not in {"pair", "wireless", "metrics"} and not (
            command == "devices" and any(getattr(args, name, False) for name in ("fast", "no_details", "watch"))
        ):
            return original_run(args)

        service = _service(module, args)
        if command == "pair":
            return service.wireless_pair(args.target, _pairing_code())
        if command == "metrics":
            return service.metrics(args.mode, limit=args.limit)
        if command == "devices":
            if not args.watch:
                return service.devices(fast=args.fast, details=not args.no_details)
            deadline = time.monotonic() + max(1, args.duration)
            snapshots = []
            while time.monotonic() < deadline:
                snapshots.append(
                    {
                        "timestamp": time.time(),
                        "devices": service.devices(fast=args.fast, details=not args.no_details),
                    }
                )
                time.sleep(max(1, args.interval))
            return snapshots

        mode = args.wireless_mode
        if mode == "status":
            return service.wireless_status(discover=not args.no_discover)
        if mode == "discover":
            return service.wireless_discover(refresh=True, detailed=not args.legacy)
        if mode == "pair":
            return service.wireless_pair(args.target, _pairing_code())
        if mode == "connect":
            return service.connect(args.target)
        if mode == "disconnect":
            return service.disconnect(args.target)
        if mode == "auto-connect":
            return service.wireless_auto_connect()
        if mode == "diagnose":
            return service.wireless_diagnose(fix=args.fix, persist=args.persist)
        if mode == "known":
            return service.wireless_known()
        if mode == "forget":
            return service.wireless_forget(args.identifier)
        if mode == "alias":
            return service.wireless_alias(args.identifier, args.alias)
        if mode == "tcpip":
            return service.wireless_tcpip(args.device, args.port)
        if mode == "watch":
            return list(service.wireless_watch(interval=args.interval, duration=args.duration))
        raise module.AdbgathError(f"Unsupported wireless mode: {mode}")

    module.build_parser = build_parser
    module.run = run
