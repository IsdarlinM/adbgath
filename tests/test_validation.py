from __future__ import annotations

import pytest

from adbgath.errors import ValidationError
from adbgath.validation import (
    ensure_within,
    validate_host_port,
    validate_package,
    validate_remote_path,
    validate_serial,
)


def test_valid_identifiers(tmp_path):
    assert validate_serial("emulator-5554") == "emulator-5554"
    assert validate_package("com.example.app") == "com.example.app"
    assert validate_host_port("192.168.1.5:5555") == "192.168.1.5:5555"
    assert validate_remote_path("/data/app/com.example/base.apk").endswith("base.apk")
    assert ensure_within(tmp_path / "child.txt", tmp_path) == (tmp_path / "child.txt").resolve()


@pytest.mark.parametrize("value", ["serial;whoami", "serial $(id)", "", "a/b"])
def test_rejects_unsafe_serial(value):
    with pytest.raises(ValidationError):
        validate_serial(value)


@pytest.mark.parametrize("value", ["com", "com.example;id", "../package", "com.example-app"])
def test_rejects_invalid_package(value):
    with pytest.raises(ValidationError):
        validate_package(value)


def test_workspace_escape_rejected(tmp_path):
    with pytest.raises(ValidationError):
        ensure_within(tmp_path.parent / "outside.txt", tmp_path)
