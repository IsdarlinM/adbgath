from __future__ import annotations

import argparse
import ipaddress
import os
import re
import socket
import threading
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

_DNS_RE = re.compile(
    r"^(?=.{1,253}\.?$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.?$"
)


def _loopback(host: str) -> bool:
    return host.strip().strip("[]").lower() in {"127.0.0.1", "localhost", "::1"}


def _tls_dir(explicit: str | Path | None) -> Path:
    if explicit:
        target = Path(explicit).expanduser().resolve()
    else:
        server_home = os.environ.get("ADBGATH_SERVER_HOME")
        target = (
            Path(server_home).expanduser().resolve() / "tls"
            if server_home
            else (Path.home() / ".adbgath" / "server" / "tls").resolve()
        )
    target.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        target.chmod(0o700)
    return target


def _san(value: str) -> x509.GeneralName:
    value = value.strip().rstrip(".")
    if not value:
        raise ValueError("TLS SAN entries cannot be empty.")
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        if not _DNS_RE.fullmatch(value):
            raise ValueError(f"Invalid TLS DNS SAN: {value!r}") from None
        return x509.DNSName(value)
    if address.is_unspecified:
        raise ValueError(f"Unspecified address cannot be used as a TLS SAN: {value}")
    return x509.IPAddress(address)


def _sans(host: str, extra: Iterable[str]) -> list[x509.GeneralName]:
    values = ["localhost", "127.0.0.1", "::1"]
    bind_host = host.strip().strip("[]")
    if bind_host not in {"", "0.0.0.0", "::", "*"}:
        values.append(bind_host)
    for name in {socket.gethostname(), socket.getfqdn()}:
        if not name:
            continue
        values.append(name)
        try:
            for info in socket.getaddrinfo(name, None):
                values.append(str(info[4][0]).split("%", 1)[0])
        except OSError:
            pass
    values.extend(extra)
    output: list[x509.GeneralName] = []
    seen: set[tuple[str, str]] = set()
    for value in values:
        try:
            item = _san(str(value))
        except ValueError:
            if value in extra:
                raise
            continue
        key = (type(item).__name__, str(item.value))
        if key not in seen:
            seen.add(key)
            output.append(item)
    return output


def _atomic_write(path: Path, data: bytes, mode: int) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            temporary.chmod(mode)
        os.replace(temporary, path)
        if os.name != "nt":
            path.chmod(mode)
    finally:
        temporary.unlink(missing_ok=True)


def _public_key_bytes(key: Any) -> bytes:
    return key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def validate_tls_pair(certificate: str | Path, private_key: str | Path) -> tuple[Path, Path, x509.Certificate]:
    cert_path = Path(certificate).expanduser().resolve()
    key_path = Path(private_key).expanduser().resolve()
    if not cert_path.is_file() or not key_path.is_file():
        raise ValueError("The TLS certificate or private key does not exist.")
    try:
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    except (TypeError, ValueError, OSError) as exc:
        raise ValueError(f"Unable to read PEM TLS material: {exc}") from exc
    if _public_key_bytes(cert.public_key()) != _public_key_bytes(key.public_key()):
        raise ValueError("TLS certificate and private key do not match.")
    now = datetime.now(timezone.utc)
    if cert.not_valid_before_utc > now or cert.not_valid_after_utc <= now:
        raise ValueError("TLS certificate is outside its validity period.")
    return cert_path, key_path, cert


def generate_self_signed_tls(
    *, host: str, directory: str | Path | None = None, extra_sans: Iterable[str] = ()
) -> tuple[Path, Path, x509.Certificate]:
    extra = tuple(str(item).strip() for item in extra_sans if str(item).strip())
    for value in extra:
        _san(value)
    target = _tls_dir(directory)
    cert_path = target / "adbgath-web-cert.pem"
    key_path = target / "adbgath-web-key.pem"
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(timezone.utc)
    common_name = (socket.getfqdn() or socket.gethostname() or "localhost")[:64]
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ADBGath"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=397))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectAlternativeName(_sans(host, extra)), critical=False)
        .sign(key, hashes.SHA256())
    )
    _atomic_write(
        key_path,
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
        0o600,
    )
    _atomic_write(cert_path, cert.public_bytes(serialization.Encoding.PEM), 0o644)
    return cert_path, key_path, cert


def _fingerprint(certificate: x509.Certificate) -> str:
    return certificate.fingerprint(hashes.SHA256()).hex().upper()


