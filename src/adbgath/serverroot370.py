from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def patch_auth_root(module: Any) -> None:
    """Keep persistent Web identity/workspace data outside managed install roots."""

    def default_server_root() -> Path:
        override = os.environ.get("ADBGATH_SERVER_HOME")
        if override:
            return Path(override).expanduser().resolve()
        if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
            return (Path(os.environ["LOCALAPPDATA"]) / "adbgath" / "server").resolve()
        xdg = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
        return (base / "adbgath-server").resolve()

    module.default_server_root = default_server_root
