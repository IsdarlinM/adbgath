from __future__ import annotations

import base64
import hashlib
import os
import secrets
import time
from pathlib import Path
from typing import Any

_SECRET_BYTES = 32
_SECRET_CREATE_RETRIES = 100
_SECRET_CREATE_DELAY = 0.01


def _restrict_permissions(root: Path, path: Path) -> None:
    if os.name == "nt":
        return
    try:
        root.chmod(0o700)
    except OSError:
        pass
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _load_or_create(root: Path) -> bytes:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "server-secret.key"
    _restrict_permissions(root, path)

    for _ in range(_SECRET_CREATE_RETRIES):
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            data = secrets.token_bytes(_SECRET_BYTES)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            try:
                descriptor = os.open(path, flags, 0o600)
            except FileExistsError:
                time.sleep(_SECRET_CREATE_DELAY)
                continue
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
            except Exception:
                try:
                    path.unlink(missing_ok=True)
                finally:
                    raise
            _restrict_permissions(root, path)
            return data
        if len(data) == _SECRET_BYTES:
            _restrict_permissions(root, path)
            return data
        # A competing creator may have created the file but not finished its
        # write/fsync yet. Retry briefly before treating it as corrupted.
        time.sleep(_SECRET_CREATE_DELAY)

    raise RuntimeError("ADB-Gath server secret has an invalid length or could not be initialized safely.")


def _legacy_marker(secret: bytes) -> str:
    """Return a stable non-secret compatibility marker safe to send as a cookie."""
    digest = hashlib.sha256(b"ADB-Gath/3.7/legacy-session-marker\x00" + secret).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def patch_webapp(module: Any) -> None:
    """Persist server-only CSRF key material while exposing only a derived marker."""
    if getattr(module, "_adbgath_370_server_secret_patched", False):
        return
    original_create_app = module.create_app

    def create_app(*, workspace=None, service=None, remote_token=None, secure_cookie=False):
        app = original_create_app(
            workspace=workspace,
            service=service,
            remote_token=remote_token,
            secure_cookie=secure_cookie,
        )
        auth_store = getattr(app.state, "auth_store", None)
        if auth_store is not None:
            secret = _load_or_create(Path(auth_store.root))
            app.state.csrf_secret_370 = secret
            app.state.session_token = _legacy_marker(secret)
        return app

    module.create_app = create_app
    module._adbgath_370_server_secret_patched = True
