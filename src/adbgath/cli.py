from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .errors import AdbgathError
from .service import AdbgathService

BANNER = r"""
╭──────────────────────────────────────────────────────────────────────────────╮
│  ADB-GATH  ::  Defensive Android Assessment Toolkit  ::  v{version:<8}       │
│  Cross-platform CLI + local security-focused web workspace                  │
╰──────────────────────────────────────────────────────────────────────────────╯
"""


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _read_lines(path: str | None) -> list[str]:
    if not path:
        return []
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise AdbgathError(f"Input file does not exist: {source}")
    values: list[str] = []
    for raw in source.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            values.append(line)
    return values


def _replacement_pairs(path: str | None) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for line in _read_lines(path):
        values = shlex.split(line, posix=os.name != "nt")
        if len(values) != 2:
            raise AdbgathError("Replacement input lines must use: APK_FILE PACKAGE_NAME")
        apk, package = values
        pairs.append((package, apk))
    return pairs


def _print(value: Any, *, as_json: bool = False) -> None:
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    if as_json or isinstance(value, (dict, list)):
        print(json.dumps(value, indent=2, ensure_ascii=False, default=str))
    else:
        print(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adbgath",
        description="Cross-platform defensive ADB toolkit for authorized Android testing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Use 'adbgath <command> -h' for command-specific help.",
    )
    parser.add_argument("--version", action="version", version=f"adbgath {__version__}")
    parser.add_argument("--adb-path", help="Path to adb/adb.exe. Overrides PATH discovery.")
    parser.add_argument("--workspace", help="Workspace used for reports and downloaded artifacts.")
    parser.add_argument(
        "--device",
        "-D",
        "-s",
        dest="device",
        default=os.environ.get("DEVICE_ID"),
        help="ADB device serial.",
    )
    parser.add_argument(
        "--user",
        "--profile",
        "-u",
        default=os.environ.get("USER_ID"),
        help="Android user/profile ID, current, or owner.",
    )
    parser.add_argument("--connect", dest="connect_target", help="Connect to HOST:PORT before the selected operation.")
    parser.add_argument("--output", "-o", dest="global_output", default=os.environ.get("OUTPUT_DIR"))
    parser.add_argument("--file", "-f", dest="global_file", help="Read command input from a UTF-8 text file.")
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=os.environ.get("VERBOSE", "").lower() in {"1", "true", "yes"},
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--no-banner", action="store_true", help="Suppress the startup banner.")

    commands = parser.add_subparsers(dest="command")

    commands.add_parser("devices", help="List connected ADB devices and root status.")
    connect = commands.add_parser("connect", help="Connect to a wireless ADB endpoint.")
    connect.add_argument("target", help="HOST:PORT")
    disconnect = commands.add_parser("disconnect", help="Disconnect a wireless ADB endpoint.")
    disconnect.add_argument("target", help="HOST:PORT")

    list_cmd = commands.add_parser("list", aliases=["ls"], help="List users, packages, or APK paths.")
    list_cmd.add_argument("kind", choices=["users", "packages", "paths"])
    list_cmd.add_argument("--package")
    list_cmd.add_argument("--include-paths", action="store_true")
    list_cmd.add_argument("--system", choices=["all", "system", "third-party"], default="all")

    download = commands.add_parser("download", aliases=["pull"], help="Download APKs from a device.")
    download.add_argument("items", nargs="*", help="Package names or absolute remote APK paths.")
    download.add_argument("--packages", help="Comma-separated package names.")
    download.add_argument("--paths", help="Comma-separated absolute remote paths.")
    download.add_argument("--output", "-o")
    download.add_argument("--file", "-f", dest="input_file")

    install = commands.add_parser("install", help="Install one or more APK files.")
    install.add_argument("files", nargs="*")
    install.add_argument("--file", "-f", dest="input_file")
    install.add_argument("--replace", action="store_true")
    install.add_argument("--grant-runtime-permissions", action="store_true")

    uninstall = commands.add_parser("uninstall", help="Uninstall one or more packages.")
    uninstall.add_argument("packages", nargs="*")
    uninstall.add_argument("--file", "-f", dest="input_file")
    uninstall.add_argument("--keep-data", action="store_true")

    replace = commands.add_parser("replace", help="Uninstall a package, then install a replacement APK.")
    replace.add_argument("package", nargs="?")
    replace.add_argument("apk", nargs="?")
    replace.add_argument("--file", "-f", dest="input_file")

    info = commands.add_parser("info", help="Collect basic, system, network, or security information.")
    info.add_argument("mode", nargs="?", default="basic", choices=["basic", "system", "network", "security", "all"])

    app = commands.add_parser("app", help="Inspect an installed package and permissions.")
    app.add_argument("package")

    runtime = commands.add_parser("runtime", help="Inspect processes, activities, or services.")
    runtime.add_argument(
        "mode", nargs="?", default="summary", choices=["summary", "processes", "activities", "services"]
    )
    runtime.add_argument("--package")

    logs = commands.add_parser("logs", aliases=["logcat"], help="Capture, stream, or clear logcat.")
    logs.add_argument("mode", nargs="?", default="listen", choices=["listen", "capture", "clear"])
    logs.add_argument("--package")
    logs.add_argument("--pid", type=int)
    logs.add_argument("--regex", "--grep")
    logs.add_argument("--filter", dest="filters", action="append", default=[])
    logs.add_argument("--duration", type=int, default=30)
    logs.add_argument("--output", "-o")
    logs.add_argument("--clear-first", "--clear-logs", action="store_true")
    logs.add_argument("--format", default="threadtime")

    sniff = commands.add_parser("sniff", help="Inspect interfaces or capture rooted device traffic.")
    sniff.add_argument("mode", choices=["interfaces", "capture", "push-tcpdump"])
    sniff.add_argument("value", nargs="?", help="Optional tcpdump path for push-tcpdump.")
    sniff.add_argument("--interface", default="wlan0")
    sniff.add_argument("--duration", type=int, default=30)
    sniff.add_argument("--output", "-o")
    sniff.add_argument("--file")

    proxy = commands.add_parser("proxy", help="Show, set, or clear the Android global HTTP proxy.")
    proxy.add_argument("mode", choices=["show", "set", "clear"])
    proxy.add_argument("spec", nargs="?")

    forward = commands.add_parser("forward", help="Create ADB forward/reverse TCP mappings.")
    forward.add_argument("mode", choices=["forward", "reverse"])
    forward.add_argument("local_port", type=int)
    forward.add_argument("remote_port", type=int)

    backup = commands.add_parser("backup", help="Create a run-as app data archive for debuggable apps.")
    backup.add_argument("package")
    backup.add_argument("--output", "-o")

    content = commands.add_parser("content", help="List content providers from package manager state.")
    content.add_argument("--package")

    frida = commands.add_parser("frida", help="Use optional frida-tools against the selected device.")
    frida.add_argument("mode", nargs="?", default="ps", choices=["ps", "attach", "spawn"])
    frida.add_argument("--package")
    frida.add_argument("--script")

    static = commands.add_parser("static", help="Perform local APK metadata/hash analysis.")
    static.add_argument("apk")
    static.add_argument("--output", "-o")

    security = commands.add_parser("security", help="Run defensive device posture checks and write reports.")
    security.add_argument("--output", "-o")

    collect = commands.add_parser("collect", help="Collect device, package, runtime, and network evidence.")
    collect.add_argument("--output", "-o")

    mastg = commands.add_parser("mastg", help="Create an OWASP MASTG-oriented evidence bundle.")
    mastg.add_argument("--output", "-o")

    inventory = commands.add_parser("inventory", help="Export a device and application inventory.")
    inventory.add_argument("--output", "-o")

    commands.add_parser("doctor", help="Validate Python, ADB, and optional tools.")

    web = commands.add_parser("web", help="Start the local web interface.")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--no-browser", action="store_true")

    return parser


