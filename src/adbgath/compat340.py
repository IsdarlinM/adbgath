from __future__ import annotations

_APPLIED = False


def apply() -> None:
    global _APPLIED
    if _APPLIED:
        return
    _APPLIED = True

    try:
        from .compat330 import apply as apply_330
        apply_330()
    except ImportError:
        pass

    from .modules.wireless import manager as manager_module
    from .modules.wireless.manager340 import patch_wireless_manager
    patch_wireless_manager(manager_module)

    from .core import storage as storage_module
    from .core.storage340 import patch_storage
    patch_storage(storage_module)

    from .core import capabilities as capabilities_module
    from .core.capabilities340 import patch_capabilities
    patch_capabilities(capabilities_module)

    from .core import operations as operations_module
    from .core.operations340 import patch_operations
    patch_operations(operations_module)

    from . import service as service_module
    from .service340 import patch_service
    service_module.WEB_ACTIONS = operations_module.WEB_ACTIONS
    patch_service(service_module)

    from . import cli as cli_module
    from .cli340 import patch_cli
    patch_cli(cli_module)

    from . import webapp as webapp_module
    from .webapp340 import patch_webapp
    webapp_module.OPERATIONS = operations_module.OPERATIONS
    webapp_module.WEB_ACTIONS = operations_module.WEB_ACTIONS
    webapp_module.DESTRUCTIVE_ACTIONS = {name for name, op in operations_module.OPERATIONS.items() if op.destructive}
    webapp_module.LONG_RUNNING_ACTIONS = {name for name, op in operations_module.OPERATIONS.items() if op.long_running}
    patch_webapp(webapp_module)
