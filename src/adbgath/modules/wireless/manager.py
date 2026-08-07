from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ...errors import AdbgathError
from ...models import CommandResult, WirelessService
from ...validation import parse_host_port, validate_alias, validate_pairing_code, validate_positive_int

PROTO_BLOCK_RE = re.compile(r"service\s*\{(?P<body>.*?)\n\s*\}", re.DOTALL)
PROTO_FIELD_RE = re.compile(r'^\s*([A-Za-z0-9_]+):\s*"?([^"\n]+?)"?\s*$', re.MULTILINE)
LEGACY_LINE_RE = re.compile(
    r"^(?P<instance>\S+)\s+(?P<service>_(?:adb|adb-tls-pairing|adb-tls-connect)\._tcp\.?)\s+"
    r"(?P<endpoint>\[[^\]]+\]:\d+|[^\s:]+:\d+)$"
)
VERSION_RE = re.compile(r"(?:Version|version)\s+(?P<version>\d+(?:\.\d+){1,3})")


def _service_type(service: str) -> str:
    normalized = service.rstrip(".")
    if "adb-tls-pairing" in normalized:
        return "pairing"
    if "adb-tls-connect" in normalized:
        return "connect"
    if normalized.startswith("_adb._tcp"):
        return "legacy"
    return "unknown"


