from __future__ import annotations

from types import SimpleNamespace

import pytest

from adbgath.exceptionguard372 import patch_web_server
from adbgath.errors import AdbgathError


def test_nonzero_server_exit_becomes_adbgath_error():
    module = SimpleNamespace(
        serve=lambda **kwargs: (_ for _ in ()).throw(SystemExit(1)),
        AdbgathError=AdbgathError,
    )
    patch_web_server(module)
    with pytest.raises(AdbgathError, match="host/port"):
        module.serve(host="0.0.0.0", port=50001)


def test_zero_server_exit_is_preserved():
    module = SimpleNamespace(
        serve=lambda **kwargs: (_ for _ in ()).throw(SystemExit(0)),
        AdbgathError=AdbgathError,
    )
    patch_web_server(module)
    with pytest.raises(SystemExit) as caught:
        module.serve()
    assert caught.value.code == 0
