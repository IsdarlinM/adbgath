from __future__ import annotations

from typing import Any


def patch_operations(module: Any) -> None:
    Operation = module.Operation
    f = module.f
    operations = module.OPERATIONS
    operations["devices"] = Operation(
        "devices", "Devices", "List connected ADB targets with optional fast mode.", "Device",
        (f("fast", "Fast mode", "boolean"), f("details", "Probe root details", "boolean", default=True)),
    )
    additions = [
        Operation("wireless_status", "Wireless status", "Inspect ADB server, mDNS, discovered services, connections, and known targets.", "Wireless", (f("discover", "Discover services now", "boolean", default=True),)),
        Operation("wireless_discover", "Discover wireless devices", "Discover pairing and connection services through ADB mDNS.", "Wireless", (f("refresh", "Bypass short cache", "boolean", default=True), f("detailed", "Use detailed proto-text discovery", "boolean", default=True))),
        Operation("wireless_pair", "Pair using code", "Pair Android 11+ using the temporary pairing endpoint and six-digit code shown by Android.", "Wireless", (f("target", "Pairing host:port", required=True, placeholder="192.168.1.50:37123"), f("pairing_code", "Six-digit pairing code", "secret", required=True, placeholder="000000")), destructive=True),
        Operation("wireless_connect", "Wireless connect", "Connect after pairing using the separate connection endpoint shown by Android.", "Wireless", (f("target", "Connection host:port", required=True, placeholder="192.168.1.50:41267"),)),
        Operation("wireless_disconnect", "Wireless disconnect", "Disconnect an active wireless ADB endpoint.", "Wireless", (f("target", "Connection host:port", required=True),)),
        Operation("wireless_auto_connect", "Auto-connect discovered targets", "Connect to all discovered _adb-tls-connect services.", "Wireless"),
        Operation("wireless_diagnose", "Wireless diagnostics", "Check Platform-Tools, mDNS enablement/backend, discovery, and safe repairs.", "Wireless", (f("fix", "Apply safe ADB mDNS repair", "boolean"), f("persist", "Persist repair in ADB-Gath environment", "boolean"))),
        Operation("wireless_known", "Known wireless targets", "List locally remembered wireless targets and last-seen state.", "Wireless"),
        Operation("wireless_alias", "Set wireless alias", "Assign a local human-readable alias to a known target.", "Wireless", (f("identifier", "ID, serial, instance, or current alias", required=True), f("alias", "New alias", required=True))),
        Operation("wireless_forget", "Forget local wireless target", "Remove ADB-Gath's local record. Android pairing must be revoked on the device.", "Wireless", (f("identifier", "ID, serial, instance, or alias", required=True),), destructive=True),
        Operation("wireless_tcpip", "Legacy TCP/IP mode", "Switch an explicitly selected USB-authorized device to legacy ADB TCP/IP mode.", "Wireless", (f("port", "TCP port", "number", default=5555, minimum=1, maximum=65535),), destructive=True),
        Operation("metrics", "Local performance metrics", "Review or clear local ADB timing, transfer, return-code, and cancellation telemetry.", "System", (f("mode", "Mode", "select", choices=("summary", "list", "clear"), default="summary"), f("limit", "List limit", "number", default=200, minimum=1, maximum=5000))),
    ]
    for operation in additions:
        operations[operation.name] = operation
    module.WEB_ACTIONS = frozenset(operations)
