from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def canonical_plugin_bytes(manifest: dict[str, Any], plugin_file: str | Path) -> bytes:
    path = Path(plugin_file).expanduser().resolve(strict=True)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    normalized = {**manifest, "sha256": digest}
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def generate_signing_keypair(private_path: str | Path, public_path: str | Path) -> dict[str, str]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    pvt = Path(private_path).expanduser().resolve()
    pub = Path(public_path).expanduser().resolve()
    pvt.parent.mkdir(parents=True, exist_ok=True)
    pub.parent.mkdir(parents=True, exist_ok=True)
    pvt.write_bytes(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    try:
        pvt.chmod(0o600)
    except OSError:
        pass
    pub.write_bytes(public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    return {"private_key": str(pvt), "public_key": str(pub)}


def sign_plugin(manifest: dict[str, Any], plugin_file: str | Path, private_key: str | Path) -> dict[str, Any]:
    private = serialization.load_pem_private_key(Path(private_key).read_bytes(), password=None)
    if not isinstance(private, Ed25519PrivateKey):
        raise ValueError("plugin signing key must be Ed25519")
    payload = canonical_plugin_bytes(manifest, plugin_file)
    signature = base64.b64encode(private.sign(payload)).decode("ascii")
    return {"manifest": json.loads(payload.decode("utf-8")), "signature": signature, "algorithm": "Ed25519"}


def verify_plugin(bundle: dict[str, Any], plugin_file: str | Path, public_key: str | Path) -> dict[str, Any]:
    public = serialization.load_pem_public_key(Path(public_key).read_bytes())
    if not isinstance(public, Ed25519PublicKey):
        raise ValueError("plugin public key must be Ed25519")
    expected = canonical_plugin_bytes({k: v for k, v in bundle["manifest"].items() if k != "sha256"}, plugin_file)
    actual_manifest = json.loads(expected.decode("utf-8"))
    if actual_manifest != bundle["manifest"]:
        return {"ok": False, "reason": "manifest digest mismatch"}
    try:
        public.verify(base64.b64decode(bundle["signature"]), expected)
    except Exception:
        return {"ok": False, "reason": "signature verification failed"}
    return {"ok": True, "manifest": actual_manifest, "algorithm": "Ed25519"}
