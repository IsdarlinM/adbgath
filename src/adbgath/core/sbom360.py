from __future__ import annotations

import hashlib
import importlib.metadata
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _components() -> list[dict[str, str]]:
    values = []
    for dist in sorted(importlib.metadata.distributions(), key=lambda d: (d.metadata.get("Name") or "").lower()):
        name = dist.metadata.get("Name")
        if not name:
            continue
        values.append({"name": name, "version": dist.version, "purl": f"pkg:pypi/{name.lower()}@{dist.version}"})
    return values


def generate_sbom(fmt: str = "cyclonedx") -> dict[str, Any]:
    components = _components()
    now = datetime.now(UTC).isoformat()
    if fmt == "cyclonedx":
        return {
            "bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
            "metadata": {"timestamp": now, "component": {"type": "application", "name": "adbgath"}},
            "components": [{"type": "library", **item} for item in components],
        }
    if fmt == "spdx":
        return {
            "spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": "SPDXRef-DOCUMENT",
            "name": "adbgath-runtime", "creationInfo": {"created": now, "creators": ["Tool: ADB-Gath"]},
            "packages": [
                {"name": item["name"], "SPDXID": f"SPDXRef-Package-{index}", "versionInfo": item["version"], "downloadLocation": "NOASSERTION"}
                for index, item in enumerate(components, 1)
            ],
        }
    raise ValueError("SBOM format must be cyclonedx or spdx")


def write_sbom(path: str | Path, fmt: str = "cyclonedx") -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    data = generate_sbom(fmt)
    encoded = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    target.write_bytes(encoded)
    return {"path": str(target), "sha256": hashlib.sha256(encoded).hexdigest(), "format": fmt, "components": len(data.get("components") or data.get("packages") or [])}
