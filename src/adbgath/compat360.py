from __future__ import annotations

_APPLIED = False


def apply() -> None:
    global _APPLIED
    if _APPLIED:
        return
    _APPLIED = True

    from .compat340 import apply as apply_340
    apply_340()

    from . import adb as adb_module
    from .adb360 import patch_adb
    patch_adb(adb_module)

    from .core import storage as storage_module
    from .core.storage360 import patch_storage
    patch_storage(storage_module)

    from .core import operations as operations_module
    from .core.operations360 import patch_operations
    patch_operations(operations_module)

    from . import service as service_module
    from .service360 import patch_service
    service_module.WEB_ACTIONS = operations_module.WEB_ACTIONS
    patch_service(service_module)

    from . import cli as cli_module
    from .cli360 import patch_cli
    patch_cli(cli_module)

    from . import webapp as webapp_module
    from .webapp360 import patch_webapp
    webapp_module.OPERATIONS = operations_module.OPERATIONS
    webapp_module.WEB_ACTIONS = operations_module.WEB_ACTIONS
    webapp_module.DESTRUCTIVE_ACTIONS = {name for name, op in operations_module.OPERATIONS.items() if op.destructive}
    webapp_module.LONG_RUNNING_ACTIONS = {name for name, op in operations_module.OPERATIONS.items() if op.long_running}
    patch_webapp(webapp_module)
