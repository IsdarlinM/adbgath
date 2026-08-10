from __future__ import annotations

from typing import Any


def patch_adb(module: Any) -> None:
    """Convert host process-start failures into normal ADBGath command errors."""
    cls = module.AdbClient
    if getattr(cls, "_adbgath_372_process_exception_guard_patched", False):
        return

    original_run = cls.run
    original_run_binary = cls.run_binary
    original_stream = cls.stream

    def run(self, *args, **kwargs):
        try:
            return original_run(self, *args, **kwargs)
        except module.CommandExecutionError:
            raise
        except OSError as exc:
            raise module.CommandExecutionError(
                f"Unable to start ADB command: {exc}",
                returncode=126,
                stderr=str(exc),
            ) from exc

    def run_binary(self, *args, **kwargs):
        try:
            return original_run_binary(self, *args, **kwargs)
        except module.CommandExecutionError:
            raise
        except OSError as exc:
            raise module.CommandExecutionError(
                f"Unable to start ADB binary command: {exc}",
                returncode=126,
                stderr=str(exc),
            ) from exc

    def stream(self, *args, **kwargs):
        try:
            yield from original_stream(self, *args, **kwargs)
        except module.CommandExecutionError:
            raise
        except OSError as exc:
            raise module.CommandExecutionError(
                f"Unable to start ADB stream: {exc}",
                returncode=126,
                stderr=str(exc),
            ) from exc

    cls.run = run
    cls.run_binary = run_binary
    cls.stream = stream
    cls._adbgath_372_process_exception_guard_patched = True
