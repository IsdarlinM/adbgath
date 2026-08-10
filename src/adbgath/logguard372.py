from __future__ import annotations

from typing import Any


def patch_service(module: Any) -> None:
    cls = module.AdbgathService
    if getattr(cls, "_adbgath_372_log_exception_guard_patched", False):
        return

    original_capture = cls.logs_capture
    original_stream = cls.logs_stream

    def logs_capture(self, *args, **kwargs):
        try:
            return original_capture(self, *args, **kwargs)
        except module.AdbgathError:
            raise
        except ValueError as exc:
            raise module.CommandExecutionError(
                "ADB returned an invalid process identifier while preparing logcat capture.",
                returncode=2,
                stderr=str(exc),
            ) from exc

    def logs_stream(self, *args, **kwargs):
        try:
            yield from original_stream(self, *args, **kwargs)
        except module.AdbgathError:
            raise
        except ValueError as exc:
            raise module.CommandExecutionError(
                "ADB returned an invalid process identifier while preparing the logcat stream.",
                returncode=2,
                stderr=str(exc),
            ) from exc

    cls.logs_capture = logs_capture
    cls.logs_stream = logs_stream
    cls._adbgath_372_log_exception_guard_patched = True
