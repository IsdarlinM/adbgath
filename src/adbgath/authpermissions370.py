from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _chmod(path: Path, mode: int) -> None:
    if os.name == "nt":
        return
    try:
        path.chmod(mode)
    except OSError:
        pass


def patch_auth_permissions(module: Any) -> None:
    if getattr(module.AuthStore, "_adbgath_370_permissions_patched", False):
        return

    original_init = module.AuthStore.__init__
    original_workspace_path = module.AuthStore._workspace_path

    def secure_init(self, root=None):
        original_init(self, root)
        _chmod(Path(self.root), 0o700)
        _chmod(Path(self.user_root), 0o700)
        if Path(self.db_path).exists():
            _chmod(Path(self.db_path), 0o600)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(self.db_path) + suffix)
            if sidecar.exists():
                _chmod(sidecar, 0o600)

    def secure_workspace_path(self, user_id: str, workspace_id: str):
        path = original_workspace_path(self, user_id, workspace_id)
        _chmod(Path(self.user_root) / user_id, 0o700)
        _chmod(Path(self.user_root) / user_id / "workspaces", 0o700)
        _chmod(Path(path), 0o700)
        return path

    module.AuthStore.__init__ = secure_init
    module.AuthStore._workspace_path = secure_workspace_path
    module.AuthStore._adbgath_370_permissions_patched = True
