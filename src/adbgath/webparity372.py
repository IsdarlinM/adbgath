from __future__ import annotations

from dataclasses import replace
from typing import Any, Literal

from .errors import ValidationError


_FIELD_TYPES = Literal[
    "text",
    "number",
    "boolean",
    "select",
    "file",
    "textarea",
    "list",
    "secret",
]

_LOG_FORMATS = (
    "brief",
    "long",
    "process",
    "raw",
    "tag",
    "thread",
    "threadtime",
    "time",
    "year",
    "zone",
)


def patch_operations(module: Any) -> None:
    """Close Web/CLI capability gaps without changing the stable 3.6 catalog source."""
    if getattr(module, "_adbgath_web_parity_372_patched", False):
        return

    # OperationField uses a postponed ``FieldType`` annotation. Rebinding the
    # module alias keeps runtime type introspection aligned with the already
    # supported secret fields used by Wireless pairing and evidence governance.
    module.FieldType = _FIELD_TYPES

    install_set = module.OPERATIONS["install_set"]
    module.OPERATIONS["install_set"] = replace(
        install_set,
        fields=(
            module.f("source", "Directory or .apks file", required=True),
            module.f("replace_existing", "Replace existing", "boolean", default=True),
            module.f("grant_runtime_permissions", "Grant runtime permissions", "boolean", default=False),
        ),
    )

    logs_capture = module.OPERATIONS["logs_capture"]
    module.OPERATIONS["logs_capture"] = replace(
        logs_capture,
        fields=(
            module.f("duration", "Duration", "number", default=30, minimum=1, maximum=86400),
            module.f("package", "Package"),
            module.f("pid", "Process ID", "number", minimum=1),
            module.f("regex", "Regex"),
            module.f("filters", "Logcat filters", "list"),
            module.f("output", "Output file"),
            module.f("clear", "Clear before capture", "boolean", default=False),
            module.f("format", "Format", "select", choices=_LOG_FORMATS, default="threadtime"),
        ),
    )

    update = module.OPERATIONS["update"]
    module.OPERATIONS["update"] = replace(
        update,
        fields=(
            module.f(
                "mode",
                "Mode",
                "select",
                choices=("auto", "force", "check", "plan", "install", "rollback"),
                default="auto",
            ),
            module.f("archive", "Local verified archive"),
            module.f("checksum", "SHA-256"),
        ),
    )

    if "inventory_watch" not in module.OPERATIONS:
        module.OPERATIONS["inventory_watch"] = module.Operation(
            "inventory_watch",
            "Watch inventory changes",
            "Watch an authorized device for bounded package/inventory changes.",
            "Inventory",
            (
                module.f("interval", "Polling interval", "number", default=10, minimum=2, maximum=3600),
                module.f("duration", "Watch duration", "number", default=60, minimum=1, maximum=86400),
            ),
            long_running=True,
        )

    module.WEB_ACTIONS = frozenset(module.OPERATIONS)
    module._adbgath_web_parity_372_patched = True


def patch_service(module: Any) -> None:
    cls = module.AdbgathService
    if getattr(cls, "_adbgath_web_parity_372_patched", False):
        return

    original_dispatch = cls.dispatch

    def dispatch(self, action: str, payload: dict[str, Any]):
        if action == "install_set":
            return self.install_apk_set(
                payload.get("device"),
                payload.get("source", ""),
                user=payload.get("user"),
                replace_existing=bool(payload.get("replace_existing", True)),
                grant_runtime_permissions=bool(payload.get("grant_runtime_permissions", False)),
            ).to_dict()

        if action == "inventory_watch":
            duration = int(payload.get("duration", 60))
            if duration <= 0:
                raise ValidationError("Web inventory watch requires a bounded positive duration.")
            return list(
                self.inventory_watch(
                    payload.get("device"),
                    interval=int(payload.get("interval", 10)),
                    duration=duration,
                    user=payload.get("user"),
                )
            )

        return original_dispatch(self, action, payload)

    cls.dispatch = dispatch
    cls._adbgath_web_parity_372_patched = True
