from __future__ import annotations

from typing import Any


def patch_operations(module: Any) -> None:
    if "wireless_qr_create" in module.OPERATIONS:
        return
    Operation, f = module.Operation, module.f
    additions = [
        Operation(
            "wireless_qr_create",
            "Pair using QR",
            "Create an ephemeral Android Wireless Debugging QR session, pair, and optionally connect.",
            "Wireless",
            (
                f("ttl_seconds", "Session lifetime", "number", default=120, minimum=30, maximum=300),
                f("auto_connect", "Connect automatically", "boolean", default=True),
            ),
            destructive=True,
        ),
        Operation(
            "wireless_broker",
            "Wireless event broker",
            "Start, stop, or inspect the shared ADB/mDNS event broker.",
            "Wireless",
            (f("mode", "Mode", "select", choices=("status", "start", "stop"), default="status"),),
        ),
        Operation(
            "schema_status",
            "Database schema",
            "Show migration history, database version, and SQLite integrity status.",
            "System",
        ),
    ]
    for item in additions:
        module.OPERATIONS[item.name] = item
    module.OPERATIONS["inventory"] = Operation(
        "inventory",
        "Inventory",
        "Export, capture, list, or compare incremental device inventories.",
        "Inventory",
        (
            f("mode", "Mode", "select", choices=("export", "capture", "list", "diff"), default="export"),
            f("name", "Capture name"),
            f("before", "Before inventory"),
            f("after", "After inventory"),
            f("limit", "List limit", "number", default=100, minimum=1, maximum=1000),
            f("output", "Output file"),
        ),
    )
    module.WEB_ACTIONS = frozenset(module.OPERATIONS)
