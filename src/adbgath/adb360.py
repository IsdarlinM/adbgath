from __future__ import annotations

from typing import Any, Sequence

from .core.asyncproc import AsyncProcessSupervisor
from .models import CommandResult


def patch_adb(module: Any) -> None:
    cls = module.AdbClient
    if getattr(cls, "_adbgath_360_patched", False):
        return

    async def run_async(self, args: Sequence[str], *, serial: str | None = None, timeout: float | None = None, input_data: str | None = None) -> CommandResult:
        supervisor = getattr(self, "_async_supervisor", None)
        if supervisor is None:
            supervisor = AsyncProcessSupervisor(max_concurrency=8)
            self._async_supervisor = supervisor
        command = self.build(args, serial=serial)
        stdin = (input_data + "\n").encode("utf-8") if input_data is not None else None
        result = await supervisor.run(command, timeout=float(timeout or self.default_timeout), env=self.env, stdin=stdin)
        ok, reason = self._semantic_ok(args, result.returncode, result.stdout, result.stderr)
        result.ok = ok
        if reason:
            result.metadata["semantic_failure"] = reason
        if input_data is not None:
            result.metadata["stdin_redacted"] = True
        self._record_metric(result, serial=serial, args=args)
        return result

    cls.run_async = run_async
    cls._adbgath_360_patched = True
