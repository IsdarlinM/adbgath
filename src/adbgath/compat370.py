from __future__ import annotations

_APPLIED = False


def apply() -> None:
    global _APPLIED
    if _APPLIED:
        return
    _APPLIED = True

    from .compat360 import apply as apply_360
    apply_360()

    from .core import auth370 as auth_module
    from .serverroot370 import patch_auth_root
    patch_auth_root(auth_module)

    from .passwordkdf370 import patch_password_kdf
    patch_password_kdf(auth_module)

    from .authpermissions370 import patch_auth_permissions
    patch_auth_permissions(auth_module)

    from .authatomic370 import patch_auth_atomic
    patch_auth_atomic(auth_module)

    from .sessionguard370 import patch_auth_sessions
    patch_auth_sessions(auth_module)

    from . import webapp as webapp_module
    from . import webapp370 as webapp370_module
    from .webapp370 import patch_webapp as patch_auth_webapp
    patch_auth_webapp(webapp_module)

    from .serversecret370 import patch_webapp as patch_server_secret
    patch_server_secret(webapp_module)

    from .csrfkey370 import patch_csrf_key
    patch_csrf_key(webapp370_module)

    from .webauthz370 import patch_webapp as patch_web_authorization
    patch_web_authorization(webapp_module)

    from .validationerrors370 import patch_webapp as patch_validation_errors
    patch_validation_errors(webapp_module)

    from .authorigin370 import patch_webapp as patch_auth_origin
    patch_auth_origin(webapp_module)

    from .websocketexpiry370 import patch_webapp as patch_websocket_expiry
    patch_websocket_expiry(webapp_module)

    from . import cli as cli_module
    from .cli370 import patch_cli as patch_auth_cli
    patch_auth_cli(cli_module)
