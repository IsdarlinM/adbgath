from __future__ import annotations

import asyncio
import contextlib
import os
import platform
import shutil
import signal
import subprocess
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

from .errors import CommandExecutionError
from .models import CommandResult


_TRUSTED_WIRELESS_STATES = {"paired", "connected", "disconnected"}


def _hidden_process_kwargs(*, process_group: bool = False) -> dict[str, Any]:
    if os.name != "nt":
        return {}
    flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if process_group:
        flags |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    return {"creationflags": flags} if flags else {}


def _patch_adb_processes(adb_module: Any) -> None:
    cls = adb_module.AdbClient
    if getattr(cls, "_adbgath_hidden_windows_patched", False):
        return

    def _popen_text(
        self,
        command: list[str],
        *,
        timeout: int,
        input_text: str | None = None,
        bounded: bool = False,
    ) -> tuple[int, str, str, bool]:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE if input_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            env=self.env,
            **_hidden_process_kwargs(),
        )
        deadline = time.monotonic() + timeout
        pending = input_text
        while True:
            cancel = self._cancel_event()
            if cancel is not None and cancel.is_set():
                process.terminate()
                try:
                    stdout, stderr = process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
                return 130, stdout or "", stderr or "Cancelled by operator.", False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.terminate()
                try:
                    stdout, stderr = process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
                if bounded:
                    return process.returncode or 0, stdout or "", stderr or "", True
                raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)
            try:
                stdout, stderr = process.communicate(input=pending, timeout=min(0.25, remaining))
                return process.returncode or 0, stdout or "", stderr or "", False
            except subprocess.TimeoutExpired:
                pending = None

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
        effective = timeout or self.default_timeout
        started = time.monotonic()
        try:
            if self._cancel_event() is None:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=effective,
                    cwd=str(cwd) if cwd else None,
                    shell=False,
                    check=False,
                    env=self.env,
                    **_hidden_process_kwargs(),
                )
                returncode, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
            else:
                returncode, stdout, stderr, _ = _popen_text(self, command, timeout=effective)
        except subprocess.TimeoutExpired as exc:
            raise CommandExecutionError(
                f"ADB command timed out after {effective} seconds.",
                returncode=124,
                stderr=str(exc),
            ) from exc
        ok, reason = self._semantic_ok(args, returncode, stdout, stderr)
        result = CommandResult(
            ok=ok,
            command=command,
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            duration_ms=int((time.monotonic() - started) * 1000),
            metadata={"semantic_failure": reason} if reason else {},
        )
        self._metric(result, args, serial)
        if check and not result.ok:
            detail = result.stderr.strip() or result.stdout.strip() or "Unknown ADB error"
            raise CommandExecutionError(
                f"ADB command failed: {detail}",
                returncode=result.returncode,
                stderr=result.stderr or result.stdout,
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
        effective = timeout or self.default_timeout
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=False,
                timeout=effective,
                shell=False,
                check=False,
                env=self.env,
                **_hidden_process_kwargs(),
            )
        except subprocess.TimeoutExpired as exc:
            raise CommandExecutionError(
                f"ADB binary command timed out after {effective} seconds.",
                returncode=124,
                stderr=str(exc),
            ) from exc
        stdout_bytes = completed.stdout or b""
        stderr = (completed.stderr or b"").decode("utf-8", errors="replace")
        ok, reason = self._semantic_ok(args, completed.returncode, "", stderr)
        result = CommandResult(
            ok=ok,
            command=command,
            stdout="",
            stderr=stderr,
            returncode=completed.returncode,
            duration_ms=int((time.monotonic() - started) * 1000),
            metadata={"bytes": stdout_bytes, **({"semantic_failure": reason} if reason else {})},
        )
        self._metric(result, args, serial)
        if check and not result.ok:
            raise CommandExecutionError(
                f"ADB command failed: {result.stderr.strip() or 'Unknown ADB error'}",
                returncode=result.returncode,
                stderr=result.stderr,
            )
        return result

    def run_interactive(
        self,
        args: Sequence[str],
        *,
        input_data: str,
        serial: str | None = None,
        timeout: int | None = None,
        check: bool = True,
    ) -> CommandResult:
        command = self.build(args, serial=serial)
        effective = timeout or self.default_timeout
        started = time.monotonic()
        try:
            if self._cancel_event() is None:
                completed = subprocess.run(
                    command,
                    input=f"{input_data}\n",
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=effective,
                    shell=False,
                    check=False,
                    env=self.env,
                    **_hidden_process_kwargs(),
                )
                returncode, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
            else:
                returncode, stdout, stderr, _ = _popen_text(
                    self,
                    command,
                    timeout=effective,
                    input_text=f"{input_data}\n",
                )
        except subprocess.TimeoutExpired as exc:
            raise CommandExecutionError(
                f"ADB command timed out after {effective} seconds.",
                returncode=124,
                stderr=str(exc),
            ) from exc
        ok, reason = self._semantic_ok(args, returncode, stdout, stderr)
        result = CommandResult(
            ok=ok,
            command=command,
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            duration_ms=int((time.monotonic() - started) * 1000),
            metadata={
                "stdin_redacted": True,
                **({"semantic_failure": reason} if reason else {}),
            },
        )
        self._metric(result, args, serial)
        if check and not result.ok:
            detail = result.stderr.strip() or result.stdout.strip() or "Unknown ADB error"
            raise CommandExecutionError(
                f"ADB command failed: {detail}",
                returncode=result.returncode,
                stderr=result.stderr or result.stdout,
            )
        return result

    def run_bounded(
        self,
        args: Sequence[str],
        *,
        duration: int = 2,
        serial: str | None = None,
        check: bool = False,
    ) -> CommandResult:
        command = self.build(args, serial=serial)
        started = time.monotonic()
        returncode, stdout, stderr, timed = _popen_text(
            self,
            command,
            timeout=max(1, duration),
            bounded=True,
        )
        ok, reason = self._semantic_ok(args, returncode, stdout, stderr)
        if timed:
            markers = getattr(__import__(self.__class__.__module__, fromlist=["_FAILURE_MARKERS"]), "_FAILURE_MARKERS", ())
            ok = not any(marker in (stdout + "\n" + stderr).lower() for marker in markers)
            reason = None if ok else "adb-textual-failure"
        result = CommandResult(
            ok=ok,
            command=command,
            stdout=stdout,
            stderr=stderr,
            returncode=0 if timed and ok else returncode,
            duration_ms=int((time.monotonic() - started) * 1000),
            metadata={
                "bounded_capture": True,
                **({"semantic_failure": reason} if reason else {}),
            },
        )
        self._metric(result, args, serial)
        if check and not result.ok:
            raise CommandExecutionError(
                f"ADB command failed: {stderr or stdout}",
                returncode=result.returncode,
                stderr=stderr or stdout,
            )
        return result

    def stream(self, args: Sequence[str], *, serial: str | None = None) -> Iterator[str]:
        command = self.build(args, serial=serial)
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            env=self.env,
            **_hidden_process_kwargs(),
        )
        try:
            if process.stdout is None:
                raise CommandExecutionError("Unable to read the ADB output stream.")
            for line in iter(process.stdout.readline, ""):
                cancel = self._cancel_event()
                if cancel is not None and cancel.is_set():
                    break
                yield line.rstrip("\r\n")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()

    cls._popen_text = _popen_text
    cls.run = run
    cls.run_binary = run_binary
    cls.run_interactive = run_interactive
    cls.run_bounded = run_bounded
    cls.stream = stream
    cls._adbgath_hidden_windows_patched = True


