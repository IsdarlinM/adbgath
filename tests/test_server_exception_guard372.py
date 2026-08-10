from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from adbgath.exceptionguard372 import patch_web_server
from adbgath.errors import AdbgathError


def _module(*, serve=None, create_app=None):
    return SimpleNamespace(
        serve=serve or (lambda **kwargs: None),
        create_app=create_app or (lambda **kwargs: object()),
        AdbgathError=AdbgathError,
    )


def test_nonzero_server_exit_becomes_adbgath_error():
    module = _module(serve=lambda **kwargs: (_ for _ in ()).throw(SystemExit(1)))
    patch_web_server(module)
    with pytest.raises(AdbgathError, match="host/port"):
        module.serve(host="0.0.0.0", port=50001)


def test_zero_server_exit_is_preserved():
    module = _module(serve=lambda **kwargs: (_ for _ in ()).throw(SystemExit(0)))
    patch_web_server(module)
    with pytest.raises(SystemExit) as caught:
        module.serve()
    assert caught.value.code == 0


@pytest.mark.parametrize(
    "failure",
    [
        OSError("permission denied"),
        sqlite3.DatabaseError("database is malformed"),
        RuntimeError("static assets are unavailable"),
    ],
)
def test_recoverable_web_initialization_failures_become_adbgath_errors(failure):
    module = _module(create_app=lambda **kwargs: (_ for _ in ()).throw(failure))
    patch_web_server(module)
    with pytest.raises(AdbgathError, match="Web application initialization failed"):
        module.create_app()


def test_programming_errors_remain_visible_to_outer_internal_error_boundary():
    module = _module(create_app=lambda **kwargs: (_ for _ in ()).throw(AttributeError("bug")))
    patch_web_server(module)
    with pytest.raises(AttributeError, match="bug"):
        module.create_app()
