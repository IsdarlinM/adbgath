from __future__ import annotations

_APPLIED = False


def apply() -> None:
    global _APPLIED
    if _APPLIED:
        return
    _APPLIED = True

    from .compat370 import apply as apply_370
    apply_370()

    from .core import auth370 as auth_module
    from .presetstore371 import patch_auth_presets

    patch_auth_presets(auth_module)

    from . import webapp as webapp_module
    from .webpresets371 import patch_webapp as patch_web_presets
    from .webux371 import patch_webapp as patch_web_ux

    patch_web_presets(webapp_module)
    patch_web_ux(webapp_module)