def _patch_async_supervisor(asyncproc_module: Any) -> None:
    cls = asyncproc_module.AsyncProcessSupervisor
    if getattr(cls, "_adbgath_hidden_windows_patched", False):
        return

    async def start(self, command, *, cwd=None, env=None, stdin=None):
        if not command:
            raise ValueError("command is required")
        kwargs: dict[str, Any] = {
            "stdin": asyncio.subprocess.PIPE if stdin is not None else None,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "cwd": str(cwd) if cwd else None,
            "env": env,
        }
        if os.name == "nt":
            kwargs.update(_hidden_process_kwargs(process_group=True))
        else:
            kwargs["start_new_session"] = True
        process = await asyncio.create_subprocess_exec(*(str(x) for x in command), **kwargs)
        handle = asyncproc_module.AsyncProcessHandle(
            process=process,
            command=[str(x) for x in command],
            started_at=asyncio.get_running_loop().time(),
            output_limit=self.output_limit,
        )
        if stdin is not None and process.stdin is not None:
            process.stdin.write(stdin)
            await process.stdin.drain()
            process.stdin.close()
        return handle

    async def terminate_tree(self, handle, *, grace: float = 0.75):
        process = handle.process
        if process.returncode is not None:
            return
        handle.cancelled = True
        if os.name == "nt":
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
            except Exception:
                process.terminate()
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
            except Exception:
                process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=grace)
            return
        except asyncio.TimeoutError:
            pass
        if os.name == "nt":
            proc = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(process.pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                **_hidden_process_kwargs(),
            )
            await proc.wait()
        else:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        with contextlib.suppress(Exception):
            process.kill()
        await process.wait()

    cls.start = start
    cls._terminate_tree = terminate_tree
    cls._adbgath_hidden_windows_patched = True


