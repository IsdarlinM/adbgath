from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Iterator, Sequence
from pathlib import Path

from .errors import CommandExecutionError, DependencyError
from .models import CommandResult, Device
from .validation import validate_serial


class AdbClient:
    """Safe subprocess wrapper for Android Debug Bridge.

    Commands are always passed as argument arrays. Shell parsing is never enabled.
    """

    def __init__(self, adb_path: str | Path | None = None, *, default_timeout: int = 60) -> None:
        self.adb_path = self._locate_adb(adb_path)
        self.default_timeout = default_timeout

    @staticmethod
    def _locate_adb(explicit: str | Path | None) -> Path:
        candidates: list[Path] = []
        if explicit:
            candidates.append(Path(explicit).expanduser())
        if os.environ.get("ADB_PATH"):
            candidates.append(Path(os.environ["ADB_PATH"]).expanduser())
        discovered = shutil.which("adb")
        if discovered:
            candidates.append(Path(discovered))

        home = Path(os.environ.get("ADBGATH_HOME", Path.home() / ".adbgath"))
        candidates.extend(
            [
                home / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb"),
                Path.home() / "AppData/Local/Android/Sdk/platform-tools/adb.exe",
                Path.home() / "Android/Sdk/platform-tools/adb",
            ]
        )
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved.is_file():
                return resolved
        raise DependencyError("ADB was not found. Run the platform installer or set ADB_PATH to adb/adb.exe.")

    def build(self, args: Sequence[str], *, serial: str | None = None) -> list[str]:
        command = [str(self.adb_path)]
        if serial:
            command.extend(["-s", validate_serial(serial)])
        command.extend(str(item) for item in args)
        return command

    def run(
        self,
        args: Sequence[str],
        *,
        serial: str | None = None,
        timeout: int | None = None,
        check: bool = True,
        cwd: Path | None = None,
    ) -> CommandResult:
        command = self.build(args, serial=serial)
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout or self.default_timeout,
                cwd=str(cwd) if cwd else None,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CommandExecutionError(
                f"ADB command timed out after {timeout or self.default_timeout} seconds.",
                returncode=124,
                stderr=str(exc),
            ) from exc
        duration = int((time.monotonic() - started) * 1000)
        result = CommandResult(
            ok=completed.returncode == 0,
            command=command,
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
            duration_ms=duration,
        )
        if check and not result.ok:
            detail = result.stderr.strip() or result.stdout.strip() or "Unknown ADB error"
            raise CommandExecutionError(
                f"ADB command failed: {detail}",
                returncode=result.returncode,
                stderr=result.stderr,
            )
        return result

    def run_binary(
        self,
        args: Sequence[str],
        *,
        serial: str | None = None,
        timeout: int | None = None,
        check: bool = True,
    ) -> CommandResult:
        command = self.build(args, serial=serial)
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=False,
                timeout=timeout or self.default_timeout,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CommandExecutionError(
                f"ADB binary command timed out after {timeout or self.default_timeout} seconds.",
                returncode=124,
                stderr=str(exc),
            ) from exc
        result = CommandResult(
            ok=completed.returncode == 0,
            command=command,
            stdout="",
            stderr=completed.stderr.decode("utf-8", errors="replace"),
            returncode=completed.returncode,
            duration_ms=int((time.monotonic() - started) * 1000),
            metadata={"bytes": completed.stdout},
        )
        if check and not result.ok:
            raise CommandExecutionError(
                f"ADB command failed: {result.stderr.strip() or 'Unknown ADB error'}",
                returncode=result.returncode,
                stderr=result.stderr,
            )
        return result

    def stream(
        self,
        args: Sequence[str],
        *,
        serial: str | None = None,
    ) -> Iterator[str]:
        command = self.build(args, serial=serial)
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
        try:
            if process.stdout is None:
                raise CommandExecutionError("Unable to read the ADB output stream.")
            for line in iter(process.stdout.readline, ""):
                yield line.rstrip("\r\n")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()

    def version(self) -> CommandResult:
        return self.run(["version"])

    def devices(self) -> list[Device]:
        output = self.run(["devices", "-l"]).stdout.splitlines()
        devices: list[Device] = []
        for line in output[1:]:
            line = line.strip()
            if not line or line.startswith("*"):
                continue
            parts = line.split()
            serial, state = parts[0], parts[1] if len(parts) > 1 else "unknown"
            fields: dict[str, str] = {}
            for part in parts[2:]:
                if ":" in part:
                    key, value = part.split(":", 1)
                    fields[key] = value
            devices.append(
                Device(
                    serial=serial,
                    state=state,
                    product=fields.get("product", ""),
                    model=fields.get("model", ""),
                    device=fields.get("device", ""),
                    transport_id=fields.get("transport_id", ""),
                )
            )
        return devices

    def require_device(self, serial: str | None) -> str:
        devices = [device for device in self.devices() if device.state == "device"]
        if serial:
            serial = validate_serial(serial)
            if not any(device.serial == serial for device in devices):
                raise CommandExecutionError(f"Device {serial!r} is unavailable or unauthorized.", returncode=2)
            return serial
        if len(devices) == 1:
            return devices[0].serial
        if not devices:
            raise CommandExecutionError("No authorized Android device is connected.", returncode=2)
        raise CommandExecutionError("Multiple devices are connected. Select one with --device.", returncode=2)


class UnavailableAdbClient:
    """ADB-compatible placeholder used when Platform-Tools is unavailable.

    This lets diagnostics, documentation, project management, and the local web
    interface start before ADB is installed. Device operations still fail closed
    with the original dependency error.
    """

    def __init__(self, reason: str, *, default_timeout: int = 60) -> None:
        self.reason = reason
        self.default_timeout = default_timeout
        self.adb_path = Path("adb.exe" if os.name == "nt" else "adb")

    def _raise(self) -> None:
        raise DependencyError(self.reason)

    def build(self, args: Sequence[str], *, serial: str | None = None) -> list[str]:
        command = [str(self.adb_path)]
        if serial:
            command.extend(["-s", validate_serial(serial)])
        command.extend(str(item) for item in args)
        return command

    def run(
        self,
        args: Sequence[str],
        *,
        serial: str | None = None,
        timeout: int | None = None,
        check: bool = True,
        cwd: Path | None = None,
    ) -> CommandResult:
        del args, serial, timeout, check, cwd
        self._raise()

    def run_binary(
        self,
        args: Sequence[str],
        *,
        serial: str | None = None,
        timeout: int | None = None,
        check: bool = True,
    ) -> CommandResult:
        del args, serial, timeout, check
        self._raise()

    def stream(self, args: Sequence[str], *, serial: str | None = None) -> Iterator[str]:
        del args, serial
        self._raise()
        yield ""  # pragma: no cover - preserves generator typing after the fail-closed raise

    def version(self) -> CommandResult:
        self._raise()

    def devices(self) -> list[Device]:
        self._raise()

    def require_device(self, serial: str | None) -> str:
        del serial
        self._raise()
