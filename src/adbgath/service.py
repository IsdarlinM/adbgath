from __future__ import annotations

import contextlib
import json
import os
import platform
import re
import shutil
import subprocess
import time
import zipfile
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .adb import AdbClient, UnavailableAdbClient
from .core.capabilities import CapabilityDetector
from .core.diffing import diff_values
from .core.evidence import EvidenceManifest, Redactor
from .core.files import atomic_write_json, atomic_write_text, collision_safe_path, sha256_file
from .core.operations import WEB_ACTIONS
from .core.reports import write_report
from .core.storage import ProjectStore
from .core.updater import SecureUpdater
from .errors import AdbgathError, CommandExecutionError, DependencyError, ValidationError
from .frida import SCRIPT_CATALOG
from .models import AppPackage, CommandResult
from .modules.apk import ApkInspector, BundletoolManager, discover_apk_set, validate_apk_set
from .plugins import KNOWN_PERMISSIONS, PluginContext, describe_plugin, discover_plugins
from .rules import engine as rule_engine
from .rules.builtin import device as _builtin_device_rules  # noqa: F401
from .validation import (
    safe_local_path,
    validate_host_port,
    validate_interface,
    validate_package,
    validate_positive_int,
    validate_remote_path,
    validate_user,
)

PACKAGE_LINE_RE = re.compile(r"^package:(?P<path>.+?)=(?P<package>[A-Za-z0-9_.]+)$")
USER_LINE_RE = re.compile(r"UserInfo\{(?P<id>\d+):(?P<name>[^:}]+)")
LOG_FORMATS = frozenset({"brief", "long", "process", "raw", "tag", "thread", "threadtime", "time", "year", "zone"})


