from __future__ import annotations

import adbgath
from adbgath.core.migrations import CURRENT_SCHEMA_VERSION


def test_release_version_is_371_while_workspace_schema_remains_360(service):
    assert adbgath.__version__ == "3.7.1"
    assert CURRENT_SCHEMA_VERSION == 360
    status = service.store.schema_status()
    assert status["database_version"] == 360
    assert status["integrity"] == "ok"
    assert any(item["version"] == 360 for item in status["migrations"])
