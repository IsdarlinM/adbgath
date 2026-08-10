from __future__ import annotations

from typing import Any


def patch_web_server(module: Any) -> None:
    """Turn non-zero server exits into normal ADBGath CLI failures."""
    if getattr(module, "_adbgath_372_server_exception_guard_patched", False):
        return

    original_serve = module.serve

    def serve(*args, **kwargs):
        try:
            return original_serve(*args, **kwargs)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
            if code in {0, None}:
                raise
            raise module.AdbgathError(
                "Web server failed to start. Check whether the host/port is already in use and whether the TLS configuration is valid."
            ) from exc

    module.serve = serve
    module._adbgath_372_server_exception_guard_patched = True
