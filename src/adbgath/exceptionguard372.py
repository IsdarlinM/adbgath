from __future__ import annotations

import sqlite3
from typing import Any


def patch_web_server(module: Any) -> None:
    """Normalize recoverable Web initialization/startup failures at the public boundary."""
    if getattr(module, "_adbgath_372_server_exception_guard_patched", False):
        return

    original_create_app = module.create_app
    original_serve = module.serve

    def create_app(*args, **kwargs):
        try:
            return original_create_app(*args, **kwargs)
        except module.AdbgathError:
            raise
        except (OSError, sqlite3.DatabaseError, RuntimeError) as exc:
            raise module.AdbgathError(
                f"Web application initialization failed ({type(exc).__name__}): {exc}"
            ) from exc

    module.create_app = create_app

    def serve(*args, **kwargs):
        try:
            return original_serve(*args, **kwargs)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
            if code == 0:
                raise
            raise module.AdbgathError(
                "Web server failed to start. Check whether the host/port is already in use and whether the TLS configuration is valid."
            ) from exc

    module.serve = serve
    module._adbgath_372_server_exception_guard_patched = True
