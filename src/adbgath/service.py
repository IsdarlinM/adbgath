from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .adb import AdbClient
from .errors import AdbgathError, CommandExecutionError, DependencyError, ValidationError
from .models import AppPackage, CommandResult
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
WEB_ACTIONS = frozenset(
    {
        "devices",
        "connect",
        "disconnect",
        "users",
        "packages",
        "paths",
        "download",
        "install",
        "uninstall",
        "replace",
        "info",
        "app",
        "runtime",
        "logs_capture",
        "logs_clear",
        "sniff_interfaces",
        "sniff_capture",
        "push_tcpdump",
        "proxy",
        "forward",
        "backup",
        "content",
        "frida",
        "static",
        "security",
        "collect",
        "mastg",
        "doctor",
        "inventory",
    }
)


class AdbgathService:
    """Cross-platform business logic shared by CLI and web UI."""

    def __init__(
        self,
        adb: AdbClient | None = None,
        *,
        workspace: str | Path | None = None,
    ) -> None:
        self.adb = adb or AdbClient()
        self.workspace = (
            Path(workspace or os.environ.get("ADBGATH_WORKSPACE", Path.home() / "adbgath-workspace"))
            .expanduser()
            .resolve()
        )
        self.workspace.mkdir(parents=True, exist_ok=True)

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

    def replace_app(
        self,
        serial: str | None,
        package: str,
        apk_file: str | Path,
        *,
        user: str | int | None,
    ) -> CommandResult:
        package = validate_package(package)
        self.uninstall_packages(serial, [package], user=user, keep_data=False)
        return self.install_apks(serial, [apk_file], user=user, replace_existing=False)

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

    def frida(
        self, serial: str | None, mode: str = "ps", package: str | None = None, script: str | Path | None = None
    ) -> CommandResult:
        serial = self._serial(serial)
        executable = shutil.which("frida-ps" if mode == "ps" else "frida")
        if not executable:
            raise DependencyError("Frida tools are not installed. Install the optional frida-tools package.")
        if mode == "ps":
            command = [executable, "-D", serial, "-ai"]
        elif mode in {"attach", "spawn"}:
            if not package:
                raise ValidationError("Frida attach/spawn requires a package name.")
            package = validate_package(package)
            command = [executable, "-D", serial]
            command.extend(["-f", package] if mode == "spawn" else ["-n", package])
            if script:
                command.extend(["-l", str(safe_local_path(script, must_exist=True))])
        else:
            raise ValidationError(f"Unknown Frida mode: {mode}")
        started = time.monotonic()
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=180,
            shell=False,
            check=False,
        )
        return CommandResult(
            ok=completed.returncode == 0,
            command=command,
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    def static_analyze(self, apk: str | Path, *, output: str | Path | None = None) -> dict[str, Any]:
        apk_path = safe_local_path(apk, must_exist=True)
        if apk_path.suffix.lower() != ".apk":
            raise ValidationError("Static analysis requires an APK file.")
        report: dict[str, Any] = {
            "apk": str(apk_path),
            "size": apk_path.stat().st_size,
            "sha256": self._sha256(apk_path),
            "tools": {},
        }
        apkanalyzer = shutil.which("apkanalyzer")
        aapt = shutil.which("aapt") or shutil.which("aapt2")
        if apkanalyzer:
            report["tools"]["apkanalyzer_manifest"] = self._run_tool(
                [apkanalyzer, "manifest", "print", str(apk_path)], timeout=120
            )
        elif aapt:
            report["tools"]["aapt_badging"] = self._run_tool([aapt, "dump", "badging", str(apk_path)], timeout=120)
        else:
            report["warning"] = "Install Android build-tools for manifest/package metadata analysis."
        target = safe_local_path(output or self.workspace / "reports" / f"{apk_path.stem}-static.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["artifact"] = str(target)
        return report

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
        findings: list[dict[str, str]] = []

        def add(condition: bool, severity: str, title: str, evidence: str, mitigation: str) -> None:
            if condition:
                findings.append(
                    {
                        "severity": severity,
                        "title": title,
                        "evidence": evidence,
                        "mitigation": mitigation,
                    }
                )

        add(
            info.get("debuggable") == "1",
            "high",
            "Device build is globally debuggable",
            "ro.debuggable=1",
            "Use a production/user build for sensitive testing and deployments.",
        )
        add(
            info.get("secure") == "0",
            "high",
            "Android secure mode is disabled",
            "ro.secure=0",
            "Restore a secure production build and disable insecure adbd settings.",
        )
        add(
            str(info.get("selinux", "")).lower() != "enforcing",
            "high",
            "SELinux is not enforcing",
            f"getenforce={info.get('selinux')}",
            "Set SELinux to enforcing and investigate policy violations instead of disabling it.",
        )
        add(
            str(info.get("verified_boot", "")).lower() not in {"green", ""},
            "medium",
            "Verified Boot is not in green state",
            f"ro.boot.verifiedbootstate={info.get('verified_boot')}",
            "Re-lock the bootloader and restore verified vendor images where appropriate.",
        )
        add(
            info.get("encryption") not in {"encrypted", "", None},
            "medium",
            "Device encryption state is unexpected",
            f"ro.crypto.state={info.get('encryption')}",
            "Verify file-based encryption and secure lock-screen configuration.",
        )
        proxy = str(info.get("proxy", ""))
        add(
            proxy not in {"", ":0", "null"},
            "info",
            "Global HTTP proxy is configured",
            f"global.http_proxy={proxy}",
            "Remove the proxy after the authorized test to avoid unintended traffic interception.",
        )
        report = {
            "tool": "adbgath",
            "version": "3.0.0",
            "generated_at": datetime.now(UTC).isoformat(),
            "device": info,
            "findings": findings,
            "summary": {
                "total": len(findings),
                "high": sum(item["severity"] == "high" for item in findings),
                "medium": sum(item["severity"] == "medium" for item in findings),
                "low": sum(item["severity"] == "low" for item in findings),
                "info": sum(item["severity"] == "info" for item in findings),
            },
        }
        target = safe_local_path(output or self.workspace / "reports" / f"security-{int(time.time())}.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
        markdown = target.with_suffix(".md")
        markdown.write_text(self._report_markdown(report), encoding="utf-8")
        report["artifacts"] = [str(target), str(markdown)]
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
        serial = self._serial(serial)
        root = safe_local_path(output or self.workspace / "collections" / f"{serial}-{int(time.time())}")
        root.mkdir(parents=True, exist_ok=True)
        data = {
            "info": self.info(serial, "all"),
            "users": self.list_users(serial),
            "packages": self.list_packages(serial, include_paths=True),
            "runtime": self.runtime(serial, "summary"),
        }
        target = root / "collection.json"
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return {"output": str(root), "artifact": str(target), "data": data}

    def mastg_collect(self, serial: str | None, *, output: str | Path | None = None) -> dict[str, Any]:
        collection = self.collect(serial, output=output)
        security = self.security_audit(serial, output=Path(collection["output"]) / "security.json")
        return {
            "profile": "OWASP MASTG-oriented evidence collection",
            "collection": collection,
            "security": security,
            "note": "This is evidence collection support, not an automated compliance certification.",
        }

    def doctor(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        checks.append(
            {
                "name": "python",
                "ok": True,
                "value": os.sys.version.split()[0],
            }
        )
        checks.append(
            {
                "name": "adb",
                "ok": self.adb.adb_path.is_file(),
                "value": str(self.adb.adb_path),
            }
        )
        version = self.adb.version()
        checks.append({"name": "adb-version", "ok": version.ok, "value": version.stdout.strip()})
        for optional in ["frida", "frida-ps", "apkanalyzer", "aapt", "aapt2"]:
            checks.append(
                {
                    "name": optional,
                    "ok": shutil.which(optional) is not None,
                    "value": shutil.which(optional) or "not installed",
                }
            )
        return {
            "ok": all(item["ok"] for item in checks if item["name"] in {"python", "adb", "adb-version"}),
            "workspace": str(self.workspace),
            "platform": os.name,
            "checks": checks,
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

    def dispatch(self, action: str, payload: dict[str, Any]) -> Any:
        """Allowlisted web command dispatcher. No arbitrary shell command is accepted."""
        if action not in WEB_ACTIONS:
            raise ValidationError(f"Unsupported action: {action}")
        serial = payload.get("device")
        user = payload.get("user")
        if action == "devices":
            return self.devices()
        if action == "connect":
            return self.connect(payload.get("target", "")).to_dict()
        if action == "disconnect":
            return self.disconnect(payload.get("target", "")).to_dict()
        if action == "users":
            return self.list_users(serial)
        if action == "packages":
            return self.list_packages(
                serial,
                user=user,
                include_paths=bool(payload.get("include_paths", False)),
                system=payload.get("system"),
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
        if action == "uninstall":
            return self.uninstall_packages(
                serial,
                payload.get("packages", []),
                user=user,
                keep_data=bool(payload.get("keep_data", False)),
            ).to_dict()
        if action == "replace":
            replacements = payload.get("replacements") or []
            if replacements:
                results = []
                for item in replacements:
                    if not isinstance(item, dict):
                        raise ValidationError("Each replacement must contain package and file values.")
                    results.append(
                        self.replace_app(serial, item.get("package", ""), item.get("file", ""), user=user).to_dict()
                    )
                return results
            return self.replace_app(
                serial,
                payload.get("package", ""),
                payload.get("file", ""),
                user=user,
            ).to_dict()
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
            return self.frida(
                serial,
                payload.get("mode", "ps"),
                payload.get("package"),
                payload.get("script"),
            ).to_dict()
        if action == "static":
            return self.static_analyze(payload.get("file", ""), output=payload.get("output"))
        if action == "security":
            return self.security_audit(serial, output=payload.get("output"))
        if action == "collect":
            return self.collect(serial, output=payload.get("output"))
        if action == "mastg":
            return self.mastg_collect(serial, output=payload.get("output"))
        if action == "doctor":
            return self.doctor()
        if action == "inventory":
            return self.inventory(serial, output=payload.get("output"))
        raise ValidationError(f"Unsupported action: {action}")