class AdbgathService:
    """Cross-platform business logic shared by CLI and web UI."""

    def __init__(
        self,
        adb: AdbClient | None = None,
        *,
        workspace: str | Path | None = None,
    ) -> None:
        if adb is not None:
            self.adb = adb
        else:
            try:
                self.adb = AdbClient()
            except DependencyError as exc:
                self.adb = UnavailableAdbClient(str(exc))
        self.workspace = (
            Path(workspace or os.environ.get("ADBGATH_WORKSPACE", Path.home() / "adbgath-workspace"))
            .expanduser()
            .resolve()
        )
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.store = ProjectStore(self.workspace / "adbgath.db")
        self.capability_detector = CapabilityDetector(self.adb)
        self.apk_inspector = ApkInspector()
        self.plugins = discover_plugins()
        self.redactor = Redactor()

    def _serial(self, serial: str | None) -> str:
        return self.adb.require_device(serial)

    def _explicit_serial(self, serial: str | None) -> str:
        if not serial:
            raise ValidationError("This operation requires an explicit --device selection.")
        return self.adb.require_device(serial)

    @staticmethod
    def _user_args(user: str | int | None) -> list[str]:
        selected = validate_user(user)
        if not selected:
            return []
        if selected in {"owner", "primary"}:
            selected = "0"
        return ["--user", selected]

    def devices(self) -> list[dict[str, Any]]:
        devices = self.adb.devices()
        for device in devices:
            if device.state == "device":
                try:
                    root_check = self.adb.run(
                        ["shell", "su", "-c", "id"],
                        serial=device.serial,
                        timeout=5,
                        check=False,
                    )
                    device.rooted = root_check.ok and "uid=0" in root_check.stdout
                except AdbgathError:
                    device.rooted = None
        return [device.to_dict() for device in devices]

    def connect(self, target: str) -> CommandResult:
        return self.adb.run(["connect", validate_host_port(target)], timeout=30)

    def disconnect(self, target: str) -> CommandResult:
        return self.adb.run(["disconnect", validate_host_port(target)], timeout=30)

    def list_users(self, serial: str | None) -> list[dict[str, str]]:
        serial = self._serial(serial)
        result = self.adb.run(["shell", "pm", "list", "users"], serial=serial)
        users: list[dict[str, str]] = []
        for line in result.stdout.splitlines():
            match = USER_LINE_RE.search(line)
            if match:
                users.append({"id": match.group("id"), "name": match.group("name")})
        return users

    def resolve_user(self, serial: str, user: str | int | None) -> str | None:
        selected = validate_user(user)
        if not selected:
            return None
        if selected == "current":
            result = self.adb.run(["shell", "am", "get-current-user"], serial=serial)
            selected = result.stdout.strip()
        if selected in {"owner", "primary"}:
            selected = "0"
        if not selected.isdigit():
            raise ValidationError("Unable to resolve Android user/profile.")
        known = {item["id"] for item in self.list_users(serial)}
        if known and selected not in known:
            raise ValidationError(f"Android user/profile {selected} was not found on the device.")
        return selected

    def list_packages(
        self,
        serial: str | None,
        *,
        user: str | int | None = None,
        include_paths: bool = False,
        system: bool | None = None,
    ) -> list[dict[str, Any]]:
        serial = self._serial(serial)
        selected_user = self.resolve_user(serial, user)
        args = ["shell", "pm", "list", "packages"]
        if include_paths:
            args.append("-f")
        if system is True:
            args.append("-s")
        elif system is False:
            args.append("-3")
        if selected_user is not None:
            args.extend(["--user", selected_user])
        result = self.adb.run(args, serial=serial, timeout=120)
        packages: list[AppPackage] = []
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line.startswith("package:"):
                continue
            payload = line[8:]
            if "=" in payload and include_paths:
                path, package = payload.rsplit("=", 1)
                packages.append(AppPackage(package, [path]))
            else:
                packages.append(AppPackage(payload))
        return [package.to_dict() for package in packages]

    def package_paths(self, serial: str | None, package: str) -> list[str]:
        serial = self._serial(serial)
        package = validate_package(package)
        result = self.adb.run(["shell", "pm", "path", package], serial=serial)
        paths = [line.removeprefix("package:").strip() for line in result.stdout.splitlines()]
        return [path for path in paths if path]

    def list_apk_paths(
        self,
        serial: str | None,
        *,
        user: str | int | None = None,
    ) -> list[dict[str, Any]]:
        return self.list_packages(serial, user=user, include_paths=True)

    def pull_apks(
        self,
        serial: str | None,
        *,
        packages: Iterable[str] = (),
        remote_paths: Iterable[str] = (),
        output: str | Path | None = None,
        user: str | int | None = None,
    ) -> CommandResult:
        serial = self._serial(serial)
        output_dir = safe_local_path(output or self.workspace / "apks")
        output_dir.mkdir(parents=True, exist_ok=True)
        requested_paths = [validate_remote_path(path) for path in remote_paths]
        requested_packages = [validate_package(package) for package in packages]
        if not requested_paths and not requested_packages:
            listed = self.list_packages(serial, user=user, include_paths=True)
            for item in listed:
                requested_paths.extend(item.get("apk_paths", []))
        for package in requested_packages:
            requested_paths.extend(self.package_paths(serial, package))
        if not requested_paths:
            raise ValidationError("No APK paths were resolved for download.")

        artifacts: list[str] = []
        stdout: list[str] = []
        for remote in dict.fromkeys(requested_paths):
            remote = validate_remote_path(remote)
            package_hint = Path(remote).parent.name or "apk"
            destination = output_dir / f"{package_hint}-{Path(remote).name}"
            result = self.adb.run(["pull", remote, str(destination)], serial=serial, timeout=600)
            stdout.append(result.stdout.strip())
            artifacts.append(str(destination))
        return CommandResult(
            ok=True,
            command=[str(self.adb.adb_path), "-s", serial, "pull", "<multiple>"],
            stdout="\n".join(item for item in stdout if item),
            artifacts=artifacts,
            metadata={"count": len(artifacts), "output": str(output_dir)},
        )

    def install_apks(
        self,
        serial: str | None,
        apk_files: Iterable[str | Path],
        *,
        user: str | int | None,
        replace_existing: bool = False,
        grant_runtime_permissions: bool = False,
    ) -> CommandResult:
        serial = self._explicit_serial(serial)
        selected_user = self.resolve_user(serial, user)
        if selected_user is None:
            raise ValidationError("Install requires an explicit Android user/profile.")
        files = [safe_local_path(path, must_exist=True) for path in apk_files]
        if not files:
            raise ValidationError("At least one APK file is required.")
        stdout: list[str] = []
        for apk in files:
            if apk.suffix.lower() != ".apk":
                raise ValidationError(f"Unsupported Android package file: {apk.name}. Expected an .apk file.")
            args = ["install"]
            if replace_existing:
                args.append("-r")
            if grant_runtime_permissions:
                args.append("-g")
            args.extend(["--user", selected_user, str(apk)])
            result = self.adb.run(args, serial=serial, timeout=600)
            stdout.append(result.stdout.strip())
        return CommandResult(
            ok=True,
            command=[str(self.adb.adb_path), "-s", serial, "install", "<multiple>"],
            stdout="\n".join(stdout),
            metadata={"count": len(files), "user": selected_user},
        )

    def uninstall_packages(
        self,
        serial: str | None,
        packages: Iterable[str],
        *,
        user: str | int | None,
        keep_data: bool = False,
    ) -> CommandResult:
        serial = self._explicit_serial(serial)
        selected_user = self.resolve_user(serial, user)
        if selected_user is None:
            raise ValidationError("Uninstall requires an explicit Android user/profile.")
        names = [validate_package(package) for package in packages]
        if not names:
            raise ValidationError("At least one package is required.")
        stdout: list[str] = []
        for package in names:
            args = ["uninstall", "--user", selected_user]
            if keep_data:
                args.append("-k")
            args.append(package)
            result = self.adb.run(args, serial=serial, timeout=120)
            stdout.append(f"{package}: {result.stdout.strip()}")
        return CommandResult(
            ok=True,
            command=[str(self.adb.adb_path), "-s", serial, "uninstall", "<multiple>"],
            stdout="\n".join(stdout),
            metadata={"count": len(names), "user": selected_user},
        )

    def install_apk_set(
        self,
        serial: str | None,
        source: str | Path,
        *,
        user: str | int | None,
        replace_existing: bool = True,
        grant_runtime_permissions: bool = False,
    ) -> CommandResult:
        serial = self._explicit_serial(serial)
        selected_user = self.resolve_user(serial, user)
        if selected_user is None:
            raise ValidationError("Split APK installation requires an explicit Android user/profile.")
        files = discover_apk_set(source)
        validation = validate_apk_set(files)
        args = ["install-multiple"] if len(files) > 1 else ["install"]
        if replace_existing:
            args.append("-r")
        if grant_runtime_permissions:
            args.append("-g")
        args.extend(["--user", selected_user])
        args.extend(str(path) for path in files)
        result = self.adb.run(args, serial=serial, timeout=900)
        result.metadata.update(validation)
        result.metadata["user"] = selected_user
        return result

    def replace_app(
        self,
        serial: str | None,
        package: str,
        apk_file: str | Path,
        *,
        user: str | int | None,
        allow_uninstall: bool = False,
    ) -> CommandResult:
        """Replace an application safely, retaining a rollback APK set when possible."""
        serial = self._explicit_serial(serial)
        package = validate_package(package)
        selected_user = self.resolve_user(serial, user)
        if selected_user is None:
            raise ValidationError("Replace requires an explicit Android user/profile.")
        apk_path = safe_local_path(apk_file, must_exist=True)
        if apk_path.suffix.lower() != ".apk":
            raise ValidationError("Transactional replacement currently requires an APK file.")

        transaction = self.workspace / "transactions" / f"{package}-{int(time.time())}"
        backup_dir = transaction / "backup"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_files: list[Path] = []
        for remote in self.package_paths(serial, package):
            destination = collision_safe_path(backup_dir, Path(remote).name)
            pulled = self.adb.run(["pull", remote, str(destination)], serial=serial, timeout=600, check=False)
            if pulled.ok and destination.is_file():
                backup_files.append(destination)

        first_args = ["install", "-r", "--user", selected_user, str(apk_path)]
        first = self.adb.run(first_args, serial=serial, timeout=600, check=False)
        if first.ok:
            first.metadata.update(
                {
                    "transactional": True,
                    "strategy": "in-place-replace",
                    "backup_files": [str(path) for path in backup_files],
                    "rollback_required": False,
                }
            )
            return first
        if not allow_uninstall:
            raise CommandExecutionError(
                "In-place replacement failed. The installed application was preserved. "
                "Use --allow-uninstall only after reviewing signature/data-loss implications.",
                returncode=first.returncode,
                stderr=first.stderr or first.stdout,
            )

        uninstall = self.adb.run(
            ["uninstall", "--user", selected_user, package], serial=serial, timeout=120, check=False
        )
        if not uninstall.ok:
            raise CommandExecutionError(
                "Unable to uninstall the existing package; no replacement was performed.",
                returncode=uninstall.returncode,
                stderr=uninstall.stderr,
            )
        install = self.adb.run(
            ["install", "--user", selected_user, str(apk_path)], serial=serial, timeout=600, check=False
        )
        if install.ok:
            install.metadata.update(
                {
                    "transactional": True,
                    "strategy": "uninstall-install",
                    "backup_files": [str(path) for path in backup_files],
                    "rollback_required": False,
                    "warning": "Application data may have been removed by uninstall.",
                }
            )
            return install

        rollback = None
        if backup_files:
            rollback_args = [
                "install-multiple" if len(backup_files) > 1 else "install",
                "-r",
                "--user",
                selected_user,
                *map(str, backup_files),
            ]
            rollback = self.adb.run(rollback_args, serial=serial, timeout=900, check=False)
        metadata = {
            "transactional": True,
            "strategy": "uninstall-install",
            "backup_files": [str(path) for path in backup_files],
            "replacement_error": install.stderr or install.stdout,
            "rollback_attempted": rollback is not None,
            "rollback_ok": rollback.ok if rollback else False,
        }
        raise CommandExecutionError(
            f"Replacement failed after uninstall. Rollback {'succeeded' if rollback and rollback.ok else 'failed or was unavailable'}. Metadata: {json.dumps(metadata)}",
            returncode=install.returncode,
            stderr=install.stderr or install.stdout,
        )

    def info(self, serial: str | None, mode: str = "basic") -> dict[str, Any]:
        serial = self._serial(serial)
        allowed = {"basic", "system", "network", "security", "all"}
        if mode not in allowed:
            raise ValidationError(f"Unknown info mode: {mode}")
        commands: dict[str, list[str]] = {
            "manufacturer": ["shell", "getprop", "ro.product.manufacturer"],
            "model": ["shell", "getprop", "ro.product.model"],
            "android_version": ["shell", "getprop", "ro.build.version.release"],
            "sdk": ["shell", "getprop", "ro.build.version.sdk"],
            "security_patch": ["shell", "getprop", "ro.build.version.security_patch"],
            "build_fingerprint": ["shell", "getprop", "ro.build.fingerprint"],
        }
        if mode in {"network", "all"}:
            commands.update(
                {
                    "interfaces": ["shell", "ip", "-brief", "address"],
                    "routes": ["shell", "ip", "route"],
                    "dns": ["shell", "getprop", "net.dns1"],
                    "proxy": ["shell", "settings", "get", "global", "http_proxy"],
                }
            )
        if mode in {"security", "all"}:
            commands.update(
                {
                    "selinux": ["shell", "getenforce"],
                    "verified_boot": ["shell", "getprop", "ro.boot.verifiedbootstate"],
                    "debuggable": ["shell", "getprop", "ro.debuggable"],
                    "secure": ["shell", "getprop", "ro.secure"],
                    "encryption": ["shell", "getprop", "ro.crypto.state"],
                }
            )
        data: dict[str, Any] = {"serial": serial, "mode": mode}
        for key, args in commands.items():
            result = self.adb.run(args, serial=serial, check=False, timeout=20)
            data[key] = (result.stdout or result.stderr).strip()
        return data

    def app_summary(self, serial: str | None, package: str) -> dict[str, Any]:
        serial = self._serial(serial)
        package = validate_package(package)
        paths = self.package_paths(serial, package)
        dumpsys = self.adb.run(["shell", "dumpsys", "package", package], serial=serial, timeout=90)
        permissions: list[str] = []
        requested: list[str] = []
        for line in dumpsys.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("android.permission."):
                permission = stripped.split(":", 1)[0]
                if "granted=true" in stripped:
                    permissions.append(permission)
                requested.append(permission)
        return {
            "package": package,
            "apk_paths": paths,
            "granted_permissions": sorted(set(permissions)),
            "requested_permissions": sorted(set(requested)),
            "raw_excerpt": dumpsys.stdout[:20000],
        }

    def runtime(self, serial: str | None, mode: str = "summary", package: str | None = None) -> Any:
        serial = self._serial(serial)
        if mode == "processes":
            return self.adb.run(["shell", "ps", "-A"], serial=serial).to_dict()
        if mode == "activities":
            return self.adb.run(["shell", "dumpsys", "activity", "activities"], serial=serial, timeout=90).to_dict()
        if mode == "services":
            return self.adb.run(["shell", "dumpsys", "activity", "services"], serial=serial, timeout=90).to_dict()
        if mode == "summary":
            data: dict[str, Any] = {
                "foreground": self.adb.run(
                    ["shell", "dumpsys", "window", "windows"], serial=serial, check=False
                ).stdout[:12000],
                "processes": self.adb.run(["shell", "ps", "-A"], serial=serial).stdout[:20000],
            }
            if package:
                package = validate_package(package)
                data["pid"] = self.adb.run(["shell", "pidof", package], serial=serial, check=False).stdout.strip()
            return data
        raise ValidationError(f"Unknown runtime mode: {mode}")

    @staticmethod
    def _logcat_options(log_format: str, regex: str | None) -> tuple[str, re.Pattern[str] | None]:
        if log_format not in LOG_FORMATS:
            raise ValidationError(f"Unsupported logcat format: {log_format}")
        try:
            pattern = re.compile(regex) if regex else None
        except re.error as exc:
            raise ValidationError(f"Invalid regular expression: {exc}") from exc
        return log_format, pattern

    def logs_capture(
        self,
        serial: str | None,
        *,
        output: str | Path | None = None,
        duration: int = 30,
        package: str | None = None,
        pid: int | None = None,
        regex: str | None = None,
        clear: bool = False,
        log_format: str = "threadtime",
        filters: Iterable[str] = (),
    ) -> CommandResult:
        serial = self._serial(serial)
        duration = validate_positive_int(duration, maximum=86400)
        log_format, pattern = self._logcat_options(log_format, regex)
        if clear:
            self.adb.run(["logcat", "-c"], serial=serial)
        if package:
            package = validate_package(package)
            pid_result = self.adb.run(["shell", "pidof", package], serial=serial, check=False)
            if not pid_result.stdout.strip():
                raise ValidationError(f"Package {package} is not currently running.")
            pid = int(pid_result.stdout.split()[0])
        args = ["logcat", "-v", log_format]
        if pid:
            args.extend(["--pid", str(validate_positive_int(pid, maximum=10_000_000))])
        args.extend(str(item) for item in filters)
        default_name = f"logcat-{int(time.time())}.log"
        target = safe_local_path(output or self.workspace / "logs" / default_name)
        if output and (target.is_dir() or not target.suffix):
            target = target / default_name
        target.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        lines: list[str] = []
        for line in self.adb.stream(args, serial=serial):
            if pattern is None or pattern.search(line):
                lines.append(line)
            if time.monotonic() - started >= duration:
                break
        target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return CommandResult(
            ok=True,
            command=self.adb.build(args, serial=serial),
            stdout=f"Captured {len(lines)} log lines.",
            artifacts=[str(target)],
            duration_ms=int((time.monotonic() - started) * 1000),
            metadata={"lines": len(lines), "duration": duration},
        )

    def logs_stream(
        self,
        serial: str | None,
        *,
        package: str | None = None,
        pid: int | None = None,
        regex: str | None = None,
        log_format: str = "threadtime",
    ) -> Iterator[str]:
        serial = self._serial(serial)
        log_format, pattern = self._logcat_options(log_format, regex)
        if package:
            package = validate_package(package)
            pid_result = self.adb.run(["shell", "pidof", package], serial=serial, check=False)
            if not pid_result.stdout.strip():
                raise ValidationError(f"Package {package} is not currently running.")
            pid = int(pid_result.stdout.split()[0])
        args = ["logcat", "-v", log_format]
        if pid:
            args.extend(["--pid", str(validate_positive_int(pid, maximum=10_000_000))])
        for line in self.adb.stream(args, serial=serial):
            if pattern is None or pattern.search(line):
                yield line

    def logs_clear(self, serial: str | None) -> CommandResult:
        serial = self._serial(serial)
        return self.adb.run(["logcat", "-c"], serial=serial)

    def sniff_interfaces(self, serial: str | None) -> CommandResult:
        serial = self._serial(serial)
        return self.adb.run(["shell", "ip", "-brief", "link"], serial=serial)

    def push_tcpdump(self, serial: str | None, binary: str | Path) -> CommandResult:
        serial = self._serial(serial)
        binary_path = safe_local_path(binary, must_exist=True)
        remote = "/data/local/tmp/adbgath-tcpdump"
        pushed = self.adb.run(["push", str(binary_path), remote], serial=serial, timeout=300)
        self.adb.run(["shell", "chmod", "0755", remote], serial=serial)
        pushed.artifacts = [remote]
        return pushed

    def sniff_capture(
        self,
        serial: str | None,
        *,
        interface: str = "wlan0",
        output: str | Path | None = None,
        duration: int = 30,
    ) -> CommandResult:
        serial = self._serial(serial)
        interface = validate_interface(interface)
        duration = validate_positive_int(duration, maximum=86400)
        default_name = f"capture-{int(time.time())}.pcap"
        target = safe_local_path(output or self.workspace / "captures" / default_name)
        if output and (target.is_dir() or not target.suffix):
            target = target / default_name
        target.parent.mkdir(parents=True, exist_ok=True)
        remote = f"/data/local/tmp/adbgath-{int(time.time())}.pcap"
        tcpdump_candidates = [
            ("tcpdump", "command -v tcpdump >/dev/null 2>&1"),
            ("/data/local/tmp/adbgath-tcpdump", "test -x /data/local/tmp/adbgath-tcpdump"),
        ]
        selected = ""
        for candidate, probe in tcpdump_candidates:
            check = self.adb.run(["shell", "su", "-c", probe], serial=serial, check=False)
            if check.ok:
                selected = candidate
                break
        if not selected:
            raise DependencyError("tcpdump was not found on the rooted Android device.")
        capture = self.adb.run(
            [
                "shell",
                "su",
                "-c",
                (
                    f"{selected} -i {interface} -s 0 -w {remote} >/dev/null 2>&1 & "
                    f"pid=$!; sleep {duration}; kill -2 $pid 2>/dev/null; wait $pid 2>/dev/null"
                ),
            ],
            serial=serial,
            timeout=duration + 20,
            check=False,
        )
        if capture.returncode not in {0, 130, 143}:
            raise CommandExecutionError("Network capture failed.", returncode=capture.returncode, stderr=capture.stderr)
        pulled = self.adb.run(["pull", remote, str(target)], serial=serial, timeout=300)
        self.adb.run(["shell", "su", "-c", f"rm -f {remote}"], serial=serial, check=False)
        pulled.artifacts = [str(target)]
        pulled.metadata = {"interface": interface, "duration": duration}
        return pulled

    def proxy(self, serial: str | None, mode: str, spec: str | None = None) -> CommandResult:
        serial = self._serial(serial)
        if mode == "show":
            return self.adb.run(["shell", "settings", "get", "global", "http_proxy"], serial=serial)
        if mode == "set":
            if not spec:
                raise ValidationError("Proxy set requires HOST:PORT.")
            return self.adb.run(
                ["shell", "settings", "put", "global", "http_proxy", validate_host_port(spec)],
                serial=serial,
            )
        if mode == "clear":
            return self.adb.run(["shell", "settings", "put", "global", "http_proxy", ":0"], serial=serial)
        raise ValidationError(f"Unknown proxy mode: {mode}")

    def port_forward(
        self,
        serial: str | None,
        *,
        mode: str,
        local_port: int,
        remote_port: int,
    ) -> CommandResult:
        serial = self._serial(serial)
        local = validate_positive_int(local_port, maximum=65535)
        remote = validate_positive_int(remote_port, maximum=65535)
        if mode not in {"forward", "reverse"}:
            raise ValidationError("Port mapping mode must be forward or reverse.")
        return self.adb.run([mode, f"tcp:{local}", f"tcp:{remote}"], serial=serial)

    def backup(
        self,
        serial: str | None,
        package: str,
        *,
        output: str | Path | None = None,
    ) -> CommandResult:
        serial = self._serial(serial)
        package = validate_package(package)
        target = safe_local_path(output or self.workspace / "backups" / f"{package}-{int(time.time())}.tar")
        target.parent.mkdir(parents=True, exist_ok=True)
        command = self.adb.build(["exec-out", "run-as", package, "tar", "-cf", "-", "."], serial=serial)
        started = time.monotonic()
        try:
            with target.open("wb") as handle:
                completed = subprocess.run(
                    command,
                    stdout=handle,
                    stderr=subprocess.PIPE,
                    timeout=600,
                    shell=False,
                    check=False,
                )
        except subprocess.TimeoutExpired as exc:
            target.unlink(missing_ok=True)
            raise CommandExecutionError("App backup timed out.", returncode=124, stderr=str(exc)) from exc
        if completed.returncode != 0:
            target.unlink(missing_ok=True)
            raise CommandExecutionError(
                "App backup failed. The package must be debuggable or the device must permit run-as.",
                returncode=completed.returncode,
                stderr=completed.stderr.decode("utf-8", errors="replace"),
            )
        return CommandResult(
            ok=True,
            command=command,
            stdout=f"Backup written to {target}",
            duration_ms=int((time.monotonic() - started) * 1000),
            artifacts=[str(target)],
        )

    def content_providers(self, serial: str | None, package: str | None = None) -> CommandResult:
        serial = self._serial(serial)
        result = self.adb.run(["shell", "dumpsys", "package", "providers"], serial=serial, timeout=120)
        if package:
            package = validate_package(package)
            lines = [line for line in result.stdout.splitlines() if package in line]
            result.stdout = "\n".join(lines)
        return result

    def _resolve_frida_script(self, script: str | Path) -> tuple[Path, dict[str, Any]]:
        candidate = Path(script).expanduser()
        bundled = Path(__file__).parent / "frida" / "scripts" / f"{candidate.stem}.js"
        if not candidate.is_file() and bundled.is_file():
            candidate = bundled
        candidate = safe_local_path(candidate, must_exist=True)
        if candidate.suffix.lower() != ".js":
            raise ValidationError("Frida scripts must use the .js extension.")
        if candidate.stat().st_size > 2 * 1024 * 1024:
            raise ValidationError("Frida scripts are limited to 2 MiB.")
        source = candidate.read_text(encoding="utf-8", errors="strict")
        if "\x00" in source:
            raise ValidationError("Frida script contains a NUL byte.")
        node = shutil.which("node")
        if node:
            checked = subprocess.run(
                [node, "--check", str(candidate)],
                capture_output=True,
                text=True,
                timeout=15,
                shell=False,
                check=False,
            )
            if checked.returncode != 0:
                raise ValidationError(f"Frida script syntax validation failed: {checked.stderr.strip()}")
        metadata = dict(SCRIPT_CATALOG.get(candidate.stem, {}))
        metadata.setdefault("version", "custom")
        metadata.setdefault("description", source.splitlines()[0].removeprefix("// ") if source else "Custom script")
        metadata.setdefault("parameters", {})
        metadata.setdefault("safety", "user-supplied")
        metadata["sha256"] = sha256_file(candidate)
        metadata["path"] = str(candidate)
        return candidate, metadata

    def frida(
        self,
        serial: str | None,
        mode: str = "ps",
        package: str | None = None,
        script: str | Path | None = None,
        *,
        redact: bool = True,
    ) -> CommandResult:
        serial = self._serial(serial)
        executable = shutil.which("frida-ps" if mode == "ps" else "frida")
        if not executable:
            raise DependencyError("Frida tools are not installed. Install the optional frida-tools package.")
        script_path: Path | None = None
        script_metadata: dict[str, Any] = {}
        if mode == "ps":
            command = [executable, "-D", serial, "-ai"]
        elif mode in {"attach", "spawn"}:
            if not package:
                raise ValidationError("Frida attach/spawn requires a package name.")
            package = validate_package(package)
            command = [executable, "-D", serial]
            command.extend(["-f", package] if mode == "spawn" else ["-n", package])
            if script:
                script_path, script_metadata = self._resolve_frida_script(script)
                command.extend(["-l", str(script_path)])
        else:
            raise ValidationError(f"Unknown Frida mode: {mode}")

        record = self.store.create_frida_session(
            device_serial=serial,
            package_name=package,
            mode=mode,
            script_name=script_path.stem if script_path else None,
            command=command,
            metadata={"script": script_metadata, "redacted_at_rest": redact},
        )
        session_root = self.workspace / "frida" / "sessions"
        session_root.mkdir(parents=True, exist_ok=True)
        stdout_path = session_root / f"{record['id']}.stdout.log"
        stderr_path = session_root / f"{record['id']}.stderr.log"
        metadata_path = session_root / f"{record['id']}.json"
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=180,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raw_stdout = (
                exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            )
            raw_stderr = (
                exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            )
            atomic_write_text(stdout_path, self.redactor.redact(raw_stdout) if redact else raw_stdout)
            atomic_write_text(stderr_path, self.redactor.redact(raw_stderr) if redact else raw_stderr)
            completed_record = self.store.complete_frida_session(
                record["id"],
                status="timeout",
                stdout_path=str(stdout_path),
                stderr_path=str(stderr_path),
                metadata={"duration_ms": int((time.monotonic() - started) * 1000), "returncode": 124},
            )
            atomic_write_json(metadata_path, completed_record)
            raise CommandExecutionError(
                "Frida session timed out after 180 seconds.", returncode=124, stderr=raw_stderr
            ) from exc

        duration_ms = int((time.monotonic() - started) * 1000)
        atomic_write_text(stdout_path, self.redactor.redact(completed.stdout) if redact else completed.stdout)
        atomic_write_text(stderr_path, self.redactor.redact(completed.stderr) if redact else completed.stderr)
        status = "completed" if completed.returncode == 0 else "failed"
        completed_record = self.store.complete_frida_session(
            record["id"],
            status=status,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            metadata={"duration_ms": duration_ms, "returncode": completed.returncode},
        )
        atomic_write_json(metadata_path, completed_record)
        return CommandResult(
            ok=completed.returncode == 0,
            command=command,
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
            duration_ms=duration_ms,
            artifacts=[str(stdout_path), str(stderr_path), str(metadata_path)],
        )

    def frida_history(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.store.list_frida_sessions(limit)

    def static_analyze(self, apk: str | Path, *, output: str | Path | None = None) -> dict[str, Any]:
        target = safe_local_path(output or self.workspace / "reports" / f"{Path(apk).stem}-static.json")
        return self.apk_inspector.inspect(apk, output=target)

    @staticmethod
    def _sha256(path: Path) -> str:
        import hashlib

        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _run_tool(command: list[str], *, timeout: int) -> dict[str, Any]:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
        return {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout[:50000],
            "stderr": completed.stderr[:10000],
        }

    def security_audit(self, serial: str | None, *, output: str | Path | None = None) -> dict[str, Any]:
        serial = self._serial(serial)
        info = self.info(serial, "all")
        context = {
            **info,
            "ro_debuggable": info.get("debuggable"),
            "ro_secure": info.get("secure"),
            "http_proxy": info.get("proxy"),
        }
        findings = rule_engine.evaluate(context)
        report = {
            "tool": "adbgath",
            "version": __version__,
            "title": "adbgath Device Security Audit",
            "generated_at": datetime.now(UTC).isoformat(),
            "device_serial": serial,
            "device": info,
            "findings": findings,
            "summary": {
                "total": len(findings),
                "critical": sum(item["severity"] == "critical" for item in findings),
                "high": sum(item["severity"] == "high" for item in findings),
                "medium": sum(item["severity"] == "medium" for item in findings),
                "low": sum(item["severity"] == "low" for item in findings),
                "info": sum(item["severity"] in {"info", "informational"} for item in findings),
            },
        }
        target = safe_local_path(output or self.workspace / "reports" / f"security-{int(time.time())}.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        write_report(report, target, "json")
        markdown = target.with_suffix(".md")
        html = target.with_suffix(".html")
        sarif = target.with_suffix(".sarif")
        pdf = target.with_suffix(".pdf")
        write_report(report, markdown, "md")
        write_report(report, html, "html")
        write_report(report, sarif, "sarif")
        write_report(report, pdf, "pdf")
        report["artifacts"] = [str(target), str(markdown), str(html), str(sarif), str(pdf)]
        return report

    @staticmethod
    def _report_markdown(report: dict[str, Any]) -> str:
        lines = [
            "# adbgath Security Audit",
            "",
            f"Generated: `{report['generated_at']}`",
            f"Device: `{report['device'].get('serial', 'unknown')}`",
            "",
            "## Summary",
            "",
            f"- Total findings: **{report['summary']['total']}**",
            f"- High: **{report['summary']['high']}**",
            f"- Medium: **{report['summary']['medium']}**",
            f"- Low: **{report['summary']['low']}**",
            f"- Informational: **{report['summary']['info']}**",
            "",
            "## Findings",
            "",
        ]
        if not report["findings"]:
            lines.append("No findings were generated by the current checks.")
        for index, finding in enumerate(report["findings"], 1):
            lines.extend(
                [
                    f"### {index}. {finding['title']}",
                    "",
                    f"**Severity:** {finding['severity'].upper()}",
                    "",
                    f"**Evidence:** `{finding['evidence']}`",
                    "",
                    f"**Mitigation:** {finding['mitigation']}",
                    "",
                ]
            )
        return "\n".join(lines) + "\n"

    def collect(self, serial: str | None, *, output: str | Path | None = None) -> dict[str, Any]:
        return self.capture_evidence(serial, output=output)

    def mastg_collect(self, serial: str | None, *, output: str | Path | None = None) -> dict[str, Any]:
        collection = self.collect(serial, output=output)
        security = self.security_audit(serial, output=Path(collection["output"]) / "security.json")
        return {
            "profile": "OWASP MASTG-oriented evidence collection",
            "collection": collection,
            "security": security,
            "note": "This is evidence collection support, not an automated compliance certification.",
        }

    def doctor(self, *, fix: bool = False) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        repairs: list[dict[str, Any]] = []
        workspace_dirs = [
            "apks",
            "backups",
            "bundles",
            "captures",
            "evidence",
            "logs",
            "projects",
            "reports",
            "uploads",
        ]
        if fix:
            for name in workspace_dirs:
                target = self.workspace / name
                target.mkdir(parents=True, exist_ok=True)
            repairs.append({"name": "workspace-directories", "ok": True, "value": "created/verified"})
            try:
                started = self.adb.run(["start-server"], timeout=30, check=False)
                repairs.append(
                    {"name": "adb-start-server", "ok": started.ok, "value": started.stderr or started.stdout}
                )
            except AdbgathError as exc:
                repairs.append({"name": "adb-start-server", "ok": False, "value": str(exc)})

        checks.append({"name": "python", "ok": os.sys.version_info >= (3, 11), "value": os.sys.version.split()[0]})
        checks.append({"name": "platform", "ok": True, "value": f"{platform.system()} {platform.machine()}"})
        checks.append({"name": "workspace", "ok": os.access(self.workspace, os.W_OK), "value": str(self.workspace)})
        free = shutil.disk_usage(self.workspace).free
        checks.append({"name": "workspace-free-space", "ok": free >= 512 * 1024 * 1024, "value": free})
        adb_path = Path(getattr(self.adb, "adb_path", "adb.exe" if os.name == "nt" else "adb"))
        checks.append({"name": "adb", "ok": adb_path.is_file(), "value": str(adb_path)})
        try:
            version = self.adb.version()
            checks.append(
                {"name": "adb-version", "ok": version.ok, "value": version.stdout.strip() or version.stderr.strip()}
            )
        except AdbgathError as exc:
            checks.append({"name": "adb-version", "ok": False, "value": str(exc)})

        adb_candidates: list[str] = []
        locator = (
            ["where.exe", "adb"]
            if os.name == "nt"
            else ["sh", "-c", "command -v -a adb 2>/dev/null || which -a adb 2>/dev/null"]
        )
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            located = subprocess.run(locator, capture_output=True, text=True, timeout=10, shell=False, check=False)
            adb_candidates = list(dict.fromkeys(line.strip() for line in located.stdout.splitlines() if line.strip()))
        checks.append(
            {
                "name": "adb-path-conflicts",
                "ok": len(adb_candidates) <= 1,
                "value": adb_candidates or [str(adb_path)],
            }
        )
        checks.append(
            {
                "name": "ADB_PATH",
                "ok": not os.environ.get("ADB_PATH") or Path(os.environ["ADB_PATH"]).is_file(),
                "value": os.environ.get("ADB_PATH", "not set"),
            }
        )
        checks.append({"name": "ADBGATH_HOME", "ok": True, "value": os.environ.get("ADBGATH_HOME", "not set")})

        optional = ["frida", "frida-ps", "apkanalyzer", "aapt", "aapt2", "apksigner", "java", "bundletool"]
        for name in optional:
            path = shutil.which(name)
            checks.append({"name": name, "ok": path is not None, "value": path or "not installed", "optional": True})
        bundletool_jar = os.environ.get("BUNDLETOOL_JAR")
        checks.append(
            {
                "name": "bundletool-jar",
                "ok": bool(bundletool_jar and Path(bundletool_jar).is_file()),
                "value": bundletool_jar or "not set",
                "optional": True,
            }
        )

        if os.name == "nt":
            powershell = shutil.which("powershell") or shutil.which("pwsh")
            checks.append({"name": "powershell", "ok": powershell is not None, "value": powershell or "not installed"})
            pnputil = shutil.which("pnputil.exe")
            driver_value = "pnputil unavailable"
            driver_ok = False
            if pnputil:
                with contextlib.suppress(OSError, subprocess.SubprocessError):
                    driver = subprocess.run(
                        [pnputil, "/enum-devices", "/connected"],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        shell=False,
                        check=False,
                    )
                    matches = [
                        line.strip() for line in driver.stdout.splitlines() if "Android" in line or "ADB" in line
                    ]
                    driver_ok = bool(matches)
                    driver_value = matches[:20] or "No connected Android/ADB driver entry detected"
            checks.append({"name": "windows-adb-driver", "ok": driver_ok, "value": driver_value, "optional": True})

        required_names = {"python", "workspace", "adb", "adb-version", "powershell"}
        return {
            "ok": all(item["ok"] for item in checks if item["name"] in required_names or (item["name"] == "platform")),
            "workspace": str(self.workspace),
            "platform": os.name,
            "architecture": platform.machine(),
            "checks": checks,
            "repairs": repairs,
        }

    def inventory(self, serial: str | None, *, output: str | Path | None = None) -> dict[str, Any]:
        serial = self._serial(serial)
        inventory = {
            "device": self.info(serial, "basic"),
            "users": self.list_users(serial),
            "packages": self.list_packages(serial, include_paths=True),
        }
        if output:
            target = safe_local_path(output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
            inventory["artifact"] = str(target)
        return inventory

    def capabilities(self, serial: str | None) -> dict[str, Any]:
        serial = self._serial(serial)
        return self.capability_detector.detect(serial)

    def bundle_operation(
        self,
        serial: str | None,
        mode: str,
        *,
        file: str | Path | None = None,
        output: str | Path | None = None,
    ) -> dict[str, Any]:
        manager = BundletoolManager()
        serial_value = self._serial(serial) if serial else None
        allowed = {"inspect", "device-spec", "build-apks", "install-apks", "extract"}
        if mode not in allowed:
            raise ValidationError(f"Unsupported bundle mode: {mode}")
        if mode == "inspect":
            if not file:
                raise ValidationError("bundle inspect requires an AAB or APKS file.")
            return self.static_analyze(file, output=output)
        if mode == "device-spec":
            if not serial_value:
                raise ValidationError("device-spec requires a connected device.")
            target = safe_local_path(output or self.workspace / "bundles" / f"{serial_value}-device-spec.json")
            target.parent.mkdir(parents=True, exist_ok=True)
            result = manager.device_spec(serial_value, target)
            if not result.ok:
                raise CommandExecutionError(
                    "bundletool device-spec failed", returncode=result.returncode, stderr=result.stderr
                )
            return {"result": result.to_dict(), "artifact": str(target)}
        if not file:
            raise ValidationError(f"bundle {mode} requires a file.")
        source = safe_local_path(file, must_exist=True)
        if mode == "build-apks":
            target = safe_local_path(output or self.workspace / "bundles" / f"{source.stem}.apks")
            target.parent.mkdir(parents=True, exist_ok=True)
            result = manager.build_apks(source, target)
            if not result.ok:
                raise CommandExecutionError(
                    "bundletool build-apks failed", returncode=result.returncode, stderr=result.stderr
                )
            return {"result": result.to_dict(), "artifact": str(target)}
        if mode == "install-apks":
            if not serial_value:
                raise ValidationError("install-apks requires a connected device.")
            result = manager.install_apks(source, adb_serial=serial_value)
            if not result.ok:
                raise CommandExecutionError(
                    "bundletool install-apks failed", returncode=result.returncode, stderr=result.stderr
                )
            return result.to_dict()
        target = safe_local_path(output or self.workspace / "bundles" / source.stem)
        artifacts = manager.extract_apks(source, target)
        return {"output": str(target), "artifacts": artifacts}

    def capture_evidence(
        self,
        serial: str | None,
        *,
        package: str | None = None,
        output: str | Path | None = None,
        screen_record_seconds: int = 0,
        redact: bool = True,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        serial = self._serial(serial)
        package = validate_package(package) if package else None
        seconds = validate_positive_int(screen_record_seconds, maximum=180) if screen_record_seconds else 0
        root = safe_local_path(output or self.workspace / "evidence" / f"{serial}-{int(time.time())}")
        root.mkdir(parents=True, exist_ok=True)
        manifest = EvidenceManifest(device_serial=serial, project_id=project_id, session_id=session_id)
        info = self.info(serial, "all")
        manifest.build_fingerprint = info.get("build_fingerprint")
        try:
            manifest.adb_version = self.adb.version().stdout.strip()
        except AdbgathError:
            manifest.adb_version = None

        structured = {
            "device": info,
            "users": self.list_users(serial),
            "packages": self.list_packages(serial, include_paths=True),
            "runtime": self.runtime(serial, "summary", package),
            "capabilities": self.capabilities(serial),
        }
        structured_path = root / "collection.json"
        atomic_write_json(structured_path, structured)
        manifest.add_artifact(structured_path, media_type="application/json")

        commands: list[tuple[str, list[str], int]] = [
            ("logcat.txt", ["logcat", "-d", "-v", "threadtime"], 120),
            ("dumpsys-activity.txt", ["shell", "dumpsys", "activity", "activities"], 120),
            ("dumpsys-window.txt", ["shell", "dumpsys", "window", "windows"], 120),
            ("properties.txt", ["shell", "getprop"], 60),
        ]
        if package:
            commands.extend(
                [
                    ("dumpsys-package.txt", ["shell", "dumpsys", "package", package], 180),
                    ("dumpsys-activity-package.txt", ["shell", "dumpsys", "activity", package], 120),
                ]
            )
        for filename, args, timeout in commands:
            result = self.adb.run(args, serial=serial, timeout=timeout, check=False)
            manifest.add_command(result)
            target = root / filename
            atomic_write_text(target, result.stdout or result.stderr)
            redacted_copy = None
            if redact:
                redacted_copy = root / "redacted" / filename
                self.redactor.redact_file(target, redacted_copy)
            manifest.add_artifact(
                target, media_type="text/plain", source_command=result.command, redacted_copy=redacted_copy
            )
            if redacted_copy:
                manifest.add_artifact(redacted_copy, media_type="text/plain")

        screenshot = root / "screenshot.png"
        if hasattr(self.adb, "run_binary"):
            capture = self.adb.run_binary(["exec-out", "screencap", "-p"], serial=serial, timeout=60, check=False)
            manifest.add_command(capture)
            if capture.ok and capture.metadata.get("bytes"):
                screenshot.write_bytes(capture.metadata["bytes"])
                capture.metadata.pop("bytes", None)
                manifest.add_artifact(screenshot, media_type="image/png", source_command=capture.command)

        bugreport = root / "bugreport.zip"
        result = self.adb.run(["bugreport", str(bugreport)], serial=serial, timeout=900, check=False)
        manifest.add_command(result)
        if bugreport.is_file():
            manifest.add_artifact(bugreport, media_type="application/zip", source_command=result.command)

        if seconds:
            remote = "/data/local/tmp/adbgath-screenrecord.mp4"
            record = self.adb.run(
                ["shell", "screenrecord", "--time-limit", str(seconds), remote],
                serial=serial,
                timeout=seconds + 30,
                check=False,
            )
            manifest.add_command(record)
            video = root / "screenrecord.mp4"
            pulled = self.adb.run(["pull", remote, str(video)], serial=serial, timeout=300, check=False)
            manifest.add_command(pulled)
            self.adb.run(["shell", "rm", "-f", remote], serial=serial, timeout=30, check=False)
            if video.is_file():
                manifest.add_artifact(video, media_type="video/mp4", source_command=pulled.command)

        if package:
            apk_result = self.pull_apks(serial, packages=[package], output=root / "apks")
            manifest.add_command(apk_result)
            for item in apk_result.artifacts:
                artifact = Path(item)
                if artifact.is_file():
                    manifest.add_artifact(artifact, media_type="application/vnd.android.package-archive")

        manifest_path = manifest.write(root / "evidence-manifest.json")
        signature_path = None
        signing_key = os.environ.get("ADBGATH_MANIFEST_HMAC_KEY")
        if signing_key:
            signature_path = root / "evidence-manifest.json.hmac-sha256"
            atomic_write_text(signature_path, manifest.hmac_sha256(signing_key) + "\n")
        if project_id or session_id:
            for record in manifest.artifacts:
                self.store.save_artifact(
                    path=record.path,
                    sha256=record.sha256,
                    size=record.size,
                    media_type=record.media_type,
                    project_id=project_id,
                    session_id=session_id,
                    metadata={"source_command": record.source_command, "redacted_copy": record.redacted_copy},
                )
            self.store.save_artifact(
                path=str(manifest_path),
                sha256=sha256_file(manifest_path),
                size=manifest_path.stat().st_size,
                media_type="application/json",
                project_id=project_id,
                session_id=session_id,
                metadata={"kind": "evidence-manifest"},
            )
        artifacts = [item.path for item in manifest.artifacts] + [str(manifest_path)]
        if signature_path:
            artifacts.append(str(signature_path))
        return {
            "output": str(root),
            "manifest": str(manifest_path),
            "signature": str(signature_path) if signature_path else None,
            "artifacts": artifacts,
            "data": structured,
        }

    def create_snapshot(
        self,
        serial: str | None,
        name: str,
        *,
        package: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        serial = self._serial(serial)
        if not name.strip():
            raise ValidationError("Snapshot name is required.")
        package = validate_package(package) if package else None
        data = {
            "device": self.info(serial, "all"),
            "capabilities": self.capabilities(serial),
            "users": self.list_users(serial),
            "packages": self.list_packages(serial, include_paths=True),
            "runtime": self.runtime(serial, "summary", package),
            "app": self.app_summary(serial, package) if package else None,
        }
        return self.store.save_snapshot(name.strip(), data, project_id=project_id, device_serial=serial)

    def compare_snapshots(self, before: str, after: str, *, output: str | Path | None = None) -> dict[str, Any]:
        left = self.store.get_snapshot(before)
        right = self.store.get_snapshot(after)
        result = {
            "before": {key: left.get(key) for key in ["id", "name", "device_serial", "created_at"]},
            "after": {key: right.get(key) for key in ["id", "name", "device_serial", "created_at"]},
            "diff": diff_values(left["data"], right["data"]),
        }
        if output:
            target = safe_local_path(output)
            atomic_write_json(target, result)
            result["artifact"] = str(target)
        return result

    def export_project_bundle(self, project_id: str, *, output: str | Path | None = None) -> dict[str, Any]:
        project = self.store.get_project(project_id)
        sessions = self.store.list_sessions(project_id)
        findings = self.store.list_findings(project_id)
        artifacts = self.store.list_artifacts(project_id=project_id)
        snapshots = self.store.list_snapshots(project_id)
        target = safe_local_path(output or self.workspace / "exports" / f"{project_id}.zip")
        target.parent.mkdir(parents=True, exist_ok=True)
        target = collision_safe_path(target.parent, target.name)
        included: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        seen_names: set[str] = set()

        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, strict_timestamps=False) as archive:
            for name, value in {
                "project.json": project,
                "sessions.json": sessions,
                "findings.json": findings,
                "snapshots.json": snapshots,
                "artifact-index.json": artifacts,
            }.items():
                archive.writestr(name, json.dumps(value, ensure_ascii=False, indent=2))
            for artifact in artifacts:
                source = Path(str(artifact.get("path", ""))).expanduser()
                if source.is_symlink():
                    skipped.append({"path": str(source), "reason": "symbolic link"})
                    continue
                try:
                    resolved = source.resolve(strict=True)
                except (FileNotFoundError, OSError):
                    skipped.append({"path": str(source), "reason": "missing"})
                    continue
                if resolved.is_symlink() or not resolved.is_file():
                    skipped.append({"path": str(resolved), "reason": "not a regular file"})
                    continue
                try:
                    relative = resolved.relative_to(self.workspace)
                except ValueError:
                    skipped.append({"path": str(resolved), "reason": "outside workspace"})
                    continue
                archive_name = (Path("artifacts") / relative).as_posix()
                if archive_name in seen_names:
                    skipped.append({"path": str(resolved), "reason": "duplicate archive name"})
                    continue
                seen_names.add(archive_name)
                archive.write(resolved, archive_name)
                included.append(
                    {
                        "path": str(resolved),
                        "archive_path": archive_name,
                        "sha256": sha256_file(resolved),
                        "size": resolved.stat().st_size,
                    }
                )
            archive.writestr(
                "export-manifest.json",
                json.dumps(
                    {
                        "tool": "adbgath",
                        "tool_version": __version__,
                        "project_id": project_id,
                        "created_at": datetime.now(UTC).isoformat(),
                        "included": included,
                        "skipped": skipped,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )

        saved = self.store.save_artifact(
            path=str(target),
            sha256=sha256_file(target),
            size=target.stat().st_size,
            media_type="application/zip",
            project_id=project_id,
            metadata={"kind": "project-export", "included": len(included), "skipped": len(skipped)},
        )
        return {
            "project": project,
            "artifact": str(target),
            "sha256": saved["sha256"],
            "size": saved["size"],
            "included": included,
            "skipped": skipped,
        }

    def project_operation(self, mode: str, payload: dict[str, Any]) -> Any:
        if mode == "list":
            return self.store.list_projects()
        if mode == "create":
            name = str(payload.get("name", "")).strip()
            if not name:
                raise ValidationError("Project name is required.")
            return self.store.create_project(
                name, description=str(payload.get("description", "")), scope=str(payload.get("scope", ""))
            )
        if mode == "sessions":
            return self.store.list_sessions(payload.get("project_id"))
        if mode == "export":
            project_id = str(payload.get("project_id", "")).strip()
            if not project_id:
                raise ValidationError("Project ID is required for export.")
            return self.export_project_bundle(project_id, output=payload.get("output"))
        raise ValidationError(f"Unsupported project mode: {mode}")

    def findings_operation(self, payload: dict[str, Any]) -> Any:
        finding_id = payload.get("finding_id")
        status = payload.get("status")
        if finding_id and status:
            self.store.update_finding_status(str(finding_id), str(status))
        return self.store.list_findings(payload.get("project_id"))

    def groups_operation(self, mode: str, *, name: str | None = None, serial: str | None = None) -> Any:
        if mode == "list":
            return self.store.list_groups()
        if not name or not serial:
            raise ValidationError("Group name and device serial are required.")
        if mode == "add":
            self.store.add_group_device(name, serial)
        elif mode == "remove":
            self.store.remove_group_device(name, serial)
        else:
            raise ValidationError(f"Unsupported group mode: {mode}")
        return self.store.list_groups()

    def run_group(self, group: str, operation: str) -> dict[str, Any]:
        serials = self.store.list_group(group)
        if not serials:
            raise ValidationError(f"Device group {group!r} is empty or does not exist.")
        allowed = {"inventory", "info", "security", "capabilities"}
        if operation not in allowed:
            raise ValidationError(
                "Group execution only permits read-only inventory, info, security, and capabilities operations."
            )

        def execute(serial: str) -> Any:
            if operation == "inventory":
                return self.inventory(serial)
            if operation == "info":
                return self.info(serial, "all")
            if operation == "security":
                return self.security_audit(serial)
            return self.capabilities(serial)

        results: dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=min(4, len(serials)), thread_name_prefix="adbgath-device") as executor:
            futures = {executor.submit(execute, serial): serial for serial in serials}
            for future in as_completed(futures):
                serial = futures[future]
                try:
                    results[serial] = {"ok": True, "data": future.result()}
                except Exception as exc:  # per-device isolation
                    results[serial] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return {"group": group, "operation": operation, "results": results}

    def export_project_report(
        self, project_id: str, format_name: str, *, output: str | Path | None = None
    ) -> dict[str, Any]:
        project = self.store.get_project(project_id)
        findings = self.store.list_findings(project_id)
        suffix = "md" if format_name == "md" else format_name
        target = safe_local_path(output or self.workspace / "reports" / f"{project_id}.{suffix}")
        sessions = self.store.list_sessions(project_id)
        artifacts = self.store.list_artifacts(project_id)
        report = {
            "title": f"{project['name']} - adbgath Assessment Report",
            "project_id": project_id,
            "scope": project.get("scope", ""),
            "executive_summary": project.get("description") or "Reproducible Android security assessment results.",
            "findings": findings,
            "sessions": sessions,
            "artifacts": artifacts,
            "project": project,
        }
        write_report(report, target, format_name)
        return {"project": project, "format": format_name, "artifact": str(target), "finding_count": len(findings)}

    def assess(
        self,
        serial: str | None,
        package: str,
        *,
        apk: str | Path | None = None,
        project_id: str | None = None,
        output: str | Path | None = None,
    ) -> dict[str, Any]:
        serial = self._serial(serial)
        package = validate_package(package)
        if not project_id:
            project = self.store.create_project(
                f"Assessment - {package}", description="Automated adbgath application assessment", scope=package
            )
            project_id = project["id"]
        session = self.store.create_session(
            project_id, device_serial=serial, package_name=package, metadata={"tool_version": __version__}
        )
        root = safe_local_path(output or self.workspace / "projects" / project_id / "sessions" / session["id"])
        root.mkdir(parents=True, exist_ok=True)
        try:
            app = self.app_summary(serial, package)
            capabilities = self.capabilities(serial)
            evidence = self.capture_evidence(
                serial,
                package=package,
                output=root / "evidence",
                project_id=project_id,
                session_id=session["id"],
            )
            static = None
            if apk:
                static = self.static_analyze(apk, output=root / "static.json")
            else:
                pulled = self.pull_apks(serial, packages=[package], output=root / "apks")
                base = next(
                    (
                        Path(item)
                        for item in pulled.artifacts
                        if Path(item).name.endswith("base.apk") or "base.apk" in Path(item).name
                    ),
                    None,
                )
                if base is None and pulled.artifacts:
                    base = Path(pulled.artifacts[0])
                if base and base.is_file():
                    static = self.static_analyze(base, output=root / "static.json")
            findings = list((static or {}).get("findings", []))
            for finding in findings:
                self.store.save_finding(finding, project_id=project_id, session_id=session["id"])
            report = {
                "title": f"Application Assessment - {package}",
                "project_id": project_id,
                "device_serial": serial,
                "package": package,
                "executive_summary": f"Authorized static and device-side assessment of {package}.",
                "findings": findings,
                "app": app,
                "capabilities": capabilities,
                "evidence": evidence,
                "static": static,
            }
            artifacts = []
            for format_name, suffix in [
                ("json", "json"),
                ("md", "md"),
                ("html", "html"),
                ("sarif", "sarif"),
                ("pdf", "pdf"),
            ]:
                target = root / f"assessment.{suffix}"
                write_report(report, target, format_name)
                artifacts.append(str(target))
            self.store.complete_session(session["id"], status="completed")
            return {**report, "session_id": session["id"], "artifacts": artifacts}
        except Exception:
            self.store.complete_session(session["id"], status="failed")
            raise

    def plugin_operation(self, payload: dict[str, Any]) -> Any:
        mode = str(payload.get("mode", "list"))
        if mode == "list":
            return [describe_plugin(plugin) for plugin in self.plugins.values()]
        if mode != "run":
            raise ValidationError(f"Unsupported plugin mode: {mode}")
        name = str(payload.get("name", "")).strip()
        plugin = self.plugins.get(name)
        if plugin is None:
            raise ValidationError(f"Unknown plugin: {name}")
        missing = plugin.check_requirements()
        if missing:
            raise DependencyError(f"Plugin {name} requirements are not met: {', '.join(missing)}")
        declared = set(plugin.permissions)
        allowed = set(payload.get("allow_permissions", []))
        unknown = allowed - KNOWN_PERMISSIONS
        if unknown:
            raise ValidationError(f"Unknown plugin permissions: {', '.join(sorted(unknown))}")
        if not declared.issubset(allowed):
            required = ", ".join(sorted(declared)) or "none"
            raise ValidationError(
                f"Plugin {name} requires explicit permission approval: {required}. "
                "Pass all declared permissions using --allow-permission."
            )
        package = payload.get("package")
        if package:
            package = validate_package(str(package))
        context = PluginContext(
            service=self,
            serial=payload.get("device"),
            package=package,
            payload={key: value for key, value in payload.items() if key not in {"device", "package"}},
        )
        result = plugin.execute(context)
        if not isinstance(result, dict):
            raise ValidationError(f"Plugin {name} returned an unsupported result type.")
        return {"plugin": describe_plugin(plugin), "result": result}

    def frida_scripts(self) -> list[dict[str, Any]]:
        root = Path(__file__).parent / "frida" / "scripts"
        if not root.is_dir():
            return []
        scripts: list[dict[str, Any]] = []
        for path in sorted(root.glob("*.js")):
            metadata = dict(SCRIPT_CATALOG.get(path.stem, {}))
            metadata.update({"name": path.stem, "path": str(path), "sha256": sha256_file(path)})
            scripts.append(metadata)
        return scripts

    def update_operation(
        self, mode: str, *, archive: str | Path | None = None, checksum: str | None = None
    ) -> dict[str, Any]:
        root = Path(os.environ.get("ADBGATH_HOME", Path(__file__).resolve().parents[2]))
        updater = SecureUpdater(root)
        if mode == "check":
            return updater.check()
        if mode == "plan":
            return updater.plan(archive, checksum)
        if mode == "install":
            if not archive or not checksum:
                raise ValidationError("Update installation requires a local archive and SHA-256 checksum.")
            return updater.install(archive, checksum)
        if mode == "rollback":
            return updater.rollback()
        raise ValidationError(f"Unsupported update mode: {mode}")

    def dispatch(self, action: str, payload: dict[str, Any]) -> Any:
        """Allowlisted web command dispatcher. No arbitrary shell command is accepted."""
        if action not in WEB_ACTIONS:
            raise ValidationError(f"Unsupported action: {action}")
        serial = payload.get("device")
        user = payload.get("user")
        if action == "devices":
            return self.devices()
        if action == "capabilities":
            return self.capabilities(serial)
        if action == "connect":
            return self.connect(payload.get("target", "")).to_dict()
        if action == "disconnect":
            return self.disconnect(payload.get("target", "")).to_dict()
        if action == "users":
            return self.list_users(serial)
        if action == "packages":
            system_value = payload.get("system")
            system = None if system_value in {None, "", "all"} else system_value == "system"
            return self.list_packages(
                serial, user=user, include_paths=bool(payload.get("include_paths", False)), system=system
            )
        if action == "paths":
            package = payload.get("package")
            return self.package_paths(serial, package) if package else self.list_apk_paths(serial, user=user)
        if action == "download":
            return self.pull_apks(
                serial,
                packages=payload.get("packages", []),
                remote_paths=payload.get("remote_paths", []),
                output=payload.get("output"),
                user=user,
            ).to_dict()
        if action == "install":
            return self.install_apks(
                serial,
                payload.get("files", []),
                user=user,
                replace_existing=bool(payload.get("replace_existing", False)),
                grant_runtime_permissions=bool(payload.get("grant_runtime_permissions", False)),
            ).to_dict()
        if action == "install_set":
            return self.install_apk_set(serial, payload.get("source", ""), user=user).to_dict()
        if action == "uninstall":
            return self.uninstall_packages(
                serial, payload.get("packages", []), user=user, keep_data=bool(payload.get("keep_data", False))
            ).to_dict()
        if action == "replace":
            replacements = payload.get("replacements") or []
            if replacements:
                return [
                    self.replace_app(
                        serial,
                        item.get("package", ""),
                        item.get("file", ""),
                        user=user,
                        allow_uninstall=bool(payload.get("allow_uninstall", False)),
                    ).to_dict()
                    for item in replacements
                    if isinstance(item, dict)
                ]
            return self.replace_app(
                serial,
                payload.get("package", ""),
                payload.get("file", ""),
                user=user,
                allow_uninstall=bool(payload.get("allow_uninstall", False)),
            ).to_dict()
        if action == "bundle":
            return self.bundle_operation(
                serial, payload.get("mode", "inspect"), file=payload.get("file"), output=payload.get("output")
            )
        if action == "info":
            return self.info(serial, payload.get("mode", "basic"))
        if action == "app":
            return self.app_summary(serial, payload.get("package", ""))
        if action == "runtime":
            return self.runtime(serial, payload.get("mode", "summary"), payload.get("package"))
        if action == "logs_capture":
            return self.logs_capture(
                serial,
                output=payload.get("output"),
                duration=payload.get("duration", 30),
                package=payload.get("package"),
                pid=payload.get("pid"),
                regex=payload.get("regex"),
                clear=bool(payload.get("clear", False)),
                log_format=payload.get("format", "threadtime"),
                filters=payload.get("filters", []),
            ).to_dict()
        if action == "logs_clear":
            return self.logs_clear(serial).to_dict()
        if action == "evidence":
            return self.capture_evidence(
                serial,
                package=payload.get("package"),
                output=payload.get("output"),
                screen_record_seconds=payload.get("screen_record_seconds", 0),
                redact=bool(payload.get("redact", True)),
            )
        if action == "sniff_interfaces":
            return self.sniff_interfaces(serial).to_dict()
        if action == "sniff_capture":
            return self.sniff_capture(
                serial,
                interface=payload.get("interface", "wlan0"),
                output=payload.get("output"),
                duration=payload.get("duration", 30),
            ).to_dict()
        if action == "push_tcpdump":
            return self.push_tcpdump(serial, payload.get("file", "")).to_dict()
        if action == "proxy":
            return self.proxy(serial, payload.get("mode", "show"), payload.get("spec")).to_dict()
        if action == "forward":
            return self.port_forward(
                serial,
                mode=payload.get("mode", "forward"),
                local_port=payload.get("local_port", 8080),
                remote_port=payload.get("remote_port", 8080),
            ).to_dict()
        if action == "backup":
            return self.backup(serial, payload.get("package", ""), output=payload.get("output")).to_dict()
        if action == "content":
            return self.content_providers(serial, payload.get("package")).to_dict()
        if action == "frida":
            if payload.get("mode") == "scripts":
                return self.frida_scripts()
            if payload.get("mode") == "history":
                return self.frida_history(payload.get("limit", 100))
            return self.frida(
                serial,
                payload.get("mode", "ps"),
                payload.get("package"),
                payload.get("script"),
                redact=bool(payload.get("redact", True)),
            ).to_dict()
        if action == "static":
            return self.static_analyze(payload.get("file", ""), output=payload.get("output"))
        if action == "assess":
            return self.assess(
                serial,
                payload.get("package", ""),
                apk=payload.get("apk"),
                project_id=payload.get("project_id"),
                output=payload.get("output"),
            )
        if action == "security":
            return self.security_audit(serial, output=payload.get("output"))
        if action == "collect":
            return self.collect(serial, output=payload.get("output"))
        if action == "mastg":
            return self.mastg_collect(serial, output=payload.get("output"))
        if action == "inventory":
            return self.inventory(serial, output=payload.get("output"))
        if action == "snapshot_create":
            return self.create_snapshot(
                serial, payload.get("name", ""), package=payload.get("package"), project_id=payload.get("project_id")
            )
        if action == "snapshot_diff":
            return self.compare_snapshots(
                payload.get("before", ""), payload.get("after", ""), output=payload.get("output")
            )
        if action == "projects":
            return self.project_operation(payload.get("mode", "list"), payload)
        if action == "findings":
            return self.findings_operation(payload)
        if action == "groups":
            return self.groups_operation(
                payload.get("mode", "list"), name=payload.get("name"), serial=payload.get("serial")
            )
        if action == "run_group":
            return self.run_group(payload.get("group", ""), payload.get("operation", "inventory"))
        if action == "reports":
            return self.export_project_report(
                payload.get("project_id", ""), payload.get("format", "html"), output=payload.get("output")
            )
        if action == "plugins":
            return self.plugin_operation(payload)
        if action == "doctor":
            return self.doctor(fix=bool(payload.get("fix", False)))
        if action == "update":
            return self.update_operation(
                payload.get("mode", "check"), archive=payload.get("archive"), checksum=payload.get("checksum")
            )
        raise ValidationError(f"Unsupported action: {action}")
