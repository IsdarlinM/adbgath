from __future__ import annotations

from pathlib import Path

import pytest

from adbgath.errors import ValidationError


def test_audit_and_lab_job_limits_reject_non_numeric_values(service):
    with pytest.raises(ValidationError, match="Result limit"):
        service.dispatch("audit", {"mode": "list", "limit": "bad"})
    with pytest.raises(ValidationError, match="Result limit"):
        service.dispatch("lab_jobs", {"limit": object()})


def test_lab_submit_nested_payload_must_be_json_object(service):
    with pytest.raises(ValidationError, match="Lab job payload must be a JSON object"):
        service.dispatch(
            "lab_job_submit",
            {
                "agent": "missing",
                "action": "devices",
                "payload": ["not", "an", "object"],
                "role": "viewer",
            },
        )

    with pytest.raises(ValidationError, match="must be valid JSON"):
        service.dispatch(
            "lab_pool_submit",
            {
                "pool": "missing",
                "action": "devices",
                "payload": "{broken-json",
                "role": "viewer",
            },
        )


def test_plugin_sign_invalid_manifest_json_is_validation_error(service, tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{not-json", encoding="utf-8")
    plugin = tmp_path / "plugin.py"
    plugin.write_text("VALUE = 1\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="invalid JSON"):
        service.plugin_sign(
            str(manifest),
            str(plugin),
            str(tmp_path / "missing-private-key.pem"),
            str(tmp_path / "signature.json"),
        )


def test_plugin_publisher_missing_key_is_validation_error(service, tmp_path: Path):
    with pytest.raises(ValidationError, match="file not found"):
        service.plugin_publisher("add", name="publisher", public_key=str(tmp_path / "missing.pem"))


def test_duplicate_lab_ca_creation_is_validation_error(service, tmp_path: Path):
    pki = tmp_path / "pki"
    service.lab_pki_init(str(pki))
    with pytest.raises(ValidationError, match="Lab CA initialization"):
        service.lab_pki_init(str(pki))
