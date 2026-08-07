from __future__ import annotations

import hashlib
import ipaddress
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def _write_private(path: Path, key: ec.EllipticCurvePrivateKey) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _fingerprint(cert: x509.Certificate) -> str:
    return cert.fingerprint(hashes.SHA256()).hex()


def init_ca(directory: str | Path, *, common_name: str = "ADB-Gath Lab CA") -> dict[str, str]:
    root = Path(directory).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    key_path, cert_path = root / "ca-key.pem", root / "ca-cert.pem"
    if key_path.exists() or cert_path.exists():
        raise FileExistsError("CA already exists; refusing to overwrite")
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.KeyUsage(True, False, False, False, False, True, True, False, False), critical=True)
        .sign(key, hashes.SHA256())
    )
    _write_private(key_path, key)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return {"ca_key": str(key_path), "ca_cert": str(cert_path), "fingerprint_sha256": _fingerprint(cert)}


def issue_certificate(
    directory: str | Path,
    *,
    name: str,
    client: bool,
    hosts: list[str] | None = None,
    days: int = 825,
) -> dict[str, str]:
    root = Path(directory).expanduser().resolve()
    ca_key = serialization.load_pem_private_key((root / "ca-key.pem").read_bytes(), password=None)
    ca_cert = x509.load_pem_x509_certificate((root / "ca-cert.pem").read_bytes())
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.now(UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=max(1, min(days, 825))))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .add_extension(x509.KeyUsage(True, False, False, False, False, False, False, False, False), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH if client else ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
    )
    if not client:
        sans: list[x509.GeneralName] = [x509.DNSName("localhost")]
        for host in hosts or []:
            try:
                sans.append(x509.IPAddress(ipaddress.ip_address(host)))
            except ValueError:
                sans.append(x509.DNSName(host))
        builder = builder.add_extension(x509.SubjectAlternativeName(sans), critical=False)
    cert = builder.sign(ca_key, hashes.SHA256())
    stem = "agent" if client else "controller"
    safe = "".join(c if c.isalnum() or c in "-." else "-" for c in name).strip("-") or stem
    key_path, cert_path = root / f"{stem}-{safe}-key.pem", root / f"{stem}-{safe}-cert.pem"
    _write_private(key_path, key)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return {"key": str(key_path), "cert": str(cert_path), "ca_cert": str(root / "ca-cert.pem"), "fingerprint_sha256": _fingerprint(cert), "subject": name}
