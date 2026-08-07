from __future__ import annotations

import os
import struct
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"ADBGATH360VAULT\x00"


def _derive(passphrase: str, salt: bytes) -> bytes:
    if len(passphrase) < 12:
        raise ValueError("vault passphrase must contain at least 12 characters")
    return Scrypt(salt=salt, length=32, n=2**14, r=8, p=1).derive(passphrase.encode("utf-8"))


def seal_file(source: str | Path, destination: str | Path, passphrase: str) -> dict[str, object]:
    src=Path(source).expanduser().resolve(strict=True); dst=Path(destination).expanduser().resolve(); dst.parent.mkdir(parents=True,exist_ok=True)
    salt=os.urandom(16); nonce=os.urandom(12); key=_derive(passphrase,salt); plaintext=src.read_bytes(); ciphertext=AESGCM(key).encrypt(nonce,plaintext,MAGIC)
    tmp=dst.with_name(f".{dst.name}.tmp"); tmp.write_bytes(MAGIC+salt+nonce+struct.pack(">Q",len(plaintext))+ciphertext); os.replace(tmp,dst)
    return {"path":str(dst),"plaintext_size":len(plaintext),"encrypted_size":dst.stat().st_size,"algorithm":"AES-256-GCM","kdf":"scrypt"}


def unseal_file(source: str | Path, destination: str | Path, passphrase: str) -> dict[str, object]:
    src=Path(source).expanduser().resolve(strict=True); data=src.read_bytes()
    if not data.startswith(MAGIC): raise ValueError("not an ADB-Gath 3.6 vault object")
    offset=len(MAGIC); salt=data[offset:offset+16]; offset+=16; nonce=data[offset:offset+12]; offset+=12; expected=struct.unpack(">Q",data[offset:offset+8])[0]; offset+=8
    plaintext=AESGCM(_derive(passphrase,salt)).decrypt(nonce,data[offset:],MAGIC)
    if len(plaintext)!=expected: raise ValueError("vault size validation failed")
    dst=Path(destination).expanduser().resolve(); dst.parent.mkdir(parents=True,exist_ok=True); tmp=dst.with_name(f".{dst.name}.tmp"); tmp.write_bytes(plaintext); os.replace(tmp,dst)
    return {"path":str(dst),"size":len(plaintext),"verified":True}