def _patch_wireless_manager(manager_module: Any) -> None:
    cls = manager_module.WirelessManager
    if getattr(cls, "_adbgath_autoconnect_360_patched", False):
        return
    original_save = cls._save_service

    def save_service(self, service, *, state: str = "discovered"):
        selected = state
        if state == "discovered":
            identifier = service.serial or service.instance or service.hostname
            if identifier:
                try:
                    existing = self.store.get_wireless_device(identifier)
                    if existing.get("state") in _TRUSTED_WIRELESS_STATES:
                        selected = str(existing["state"])
                except KeyError:
                    pass
        return original_save(self, service, state=selected)

    def auto_connect(self) -> dict[str, Any]:
        before = [device.to_dict() for device in self.adb.devices()]
        discovery = self.discover(refresh=True)
        connect_services = list(discovery.get("connect_services", []))

        connected: list[dict[str, Any]] = []
        latest_devices = before
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            latest_devices = [device.to_dict() for device in self.adb.devices()]
            online = {item.get("serial") for item in latest_devices if item.get("state") == "device"}
            connected = [service for service in connect_services if service.get("endpoint") in online]
            if connected or not connect_services:
                break
            time.sleep(0.25)

        online = {item.get("serial") for item in latest_devices if item.get("state") == "device"}
        known = self.store.list_wireless_devices()
        trusted = {
            str(item.get("instance") or item.get("serial") or "")
            for item in known
            if item.get("state") in _TRUSTED_WIRELESS_STATES
        }

        results: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        attempted = 0
        for service in connect_services:
            endpoint = str(service.get("endpoint") or "")
            identity = str(service.get("serial") or service.get("instance") or "")
            if endpoint in online:
                results.append(
                    {
                        "ok": True,
                        "endpoint": endpoint,
                        "method": "adb-native-mdns",
                        "note": "ADB server auto-connected this previously paired device.",
                    }
                )
                continue
            if identity not in trusted:
                skipped.append(
                    {
                        "endpoint": endpoint,
                        "instance": service.get("instance"),
                        "reason": "not-known-as-paired-by-adbgath-and-adb-native-autoconnect-did-not-connect",
                    }
                )
                continue

            attempted += 1
            result = self.connect(endpoint)
            result.metadata["auto_connect_method"] = "trusted-manual-fallback"
            if not result.ok:
                refreshed = self.discover(refresh=True)
                candidates = [
                    item
                    for item in refreshed.get("connect_services", [])
                    if (
                        item.get("instance") == service.get("instance")
                        or (service.get("serial") and item.get("serial") == service.get("serial"))
                    )
                    and item.get("endpoint") != endpoint
                ]
                if candidates:
                    retry = self.connect(candidates[0]["endpoint"])
                    retry.metadata.update(
                        {
                            "auto_connect_method": "trusted-manual-fallback-after-port-refresh",
                            "previous_endpoint": endpoint,
                        }
                    )
                    results.append(retry.to_dict())
                    continue
            results.append(result.to_dict())

        return {
            "native_autoconnect": True,
            "discovered": len(connect_services),
            "attempted": attempted,
            "connected": len([item for item in results if item.get("ok")]),
            "results": results,
            "skipped": skipped,
            "devices": latest_devices,
            "notes": [
                "ADB natively auto-connects only devices known to this host from pairing.",
                "A _adb-tls-connect service can be advertised even when this host is not paired.",
                "Connection ports are ephemeral and may rotate.",
            ],
        }

    cls._save_service = save_service
    cls.auto_connect = auto_connect
    cls._adbgath_autoconnect_360_patched = True


