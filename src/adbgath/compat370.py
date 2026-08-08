from __future__ import annotations

_APPLIED = False


def apply() -> None:
    global _APPLIED
    if _APPLIED:
        return
    _APPLIED = True

    from .compat360 import apply as apply_360
    apply_360()

    from . import webapp as webapp_module
    from .webapp370 import patch_webapp as patch_auth_webapp
    patch_auth_webapp(webapp_module)

    from . import cli as cli_module
    from .cli370 import patch_cli as patch_auth_cli
    patch_auth_cli(cli_module)
