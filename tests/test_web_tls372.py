from __future__ import annotations

import os
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from adbgath import cli, webapp
from adbgath.errors import AdbgathError
from adbgath.webtls372 import generate_self_signed_tls, validate_tls_pair


def test_web_cli_exposes_auto_tls_and_explicit_insecure_mode():
    parser = cli.build_parser()
    secure = parser.parse_args(
        ["web", "--host", "0.0.0.0", "--remote-token", "x" * 24, "--tls-san", "192.168.1.20"]
    )
    assert secure.insecure_http is False
    assert secure.tls_san == ["192.168.1.20"]

    insecure = parser.parse_args(
        ["web", "--host", "0.0.0.0", "--remote-token", "x" * 24, "--insecure-http"]
    )
    assert insecure.insecure_http is True

    help_text = next(
        action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"
    ).choices["web"].format_help()
    assert "--insecure-http" in help_text
    assert "--tls-san" in help_text
    assert "generates a self-signed certificate" in help_text


def test_generated_tls_is_ecdsa_p256_sha256_with_requested_sans(tmp_path: Path):
    cert_path, key_path, cert = generate_self_signed_tls(
        host="0.0.0.0",
        directory=tmp_path,
        extra_sans=["192.168.1.20", "adb.example.test"],
    )
    assert cert_path.is_file() and key_path.is_file()
    assert cert.issuer == cert.subject
    assert cert.signature_hash_algorithm.name == "sha256"
    assert isinstance(cert.public_key(), ec.EllipticCurvePublicKey)
    assert cert.public_key().curve.name == "secp256r1"

    names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert "adb.example.test" in names.get_values_for_type(x509.DNSName)
    assert "192.168.1.20" in {str(value) for value in names.get_values_for_type(x509.IPAddress)}
    assert "127.0.0.1" in {str(value) for value in names.get_values_for_type(x509.IPAddress)}

    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    assert isinstance(key, ec.EllipticCurvePrivateKey)
    assert key.curve.name == "secp256r1"
    if os.name != "nt":
        assert key_path.stat().st_mode & 0o777 == 0o600
        assert tmp_path.stat().st_mode & 0o777 == 0o700

    checked_cert, checked_key, checked = validate_tls_pair(cert_path, key_path)
    assert checked_cert == cert_path.resolve()
    assert checked_key == key_path.resolve()
    assert checked.serial_number == cert.serial_number


def test_invalid_requested_tls_san_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="Invalid TLS DNS SAN"):
        generate_self_signed_tls(host="0.0.0.0", directory=tmp_path, extra_sans=["bad host/name"])


def test_mismatched_certificate_and_key_are_rejected(tmp_path: Path):
    cert_a, _, _ = generate_self_signed_tls(host="127.0.0.1", directory=tmp_path / "a")
    _, key_b, _ = generate_self_signed_tls(host="127.0.0.1", directory=tmp_path / "b")
    with pytest.raises(ValueError, match="do not match"):
        validate_tls_pair(cert_a, key_b)


def test_remote_serve_auto_generates_tls(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    def fake_create_app(**kwargs):
        captured["create_app"] = kwargs
        return object()

    def fake_run(app, **kwargs):
        captured["app"] = app
        captured["uvicorn"] = kwargs

    import uvicorn

    monkeypatch.setattr(webapp, "create_app", fake_create_app)
    monkeypatch.setattr(uvicorn, "run", fake_run)
    webapp.serve(
        host="0.0.0.0",
        port=9443,
        open_browser=False,
        remote_token="r" * 24,
        tls_dir=tmp_path,
        tls_sans=["192.168.1.20"],
    )

    assert captured["create_app"]["secure_cookie"] is True
    assert Path(captured["uvicorn"]["ssl_certfile"]).is_file()
    assert Path(captured["uvicorn"]["ssl_keyfile"]).is_file()


def test_remote_serve_can_explicitly_use_plain_http(monkeypatch, capsys):
    captured: dict[str, object] = {}

    def fake_create_app(**kwargs):
        captured["create_app"] = kwargs
        return object()

    def fake_run(app, **kwargs):
        captured["uvicorn"] = kwargs

    import uvicorn

    monkeypatch.setattr(webapp, "create_app", fake_create_app)
    monkeypatch.setattr(uvicorn, "run", fake_run)
    webapp.serve(
        host="0.0.0.0",
        port=8080,
        open_browser=False,
        remote_token="r" * 24,
        insecure_http=True,
    )

    assert captured["create_app"]["secure_cookie"] is False
    assert captured["uvicorn"]["ssl_certfile"] is None
    assert captured["uvicorn"]["ssl_keyfile"] is None
    output = capsys.readouterr().out
    assert "plaintext HTTP" in output
    assert "can be intercepted" in output


def test_remote_authentication_is_still_required_for_insecure_http():
    with pytest.raises(AdbgathError, match="remote-token"):
        webapp.serve(host="0.0.0.0", open_browser=False, insecure_http=True)


def test_partial_or_conflicting_tls_configuration_is_rejected(tmp_path: Path):
    cert, key, _ = generate_self_signed_tls(host="127.0.0.1", directory=tmp_path)
    with pytest.raises(AdbgathError, match="supplied together"):
        webapp.serve(host="127.0.0.1", open_browser=False, tls_cert=cert)
    with pytest.raises(AdbgathError, match="cannot be combined"):
        webapp.serve(
            host="127.0.0.1", open_browser=False, tls_cert=cert, tls_key=key, insecure_http=True
        )
