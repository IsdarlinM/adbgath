from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class HostPort:
    host: str
    port: int

    @property
    def endpoint(self) -> str:
        return f"[{self.host}]:{self.port}" if ":" in self.host else f"{self.host}:{self.port}"

    def to_dict(self) -> dict[str, Any]:
        return {"host": self.host, "port": self.port, "endpoint": self.endpoint}


WirelessServiceType = Literal["pairing", "connect", "legacy", "unknown"]


@dataclass(slots=True)
class WirelessService:
    instance: str
    service: str
    host: str
    port: int
    service_type: WirelessServiceType = "unknown"
    ipv4: str = ""
    ipv6: str = ""
    hostname: str = ""
    serial: str = ""
    model: str = ""
    given_name: str = ""
    sdk: str = ""
    mdns_service_version: str = ""
    source: str = "mdns"
    discovered_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def endpoint(self) -> str:
        return f"[{self.host}]:{self.port}" if ":" in self.host else f"{self.host}:{self.port}"

    @property
    def requires_pairing(self) -> bool:
        return self.service_type == "pairing"

    @property
    def connectable(self) -> bool:
        return self.service_type in {"connect", "legacy"}

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update({"endpoint": self.endpoint, "requires_pairing": self.requires_pairing, "connectable": self.connectable})
        return data