def _patch_web_lazy_start(webapp_module: Any, service_module: Any) -> None:
    if getattr(webapp_module, "_adbgath_lazy_adb_start_patched", False):
        return
    base_cls = service_module.AdbgathService

    class LazyWebService(base_cls):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._adbgath_bootstrap_pending = True

        def _bootstrap_doctor(self) -> dict[str, Any]:
            checks: list[dict[str, Any]] = []
            checks.append(
                {
                    "name": "python",
                    "ok": os.sys.version_info >= (3, 11),
                    "value": os.sys.version.split()[0],
                }
            )
            checks.append(
                {
                    "name": "platform",
                    "ok": True,
                    "value": f"{platform.system()} {platform.machine()}",
                }
            )
            checks.append(
                {
                    "name": "workspace",
                    "ok": os.access(self.workspace, os.W_OK),
                    "value": str(self.workspace),
                }
            )
            free = shutil.disk_usage(self.workspace).free
            checks.append(
                {
                    "name": "workspace-free-space",
                    "ok": free >= 512 * 1024 * 1024,
                    "value": free,
                }
            )
            adb_path = Path(getattr(self.adb, "adb_path", "adb.exe" if os.name == "nt" else "adb"))
            adb_exists = adb_path.is_file()
            checks.extend(
                [
                    {"name": "adb", "ok": adb_exists, "value": str(adb_path)},
                    {
                        "name": "adb-version",
                        "ok": adb_exists,
                        "value": "Deferred until device refresh or Run doctor",
                        "deferred": True,
                    },
                    {
                        "name": "adb-path-conflicts",
                        "ok": True,
                        "value": "Deferred until Run doctor",
                        "deferred": True,
                    },
                    {
                        "name": "ADB_PATH",
                        "ok": not os.environ.get("ADB_PATH") or Path(os.environ["ADB_PATH"]).is_file(),
                        "value": os.environ.get("ADB_PATH", "not set"),
                    },
                ]
            )
            return {
                "ok": all(item["ok"] for item in checks if item["name"] in {"python", "platform", "workspace", "adb"}),
                "workspace": str(self.workspace),
                "platform": os.name,
                "architecture": platform.machine(),
                "checks": checks,
                "repairs": [],
                "adb_probe_deferred": True,
            }

        def doctor(self, *, fix: bool = False):
            if self._adbgath_bootstrap_pending and not fix:
                return self._bootstrap_doctor()
            return super().doctor(fix=fix)

        def devices(self, *args, **kwargs):
            if self._adbgath_bootstrap_pending:
                self._adbgath_bootstrap_pending = False
                return []
            return super().devices(*args, **kwargs)

    webapp_module.AdbgathService = LazyWebService
    webapp_module._adbgath_lazy_adb_start_patched = True


def apply_runtime_fixes() -> None:
    from . import adb as adb_module
    from .core import asyncproc as asyncproc_module
    from . import service as service_module
    from . import webapp as webapp_module
    from .modules.wireless import manager as manager_module

    _patch_adb_processes(adb_module)
    _patch_async_supervisor(asyncproc_module)
    _patch_wireless_manager(manager_module)
    _patch_web_lazy_start(webapp_module, service_module)
