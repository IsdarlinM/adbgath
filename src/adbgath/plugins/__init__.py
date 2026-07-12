from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from typing import Any, Protocol

from ..errors import ValidationError

PLUGIN_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")
KNOWN_PERMISSIONS = frozenset({"read_device", "write_device", "network", "filesystem"})


@dataclass(slots=True)
class PluginContext:
    service: Any
    serial: str | None = None
    package: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


class AdbgathPlugin(Protocol):
    name: str
    version: str
    permissions: tuple[str, ...]

    def check_requirements(self) -> list[str]: ...
    def execute(self, context: PluginContext) -> dict[str, Any]: ...


def discover_plugins() -> dict[str, AdbgathPlugin]:
    plugins: dict[str, AdbgathPlugin] = {}
    for entry in entry_points(group="adbgath.plugins"):
        plugin = entry.load()()
        name = str(getattr(plugin, "name", ""))
        if not PLUGIN_NAME_RE.fullmatch(name):
            raise ValidationError(f"Plugin entry {entry.name!r} exposes an invalid name.")
        permissions = tuple(getattr(plugin, "permissions", ()))
        unknown = sorted(set(permissions) - KNOWN_PERMISSIONS)
        if unknown:
            raise ValidationError(f"Plugin {name!r} declares unsupported permissions: {', '.join(unknown)}")
        if name in plugins:
            raise ValidationError(f"Duplicate plugin name: {name}")
        plugins[name] = plugin
    return plugins


def describe_plugin(plugin: AdbgathPlugin) -> dict[str, Any]:
    try:
        missing = list(plugin.check_requirements())
    except Exception as exc:
        missing = [f"requirement check failed: {type(exc).__name__}: {exc}"]
    return {
        "name": plugin.name,
        "version": str(plugin.version),
        "permissions": list(plugin.permissions),
        "ready": not missing,
        "missing_requirements": missing,
    }