def parse_server_status(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for raw in text.splitlines():
        line = raw.strip().strip("{}")
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().strip('"')
        value = value.strip().rstrip(",").strip('"')
        if value.lower() in {"true", "false"}:
            result[key] = value.lower() == "true"
        elif value.isdigit():
            result[key] = int(value)
        else:
            result[key] = value
    return result


def _from_fields(fields: dict[str, str], *, source: str) -> WirelessService | None:
    service_name = fields.get("service", "")
    port_text = fields.get("port", "")
    if not service_name or not port_text.isdigit():
        return None
    host = fields.get("ipv4") or fields.get("hostname") or fields.get("ipv6") or ""
    if not host:
        return None
    return WirelessService(
        instance=fields.get("instance", ""),
        service=service_name.rstrip("."),
        host=host,
        port=int(port_text),
        service_type=_service_type(service_name),
        ipv4=fields.get("ipv4", ""),
        ipv6=fields.get("ipv6", ""),
        hostname=fields.get("hostname", ""),
        serial=fields.get("serial", ""),
        model=fields.get("product_model", ""),
        given_name=fields.get("given_name", ""),
        sdk=fields.get("build_version_sdk_full", ""),
        mdns_service_version=fields.get("mdns_service_version", ""),
        source=source,
    )


def parse_mdns_output(text: str) -> list[WirelessService]:
    services: list[WirelessService] = []
    seen: set[tuple[str, str, int]] = set()
    for match in PROTO_BLOCK_RE.finditer(text):
        fields = {key: value.strip() for key, value in PROTO_FIELD_RE.findall(match.group("body"))}
        service = _from_fields(fields, source="track-services-proto-text")
        if service:
            key = (service.service, service.host, service.port)
            if key not in seen:
                seen.add(key)
                services.append(service)
    for raw in text.splitlines():
        match = LEGACY_LINE_RE.match(raw.strip())
        if not match:
            continue
        endpoint = parse_host_port(match.group("endpoint"))
        service_name = match.group("service").rstrip(".")
        service = WirelessService(
            instance=match.group("instance"), service=service_name, host=endpoint.host, port=endpoint.port,
            service_type=_service_type(service_name),
            ipv4=endpoint.host if ":" not in endpoint.host else "",
            ipv6=endpoint.host if ":" in endpoint.host else "", source="mdns-services",
        )
        key = (service.service, service.host, service.port)
        if key not in seen:
            seen.add(key)
            services.append(service)
    return services


class WirelessManager:
    def __init__(self, adb: Any, store: Any, *, home: Path) -> None:
        self.adb = adb
        self.store = store
        self.home = home
        self._last_discovery: tuple[float, list[dict[str, Any]]] | None = None

    @staticmethod
    def _version_number(text: str) -> str:
        matches = VERSION_RE.findall(text)
        return matches[-1] if matches else "unknown"

    def _save_service(self, service: WirelessService, *, state: str = "discovered") -> dict[str, Any]:
        item = service.to_dict()
        return self.store.upsert_wireless_device({
            **item,
            "state": state,
            "pairing_port": service.port if service.requires_pairing else None,
            "connect_port": service.port if service.connectable else None,
            "metadata": {
                "service": service.service, "service_type": service.service_type, "source": service.source,
                "sdk": service.sdk, "mdns_service_version": service.mdns_service_version,
                "ipv4": service.ipv4, "ipv6": service.ipv6,
            },
        })

    def discover(self, *, refresh: bool = False, detailed: bool = True) -> dict[str, Any]:
        now = time.monotonic()
        if not refresh and self._last_discovery and now - self._last_discovery[0] < 3:
            return {"cached": True, "services": self._last_discovery[1]}
        attempts: list[dict[str, Any]] = []
        services: list[WirelessService] = []
        if detailed and hasattr(self.adb, "run_bounded"):
            tracked = self.adb.run_bounded(["mdns", "track-services", "--proto-text"], duration=2, check=False)
            attempts.append(tracked.to_dict())
            services = parse_mdns_output(tracked.stdout)
        if not services:
            legacy = self.adb.run(["mdns", "services"], timeout=15, check=False)
            attempts.append(legacy.to_dict())
            services = parse_mdns_output(legacy.stdout)
        stored = [self._save_service(service) for service in services]
        data = [service.to_dict() for service in services]
        self._last_discovery = (now, data)
        return {
            "cached": False, "service_count": len(data),
            "pairing_services": [item for item in data if item["requires_pairing"]],
            "connect_services": [item for item in data if item["connectable"]],
            "services": data, "stored": stored, "attempts": attempts,
        }

    def _context_for_endpoint(self, endpoint: str) -> dict[str, Any]:
        if not self._last_discovery:
            return {}
        for service in self._last_discovery[1]:
            if service.get("endpoint") == endpoint:
                return {
                    "serial": service.get("serial") or None, "instance": service.get("instance") or endpoint,
                    "model": service.get("model") or None, "given_name": service.get("given_name") or None,
                    "hostname": service.get("hostname") or None,
                }
        return {}

    def pair(self, target: str, pairing_code: str) -> CommandResult:
        parsed = parse_host_port(target)
        endpoint = parsed.endpoint
        code = validate_pairing_code(pairing_code)
        result = self.adb.run_interactive(["pair", endpoint], input_data=code, timeout=45, check=False)
        result.metadata.update({"endpoint": endpoint, "pairing_code_redacted": True})
        context = self._context_for_endpoint(endpoint)
        self.store.upsert_wireless_device({
            **context, "instance": context.get("instance") or endpoint, "host": parsed.host,
            "pairing_port": parsed.port, "state": "paired" if result.ok else "pairing-failed",
            "metadata": {"last_pair_result": result.stdout.strip() or result.stderr.strip()},
        })
        return result

    def connect(self, target: str) -> CommandResult:
        parsed = parse_host_port(target)
        result = self.adb.run(["connect", parsed.endpoint], timeout=30, check=False)
        context = self._context_for_endpoint(parsed.endpoint)
        self.store.upsert_wireless_device({
            **context, "instance": context.get("instance") or parsed.endpoint, "host": parsed.host,
            "connect_port": parsed.port, "state": "connected" if result.ok else "connection-failed",
            "metadata": {"last_connect_result": result.stdout.strip() or result.stderr.strip()},
        })
        return result

    def disconnect(self, target: str) -> CommandResult:
        parsed = parse_host_port(target)
        result = self.adb.run(["disconnect", parsed.endpoint], timeout=30, check=False)
        self.store.upsert_wireless_device({
            "instance": parsed.endpoint, "host": parsed.host, "connect_port": parsed.port,
            "state": "disconnected" if result.ok else "disconnect-failed",
            "metadata": {"last_disconnect_result": result.stdout.strip() or result.stderr.strip()},
        })
        return result

    def status(self, *, discover: bool = True) -> dict[str, Any]:
        version = self.adb.version()
        server = self.adb.run(["server-status"], timeout=15, check=False)
        mdns = self.adb.run(["mdns", "check"], timeout=15, check=False)
        devices = [device.to_dict() for device in self.adb.devices()]
        discovery: dict[str, Any] = {"services": []}
        if discover:
            try:
                discovery = self.discover(refresh=True)
            except AdbgathError as exc:
                discovery = {"services": [], "error": str(exc)}
        return {
            "adb_version": self._version_number(version.stdout), "adb_version_raw": version.stdout.strip(),
            "server_status": parse_server_status(server.stdout), "server_status_raw": server.stdout.strip(),
            "mdns": {"ok": mdns.ok, "output": mdns.stdout.strip() or mdns.stderr.strip()},
            "devices": devices, "discovery": discovery, "known_devices": self.store.list_wireless_devices(),
        }

    def _environment_file(self) -> Path:
        return self.home / "wireless.env"

    def _persist_environment(self, values: dict[str, str]) -> Path:
        target = self._environment_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        existing: dict[str, str] = {}
        if target.is_file():
            for line in target.read_text(encoding="utf-8-sig").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    key, value = line.split("=", 1)
                    existing[key.strip()] = value.strip()
        existing.update(values)
        allowed = {key: value for key, value in existing.items() if key in {"ADB_MDNS", "ADB_MDNS_OPENSCREEN", "ADB_BURST_MODE"}}
        target.write_text("# Managed by ADB-Gath. No secrets are stored here.\n" + "\n".join(f"{key}={value}" for key, value in sorted(allowed.items())) + "\n", encoding="utf-8")
        return target

    def diagnose(self, *, fix: bool = False, persist: bool = False) -> dict[str, Any]:
        status = self.status(discover=True)
        server = status.get("server_status", {})
        version_text = status.get("adb_version", "unknown")
        try:
            major = int(str(version_text).split(".", 1)[0])
        except ValueError:
            major = 0
        services = status.get("discovery", {}).get("services", [])
        checks = [
            {"name": "adb-version", "ok": major >= 37, "value": version_text, "recommendation": "Use SDK Platform-Tools 37.0.0+ for current wireless diagnostics."},
            {"name": "mdns-enabled", "ok": server.get("mdns_enabled") is True, "value": server.get("mdns_enabled", "unknown"), "recommendation": "Set ADB_MDNS=1 and restart the ADB server."},
            {"name": "mdns-backend", "ok": str(server.get("mdns_backend", "")).upper() == "LIBADBMDNS", "value": server.get("mdns_backend", "unknown"), "recommendation": "Set ADB_MDNS_OPENSCREEN=0 and restart the ADB server."},
            {"name": "mdns-services", "ok": bool(services), "value": len(services), "recommendation": "Enable Wireless debugging and verify that the network permits multicast DNS."},
        ]
        repairs: list[dict[str, Any]] = []
        if fix:
            values = {"ADB_MDNS": "1", "ADB_MDNS_OPENSCREEN": "0"}
            self.adb.env.update(values)
            if persist:
                path = self._persist_environment(values)
                repairs.append({"name": "persist-wireless-environment", "ok": True, "path": str(path)})
            stopped = self.adb.run(["kill-server"], timeout=15, check=False)
            started = self.adb.run(["start-server"], timeout=30, check=False)
            self.adb.reload_environment()
            repairs.extend([
                {"name": "adb-kill-server", "ok": stopped.ok, "output": stopped.stdout or stopped.stderr},
                {"name": "adb-start-server", "ok": started.ok, "output": started.stdout or started.stderr},
            ])
        return {
            "ok": all(item["ok"] for item in checks), "checks": checks, "repairs": repairs, "status": status,
            "notes": ["The pairing port and connection port are normally different.", "Pairing codes are accepted through stdin and are never stored.", "QR pairing is intentionally outside this release; code-based pairing is supported."],
        }

    def auto_connect(self) -> dict[str, Any]:
        discovery = self.discover(refresh=True)
        results = [self.connect(service["endpoint"]).to_dict() for service in discovery.get("connect_services", [])]
        return {"attempted": len(results), "results": results}

    def tcpip(self, serial: str, port: int = 5555) -> CommandResult:
        return self.adb.run(["tcpip", str(validate_positive_int(port, maximum=65535))], serial=serial, timeout=30, check=False)

    def known(self) -> list[dict[str, Any]]:
        return self.store.list_wireless_devices()

    def forget(self, identifier: str) -> dict[str, Any]:
        item = self.store.forget_wireless_device(identifier)
        return {"forgotten": item, "note": "This only removes ADB-Gath's local record. Forget the workstation on Android to revoke pairing."}

    def alias(self, identifier: str, alias: str) -> dict[str, Any]:
        return self.store.set_wireless_alias(identifier, validate_alias(alias))

    def watch(self, *, interval: int = 3, duration: int = 0) -> Iterator[dict[str, Any]]:
        interval = validate_positive_int(interval, maximum=300)
        if duration:
            duration = validate_positive_int(duration, maximum=86400)
        started = time.monotonic()
        previous = ""
        while not duration or time.monotonic() - started < duration:
            snapshot = self.discover(refresh=True)
            current = json.dumps(snapshot.get("services", []), sort_keys=True)
            if current != previous:
                previous = current
                yield {"timestamp": datetime.now(UTC).isoformat(), "services": snapshot.get("services", [])}
            time.sleep(interval)