def normalize_legacy_args(argv: list[str]) -> list[str]:
    """Translate common v2 Bash flags into v3 subcommands."""
    if not argv:
        return argv
    known_commands = {
        "devices",
        "connect",
        "disconnect",
        "list",
        "ls",
        "download",
        "pull",
        "install",
        "uninstall",
        "replace",
        "info",
        "app",
        "runtime",
        "logs",
        "logcat",
        "sniff",
        "proxy",
        "forward",
        "backup",
        "content",
        "frida",
        "static",
        "security",
        "collect",
        "mastg",
        "inventory",
        "doctor",
        "web",
    }
    if any(token in known_commands for token in argv):
        return argv
    mappings = {
        "--devices": ("devices", 0),
        "-d": ("download", 0),
        "--download": ("download", 0),
        "-I": ("install", 0),
        "--install": ("install", 0),
        "-U": ("uninstall", 0),
        "--uninstall": ("uninstall", 0),
        "-R": ("replace", 0),
        "--replace": ("replace", 0),
        "-C": ("collect", 0),
        "--collect": ("collect", 0),
        "-l": ("list", 1),
        "--list": ("list", 1),
        "-i": ("info", 1),
        "--info": ("info", 1),
    }
    for index, token in enumerate(argv):
        if token not in mappings:
            continue
        command, takes_value = mappings[token]
        prefix = argv[:index]
        suffix = argv[index + 1 :]
        if takes_value and suffix:
            return prefix + [command, suffix[0]] + suffix[1:]
        return prefix + [command] + suffix
    return argv


