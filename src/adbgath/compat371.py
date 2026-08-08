from __future__ import annotations

_APPLIED = False


def apply() -> None:
    global _APPLIED
    if _APPLIED:
        return
    _APPLIED = True

    from .compat370 import apply as apply_370
    apply_370()

    from . import webapp as webapp_module
    from .webux371 import patch_webapp

    patch_webapp(webapp_module)
