from __future__ import annotations

import pytest

from adbgath.core.operations import OPERATIONS, validate_operation_payload


def test_every_registered_web_operation_rejects_unknown_fields():
    for action in sorted(OPERATIONS):
        with pytest.raises(ValueError, match="Unsupported fields"):
            validate_operation_payload(action, {"__unexpected_field__": "value"})


def test_operation_validator_rejects_unknown_action():
    with pytest.raises(ValueError, match="Unsupported action"):
        validate_operation_payload("__not_registered__", {})