def run(args: argparse.Namespace) -> Any:
    if args.command == "web":
        from .webapp import serve

        serve(host=args.host, port=args.port, open_browser=not args.no_browser, workspace=args.workspace)
        return None

    from .adb import AdbClient

    service = AdbgathService(
        AdbClient(args.adb_path) if args.adb_path else None,
        workspace=args.workspace,
    )
    serial = args.device
    user = args.user
    command = args.command
    output = getattr(args, "output", None) or args.global_output
    input_file = getattr(args, "input_file", None) or args.global_file
    connect_result = None
    if args.connect_target:
        connect_result = service.connect(args.connect_target)
        serial = serial or args.connect_target
    if command is None and connect_result is not None:
        return connect_result
    if args.verbose:
        print(
            f"[debug] workspace={service.workspace} device={serial or 'auto'} user={user or 'unspecified'}",
            file=sys.stderr,
        )
    if command == "devices":
        return service.devices()
    if command == "connect":
        return service.connect(args.target)
    if command == "disconnect":
        return service.disconnect(args.target)
    if command in {"list", "ls"}:
        if args.kind == "users":
            return service.list_users(serial)
        if args.kind == "paths":
            return (
                service.package_paths(serial, args.package)
                if args.package
                else service.list_apk_paths(serial, user=user)
            )
        system = None if args.system == "all" else args.system == "system"
        return service.list_packages(serial, user=user, include_paths=args.include_paths, system=system)
    if command in {"download", "pull"}:
        packages = _csv(args.packages)
        paths = _csv(args.paths)
        for item in [*args.items, *_read_lines(input_file)]:
            (paths if item.startswith("/") else packages).append(item)
        return service.pull_apks(serial, packages=packages, remote_paths=paths, output=output, user=user)
    if command == "install":
        return service.install_apks(
            serial,
            [*args.files, *_read_lines(input_file)],
            user=user,
            replace_existing=args.replace,
            grant_runtime_permissions=args.grant_runtime_permissions,
        )
    if command == "uninstall":
        return service.uninstall_packages(
            serial, [*args.packages, *_read_lines(input_file)], user=user, keep_data=args.keep_data
        )
    if command == "replace":
        pairs = _replacement_pairs(input_file)
        if args.package or args.apk:
            if not args.package or not args.apk:
                raise AdbgathError("replace requires PACKAGE APK, or --file with APK_FILE PACKAGE_NAME pairs.")
            pairs.insert(0, (args.package, args.apk))
        if not pairs:
            raise AdbgathError("replace requires PACKAGE APK, or --file with replacement pairs.")
        return [service.replace_app(serial, package, apk, user=user).to_dict() for package, apk in pairs]
    if command == "info":
        return service.info(serial, args.mode)
    if command == "app":
        return service.app_summary(serial, args.package)
    if command == "runtime":
        return service.runtime(serial, args.mode, args.package)
    if command in {"logs", "logcat"}:
        if args.mode == "clear":
            return service.logs_clear(serial)
        if args.mode == "listen":
            for line in service.logs_stream(
                serial, package=args.package, pid=args.pid, regex=args.regex, log_format=args.format
            ):
                print(line)
            return None
        return service.logs_capture(
            serial,
            output=output,
            duration=args.duration,
            package=args.package,
            pid=args.pid,
            regex=args.regex,
            clear=args.clear_first,
            log_format=args.format,
            filters=args.filters,
        )
    if command == "sniff":
        if args.mode == "interfaces":
            return service.sniff_interfaces(serial)
        if args.mode == "push-tcpdump":
            binary = args.file or args.value or input_file
            if not binary:
                raise AdbgathError("sniff push-tcpdump requires a file path.")
            return service.push_tcpdump(serial, binary)
        return service.sniff_capture(serial, interface=args.interface, output=output, duration=args.duration)
    if command == "proxy":
        return service.proxy(serial, args.mode, args.spec)
    if command == "forward":
        return service.port_forward(serial, mode=args.mode, local_port=args.local_port, remote_port=args.remote_port)
    if command == "backup":
        return service.backup(serial, args.package, output=output)
    if command == "content":
        return service.content_providers(serial, args.package)
    if command == "frida":
        return service.frida(serial, args.mode, args.package, args.script)
    if command == "static":
        return service.static_analyze(args.apk, output=output)
    if command == "security":
        return service.security_audit(serial, output=output)
    if command == "collect":
        return service.collect(serial, output=output)
    if command == "mastg":
        return service.mastg_collect(serial, output=output)
    if command == "inventory":
        return service.inventory(serial, output=output)
    if command == "doctor":
        return service.doctor()
    raise AdbgathError(f"Unknown command: {command}")


def interactive(parser: argparse.ArgumentParser) -> int:
    print(BANNER.format(version=__version__))
    print("Interactive mode. Type 'help', 'web', or 'exit'.")
    while True:
        try:
            line = input("adbgath> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line in {"exit", "quit", "q"}:
            return 0
        if line in {"help", "?"}:
            parser.print_help()
            continue
        try:
            argv = normalize_legacy_args(shlex.split(line, posix=os.name != "nt"))
            args = parser.parse_args(argv)
            result = run(args)
            if result is not None:
                _print(result, as_json=args.json)
        except SystemExit:
            continue
        except AdbgathError as exc:
            print(f"Error: {exc}", file=sys.stderr)
        except Exception as exc:  # defensive CLI boundary
            print(f"Unexpected error: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    raw = list(sys.argv[1:] if argv is None else argv)
    if not raw:
        return interactive(parser)
    try:
        args = parser.parse_args(normalize_legacy_args(raw))
        if not args.no_banner and args.command not in {"web"}:
            print(BANNER.format(version=__version__))
        result = run(args)
        if result is not None:
            _print(result, as_json=args.json)
        return 0
    except AdbgathError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
