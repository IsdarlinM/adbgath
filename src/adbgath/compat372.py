from __future__ import annotations

_APPLIED = False


def apply() -> None:
    global _APPLIED
    if _APPLIED:
        return
    _APPLIED = True

    from .compat371 import apply as apply_371

    apply_371()

    from .core import selfupdate360 as selfupdate_module
    from .selfupdatesafety372 import patch_self_update_safety

    patch_self_update_safety(selfupdate_module)

    from . import cli as cli_module
    from .cliguard372 import patch_cli_input_errors

    patch_cli_input_errors(cli_module)

    from . import webapp as webapp_module
    from .webfinal372 import patch_webapp as patch_final_web

    patch_final_web(webapp_module)
