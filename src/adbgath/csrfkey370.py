from __future__ import annotations

import hashlib
import hmac
from typing import Any


def patch_csrf_key(webapp370_module: Any) -> None:
    """Make CSRF HMAC depend only on server-side key material."""

    def csrf_token(app: Any, session: Any) -> str:
        secret = getattr(app.state, "csrf_secret_370", None)
        if not isinstance(secret, (bytes, bytearray)) or len(secret) < 32:
            raise RuntimeError("ADB-Gath 3.7 CSRF server secret is unavailable.")
        message = b"ADB-Gath/3.7/csrf\x00" + session.token.encode("utf-8")
        return hmac.new(bytes(secret), message, hashlib.sha256).hexdigest()

    webapp370_module._csrf_token = csrf_token
