from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adbgath import __version__

from .files import atomic_write_json, sha256_file

DEFAULT_PATTERNS: dict[str, re.Pattern[str]] = {
    "authorization": re.compile(r"(?i)(authorization\s*[:=]\s*)(bearer\s+)?[^\s,;]+"),
    "cookie": re.compile(r"(?i)(cookie\s*[:=]\s*)[^\r\n]+"),
    "token": re.compile(r"(?i)((?:access|refresh|id)?_?token\s*[:=]\s*)[\"']?[^\s\"',;]+"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "phone": re.compile(r"(?<!\d)(?:\+?\d[\d .()-]{7,}\d)(?!\d)"),
}


class Redactor:
    def __init__(self, patterns: dict[str, re.Pattern[str]] | None = None) -> None:
        self.patterns = patterns or DEFAULT_PATTERNS

    def redact(self, value: str) -> str:
        output = value
        for name, pattern in self.patterns.items():
            if name in {"authorization", "cookie", "token"}:
                output = pattern.sub(lambda match: f"{match.group(1)}<REDACTED>", output)
            else:
                output = pattern.sub(f"<{name.upper()}_REDACTED>", output)
        return output

    def redact_file(self, source: Path, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.redact(source.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")
        return destination


@dataclass(slots=True)
class ArtifactRecord:
    path: str
    sha256: str
    size: int
    media_type: str = "application/octet-stream"
    source_command: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    redacted_copy: str | None = None


@dataclass(slots=True)
class EvidenceManifest:
    tool: str = "adbgath"
    tool_version: str = __version__
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None
    device_serial: str | None = None
    build_fingerprint: str | None = None
    adb_version: str | None = None
    project_id: str | None = None
    session_id: str | None = None
    commands: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[ArtifactRecord] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add_command(self, result: Any) -> None:
        if hasattr(result, "to_dict"):
            result = result.to_dict()
        self.commands.append(
            {
                "command": list(result.get("command", [])),
                "returncode": int(result.get("returncode", 0)),
                "ok": bool(result.get("ok", False)),
                "duration_ms": int(result.get("duration_ms", 0)),
                "timestamp": result.get("timestamp"),
            }
        )

    def add_artifact(
        self,
        path: Path,
        *,
        media_type: str = "application/octet-stream",
        source_command: list[str] | None = None,
        redacted_copy: Path | None = None,
    ) -> ArtifactRecord:
        record = ArtifactRecord(
            path=str(path),
            sha256=sha256_file(path),
            size=path.stat().st_size,
            media_type=media_type,
            source_command=source_command or [],
            redacted_copy=str(redacted_copy) if redacted_copy else None,
        )
        self.artifacts.append(record)
        return record

    def finalize(self) -> None:
        self.completed_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            **{key: value for key, value in asdict(self).items() if key != "artifacts"},
            "artifacts": [asdict(item) for item in self.artifacts],
        }

    def write(self, path: Path) -> Path:
        self.finalize()
        atomic_write_json(path, self.to_dict())
        return path

    def canonical_bytes(self) -> bytes:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")

    def hmac_sha256(self, key: str | bytes) -> str:
        secret = key.encode("utf-8") if isinstance(key, str) else key
        return hmac.new(secret, self.canonical_bytes(), hashlib.sha256).hexdigest()
