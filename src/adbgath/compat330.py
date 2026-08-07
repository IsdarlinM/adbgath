from __future__ import annotations

_APPLIED = False


def apply() -> None:
    global _APPLIED
    if _APPLIED:
        return
    _APPLIED = True

    from . import models as models_module
    from .models330 import HostPort, WirelessService, WirelessServiceType

    models_module.HostPort = HostPort
    models_module.WirelessService = WirelessService
    models_module.WirelessServiceType = WirelessServiceType

    from . import validation as validation_module
    from .validation330 import parse_host_port, validate_alias, validate_host_port, validate_pairing_code

    validation_module.parse_host_port = parse_host_port
    validation_module.validate_host_port = validate_host_port
    validation_module.validate_pairing_code = validate_pairing_code
    validation_module.validate_alias = validate_alias

    from . import adb as adb_module
    from .adb330 import AdbClient, UnavailableAdbClient

    adb_module.AdbClient = AdbClient
    adb_module.UnavailableAdbClient = UnavailableAdbClient

    from .core import operations as operations_module
    from .core.operations330 import patch_operations

    patch_operations(operations_module)

    from .core import storage as storage_module
    from .core.storage330 import ProjectStore

    storage_module.ProjectStore = ProjectStore

    from .core import capabilities as capabilities_module
    from .core.capabilities330 import CapabilityDetector

    capabilities_module.CapabilityDetector = CapabilityDetector

    from . import service as service_module
    from .service330 import patch_service

    service_module.WEB_ACTIONS = operations_module.WEB_ACTIONS
    patch_service(service_module)

    from . import cli as cli_module
    from .cli330 import patch_cli

    patch_cli(cli_module)

    from . import webapp as webapp_module
    from .webapp330 import patch_webapp

    webapp_module.OPERATIONS = operations_module.OPERATIONS
    webapp_module.WEB_ACTIONS = operations_module.WEB_ACTIONS
    webapp_module.DESTRUCTIVE_ACTIONS = {
        name for name, operation in operations_module.OPERATIONS.items() if operation.destructive
    }
    webapp_module.LONG_RUNNING_ACTIONS = {
        name for name, operation in operations_module.OPERATIONS.items() if operation.long_running
    }
    patch_webapp(webapp_module)
