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

    from .core import operations as operations_module
    from .webparity372 import patch_operations, patch_service

    patch_operations(operations_module)

    from . import service as service_module

    service_module.WEB_ACTIONS = operations_module.WEB_ACTIONS
    patch_service(service_module)

    from . import webapp as webapp_module

    webapp_module.OPERATIONS = operations_module.OPERATIONS
    webapp_module.WEB_ACTIONS = operations_module.WEB_ACTIONS
    webapp_module.DESTRUCTIVE_ACTIONS = {
        name for name, operation in operations_module.OPERATIONS.items() if operation.destructive
    }
    webapp_module.LONG_RUNNING_ACTIONS = {
        name for name, operation in operations_module.OPERATIONS.items() if operation.long_running
    }

    from .webfinal372 import patch_webapp as patch_final_web

    patch_final_web(webapp_module)

    from .webtls372 import patch_cli as patch_remote_tls_cli
    from .webtls372 import patch_webapp as patch_remote_tls_webapp

    patch_remote_tls_webapp(webapp_module)
    patch_remote_tls_cli(cli_module, webapp_module)

    from .exceptionguard372 import patch_web_server

    patch_web_server(webapp_module)