def patch_webapp(module: Any) -> None:
    if getattr(module, "_adbgath_372_remote_tls_patched", False):
        return

    def serve(
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        open_browser: bool = True,
        workspace: str | Path | None = None,
        remote_token: str | None = None,
        tls_cert: str | Path | None = None,
        tls_key: str | Path | None = None,
        insecure_http: bool = False,
        tls_dir: str | Path | None = None,
        tls_sans: Iterable[str] = (),
    ) -> None:
        loopback = _loopback(host)
        if not loopback and (not remote_token or len(remote_token) < 24):
            raise module.AdbgathError("Remote mode requires --remote-token with at least 24 characters.")
        if bool(tls_cert) != bool(tls_key):
            raise module.AdbgathError("--tls-cert and --tls-key must be supplied together.")
        if insecure_http and (tls_cert or tls_key):
            raise module.AdbgathError("--insecure-http cannot be combined with --tls-cert/--tls-key.")

        cert_path: Path | None = None
        key_path: Path | None = None
        certificate: x509.Certificate | None = None
        try:
            if tls_cert and tls_key:
                cert_path, key_path, certificate = validate_tls_pair(tls_cert, tls_key)
            elif not loopback and not insecure_http:
                cert_path, key_path, certificate = generate_self_signed_tls(
                    host=host, directory=tls_dir, extra_sans=tls_sans
                )
        except (OSError, ValueError) as exc:
            raise module.AdbgathError(f"TLS setup failed: {exc}") from exc

        import uvicorn

        secure = bool(cert_path and key_path)
        scheme = "https" if secure else "http"
        shown_host = host if host not in {"::1", "0.0.0.0", "::"} else (
            "[::1]" if host == "::1" else "HOSTNAME"
        )
        url = f"{scheme}://{shown_host}:{port}"
        print(f"ADB-Gath web UI: {url}")
        if secure and certificate is not None:
            print(f"TLS certificate: {cert_path}")
            print(f"TLS private key: {key_path}")
            print(f"TLS SHA-256 fingerprint: {_fingerprint(certificate)}")
            if not tls_cert:
                print(
                    "TLS: generated a self-signed ECDSA P-256 certificate. "
                    "Clients must explicitly trust it to avoid certificate warnings."
                )
        elif not loopback:
            print(
                "WARNING: remote Web UI is running over plaintext HTTP. "
                "Operator credentials, cookies, and assessment data can be intercepted in transit."
            )
        print("Remote access requires authentication; no arbitrary shell endpoint is exposed.")
        if open_browser and loopback:
            threading.Timer(0.8, lambda: webbrowser.open(url)).start()
        uvicorn.run(
            module.create_app(workspace=workspace, remote_token=remote_token, secure_cookie=secure),
            host=host,
            port=port,
            log_level="info",
            ssl_certfile=str(cert_path) if cert_path else None,
            ssl_keyfile=str(key_path) if key_path else None,
        )

    module.serve = serve
    module._adbgath_372_remote_tls_patched = True


def patch_cli(module: Any, webapp_module: Any) -> None:
    if getattr(module, "_adbgath_372_remote_tls_cli_patched", False):
        return
    original_build_parser = module.build_parser
    original_run = module.run

    def build_parser() -> argparse.ArgumentParser:
        parser = original_build_parser()
        root = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))
        web = root.choices.get("web")
        if web is not None and "--insecure-http" not in web._option_string_actions:
            web.add_argument(
                "--insecure-http",
                action="store_true",
                help="Allow authenticated remote Web access over plaintext HTTP. Unsafe on untrusted networks.",
            )
            web.add_argument("--tls-dir", help="Directory for automatically generated TLS material.")
            web.add_argument(
                "--tls-san",
                action="append",
                default=[],
                help="Additional DNS name or IP address for the generated certificate SAN. Repeatable.",
            )
            web._option_string_actions["--tls-cert"].help = (
                "PEM certificate. If omitted remotely, ADBGath generates a self-signed certificate."
            )
            web._option_string_actions["--tls-key"].help = "PEM private key paired with --tls-cert."
        return parser

    def run(args):
        if getattr(args, "command", None) == "web":
            webapp_module.serve(
                host=args.host,
                port=args.port,
                open_browser=not args.no_browser,
                workspace=args.workspace,
                remote_token=args.remote_token,
                tls_cert=args.tls_cert,
                tls_key=args.tls_key,
                insecure_http=bool(getattr(args, "insecure_http", False)),
                tls_dir=getattr(args, "tls_dir", None),
                tls_sans=getattr(args, "tls_san", []) or [],
            )
            return None
        return original_run(args)

    module.build_parser = build_parser
    module.run = run
    module._adbgath_372_remote_tls_cli_patched = True
