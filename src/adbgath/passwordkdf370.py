from __future__ import annotations

import hashlib
from typing import Any

_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 3
_SCRYPT_MAXMEM = 128 * 1024 * 1024


def patch_password_kdf(module: Any) -> None:
    """Apply the OWASP-listed scrypt N=2^15, r=8, p=3 profile for 3.7."""

    def hash_password(password: str, salt: bytes) -> bytes:
        return hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
            maxmem=_SCRYPT_MAXMEM,
            dklen=32,
        )

    module._hash_password = hash_password
