from __future__ import annotations

import contextlib
import os
import subprocess
import threading
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, Callable

from .adb import AdbClient as LegacyAdbClient
from .adb import UnavailableAdbClient as LegacyUnavailableAdbClient
from .errors import CommandExecutionError
from .models import CommandResult

MetricSink = Callable[[dict[str, Any]], None]
_FAILURE_MARKERS = (
    "failed to connect", "cannot connect", "unable to connect", "actively refused",
    "connection refused", "no connection could be made", "timed out", "unknown host",
    "protocol fault", "failed to pair", "pairing failed", "wrong password",
    "incorrect pairing code", "error:", "failure [",
)


class AdbClient(LegacyAdbClient):
    """ADB wrapper with semantic network results, secret stdin, cancellation, and local metrics."""

    def __init__(self, adb_path: str | Path | None = None, *, default_timeout: int = 60) -> None:
        super().__init__(adb_path, default_timeout=default_timeout)
        self._local = threading.local()
        self._metric_sink: MetricSink | None = None
        self.env = os.environ.copy()
        self.reload_environment()

    def reload_environment(self) -> None:
        self.env = os.environ.copy()
        home = Path(os.environ.get("ADBGATH_HOME", Path.home() / ".adbgath")).expanduser().resolve()
        target = home / "wireless.env"
        if not target.is_file():
            return
        for raw in target.read_text(encoding="utf-8-sig").splitlines():
            if "=" not in raw or raw.lstrip().startswith("#"):
                continue
            key, value = raw.split("=", 1)
            if key in {"ADB_MDNS", "ADB_MDNS_OPENSCREEN", "ADB_BURST_MODE"}:
                self.env[key] = value.strip()

    def set_metric_sink(self, sink: MetricSink | None) -> None:
        self._metric_sink = sink

    @contextlib.contextmanager
    def cancellation(self, cancel_event: threading.Event | None) -> Iterator[None]:
        previous = getattr(self._local, "cancel_event", None)
        self._local.cancel_event = cancel_event
        try:
            yield
        finally:
            self._local.cancel_event = previous

    def _cancel_event(self) -> threading.Event | None:
        return getattr(self._local, "cancel_event", None)

    @staticmethod
    def _semantic_ok(args: Sequence[str], returncode: int, stdout: str, stderr: str) -> tuple[bool, str | None]:
        if returncode != 0:
            return False, "non-zero-return-code"
        text = f"{stdout}\n{stderr}".strip().lower()
        if any(marker in text for marker in _FAILURE_MARKERS):
            return False, "adb-textual-failure"
        command = args[0] if args else ""
        if command == "connect":
            return (True, None) if "connected to" in text or "already connected to" in text else (False, "connect-did-not-confirm-success")
        if command == "pair":
            return (True, None) if "successfully paired" in text or "already paired" in text else (False, "pair-did-not-confirm-success")
        return True, None

    def _metric(self, result: CommandResult, args: Sequence[str], serial: str | None) -> None:
        if self._metric_sink is None:
            return
        try:
            self._metric_sink({
                "serial": serial,
                "command": str(args[0]) if args else "",
                "duration_ms": result.duration_ms,
                "returncode": result.returncode,
                "ok": result.ok,
                "stdout_bytes": len(result.stdout.encode("utf-8", errors="replace")),
                "stderr_bytes": len(result.stderr.encode("utf-8", errors="replace")),
                "metadata": {key: value for key, value in result.metadata.items() if key != "bytes"},
                "timestamp": result.timestamp,
            })
        except Exception:
            pass

    def _popen_text(self, command: list[str], *, timeout: int, input_text: str | None = None, bounded: bool = False) -> tuple[int, str, str, bool]:
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
                    process.kill(); stdout, stderr = process.communicate()
                return 130, stdout or "", stderr or "Cancelled by operator.", False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.terminate()
                try:
                    stdout, stderr = process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill(); stdout, stderr = process.communicate()
                if bounded:
                    return process.returncode or 0, stdout or "", stderr or "", True
                raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)
            try:
                stdout, stderr = process.communicate(input=pending, timeout=min(.25, remaining))
                return process.returncode or 0, stdout or "", stderr or "", False
            except subprocess.TimeoutExpired:
                pending = None

    def run(self, args: Sequence[str], *, serial: str | None = None, timeout: int | None = None, check: bool = True, cwd: Path | None = None) -> CommandResult:
        command = self.build(args, serial=serial)
        effective = timeout or self.default_timeout
        started = time.monotonic()
        try:
            if self._cancel_event() is None:
                completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=effective, cwd=str(cwd) if cwd else None, shell=False, check=False, env=self.env)
                returncode, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
            else:
                returncode, stdout, stderr, _ = self._popen_text(command, timeout=effective)
        except subprocess.TimeoutExpired as exc:
            raise CommandExecutionError(f"ADB command timed out after {effective} seconds.", returncode=124, stderr=str(exc)) from exc
        ok, reason = self._semantic_ok(args, returncode, stdout, stderr)
        result = CommandResult(ok=ok, command=command, stdout=stdout, stderr=stderr, returncode=returncode, duration_ms=int((time.monotonic()-started)*1000), metadata={"semantic_failure": reason} if reason else {})
        self._metric(result, args, serial)
        if check and not result.ok:
            detail = result.stderr.strip() or result.stdout.strip() or "Unknown ADB error"
            raise CommandExecutionError(f"ADB command failed: {detail}", returncode=result.returncode, stderr=result.stderr or result.stdout)
        return result

    def run_interactive(self, args: Sequence[str], *, input_data: str, serial: str | None = None, timeout: int | None = None, check: bool = True) -> CommandResult:
        command = self.build(args, serial=serial)
        effective = timeout or self.default_timeout
        started = time.monotonic()
        try:
            if self._cancel_event() is None:
                completed = subprocess.run(command, input=f"{input_data}\n", capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=effective, shell=False, check=False, env=self.env)
                returncode, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
            else:
                returncode, stdout, stderr, _ = self._popen_text(command, timeout=effective, input_text=f"{input_data}\n")
        except subprocess.TimeoutExpired as exc:
            raise CommandExecutionError(f"ADB command timed out after {effective} seconds.", returncode=124, stderr=str(exc)) from exc
        ok, reason = self._semantic_ok(args, returncode, stdout, stderr)
        result = CommandResult(ok=ok, command=command, stdout=stdout, stderr=stderr, returncode=returncode, duration_ms=int((time.monotonic()-started)*1000), metadata={"stdin_redacted": True, **({"semantic_failure": reason} if reason else {})})
        self._metric(result, args, serial)
        if check and not result.ok:
            detail = result.stderr.strip() or result.stdout.strip() or "Unknown ADB error"
            raise CommandExecutionError(f"ADB command failed: {detail}", returncode=result.returncode, stderr=result.stderr or result.stdout)
        return result

    def run_bounded(self, args: Sequence[str], *, duration: int = 2, serial: str | None = None, check: bool = False) -> CommandResult:
        command = self.build(args, serial=serial)
        started = time.monotonic()
        returncode, stdout, stderr, timed = self._popen_text(command, timeout=max(1, duration), bounded=True)
        ok, reason = self._semantic_ok(args, returncode, stdout, stderr)
        if timed:
            ok = not any(marker in (stdout + "\n" + stderr).lower() for marker in _FAILURE_MARKERS)
            reason = None if ok else "adb-textual-failure"
        result = CommandResult(ok=ok, command=command, stdout=stdout, stderr=stderr, returncode=0 if timed and ok else returncode, duration_ms=int((time.monotonic()-started)*1000), metadata={"bounded_capture": True, **({"semantic_failure": reason} if reason else {})})
        self._metric(result, args, serial)
        if check and not result.ok:
            raise CommandExecutionError(f"ADB command failed: {stderr or stdout}", returncode=result.returncode, stderr=stderr or stdout)
        return result

    def stream(self, args: Sequence[str], *, serial: str | None = None) -> Iterator[str]:
        command = self.build(args, serial=serial)
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", shell=False, env=self.env)
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


class UnavailableAdbClient(LegacyUnavailableAdbClient):
    def set_metric_sink(self, sink: MetricSink | None) -> None:
        del sink

    def reload_environment(self) -> None:
        return None

    @contextlib.contextmanager
    def cancellation(self, cancel_event: threading.Event | None) -> Iterator[None]:
        del cancel_event
        yield

    def run_interactive(self, *args: Any, **kwargs: Any) -> CommandResult:
        del args, kwargs
        self._raise()

    def run_bounded(self, *args: Any, **kwargs: Any) -> CommandResult:
        del args, kwargs
        self._raise()
