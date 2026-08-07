from __future__ import annotations

import gzip
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .files import sha256_file


class ContentAddressedStore:
    """Content-addressed evidence store with atomic writes and deduplication."""

    def __init__(self, workspace: Path, store: Any) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.store = store
        self.objects = self.workspace / "objects" / "sha256"
        self.objects.mkdir(parents=True, exist_ok=True)

    def _path(self, digest: str, *, compression: str = "none") -> Path:
        suffix = ".gz" if compression == "gzip" else ""
        return self.objects / digest[:2] / f"{digest}{suffix}"

    @staticmethod
    def _should_compress(path: Path) -> bool:
        return path.suffix.lower() in {".txt", ".log", ".json", ".xml", ".html", ".csv", ".md"} and path.stat().st_size >= 4096

    def import_file(
        self,
        source: str | Path,
        *,
        logical_name: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        compress: bool | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        source_path = Path(source).expanduser().resolve(strict=True)
        if not source_path.is_file():
            raise ValueError("artifact source must be a regular file")
        digest = sha256_file(source_path)
        use_gzip = self._should_compress(source_path) if compress is None else bool(compress)
        compression = "gzip" if use_gzip else "none"
        target = self._path(digest, compression=compression)
        target.parent.mkdir(parents=True, exist_ok=True)
        created = False
        if not target.exists():
            fd, temporary = tempfile.mkstemp(prefix=f".{digest}.", dir=str(target.parent))
            os.close(fd)
            temp_path = Path(temporary)
            try:
                if compression == "gzip":
                    with source_path.open("rb") as src, temp_path.open("wb") as raw_dst:
                        with gzip.GzipFile(fileobj=raw_dst, mode="wb", compresslevel=6, mtime=0) as dst:
                            while chunk := src.read(1024 * 1024):
                                dst.write(chunk)
                else:
                    with source_path.open("rb") as src, temp_path.open("wb") as dst:
                        while chunk := src.read(1024 * 1024):
                            dst.write(chunk)
                        dst.flush()
                        os.fsync(dst.fileno())
                os.replace(temp_path, target)
                created = True
            finally:
                temp_path.unlink(missing_ok=True)
        record = self.store.register_artifact_object(
            digest=digest,
            size=source_path.stat().st_size,
            stored_size=target.stat().st_size,
            compression=compression,
            path=str(target.relative_to(self.workspace)),
        )
        reference = self.store.add_artifact_reference(
            digest=digest,
            logical_name=logical_name or source_path.name,
            project_id=project_id,
            session_id=session_id,
            metadata={"source": str(source_path), **(metadata or {})},
        )
        return {"object": record, "reference": reference, "deduplicated": not created}

    def materialize(self, digest: str, destination: str | Path) -> Path:
        record = self.store.get_artifact_object(digest)
        source = self.workspace / record["path"]
        target = Path(destination).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
        os.close(fd)
        temp_path = Path(temporary)
        try:
            if record["compression"] == "gzip":
                with gzip.open(source, "rb") as src, temp_path.open("wb") as dst:
                    while chunk := src.read(1024 * 1024):
                        dst.write(chunk)
            else:
                with source.open("rb") as src, temp_path.open("wb") as dst:
                    while chunk := src.read(1024 * 1024):
                        dst.write(chunk)
            if sha256_file(temp_path) != digest:
                raise RuntimeError("artifact integrity validation failed during materialization")
            os.replace(temp_path, target)
            return target
        finally:
            temp_path.unlink(missing_ok=True)

    def verify(self, digest: str | None = None) -> dict[str, Any]:
        objects = [self.store.get_artifact_object(digest)] if digest else self.store.list_artifact_objects(limit=100000)
        checked: list[dict[str, Any]] = []
        ok = True
        for record in objects:
            path = self.workspace / record["path"]
            exists = path.is_file()
            valid = exists
            error = None
            if exists:
                if record["compression"] == "none":
                    valid = sha256_file(path) == record["digest"]
                else:
                    hasher = hashlib.sha256()
                    try:
                        with gzip.open(path, "rb") as src:
                            while chunk := src.read(1024 * 1024):
                                hasher.update(chunk)
                        valid = hasher.hexdigest() == record["digest"]
                    except OSError as exc:
                        valid = False
                        error = str(exc)
            ok = ok and valid
            checked.append({"digest": record["digest"], "path": str(path), "exists": exists, "valid": valid, "error": error})
        return {"ok": ok, "checked": len(checked), "objects": checked}

    def gc(self, *, dry_run: bool = True) -> dict[str, Any]:
        candidates = self.store.unreferenced_artifact_objects()
        removed = []
        bytes_freed = 0
        for record in candidates:
            path = self.workspace / record["path"]
            size = path.stat().st_size if path.exists() else 0
            if not dry_run:
                path.unlink(missing_ok=True)
                self.store.delete_artifact_object(record["digest"])
            removed.append(record["digest"])
            bytes_freed += size
        return {"dry_run": dry_run, "objects": removed, "bytes": bytes_freed}

    def migrate_legacy(self, paths: list[str | Path], *, dry_run: bool = False) -> dict[str, Any]:
        imported = []
        skipped = []
        for base in paths:
            root = Path(base).expanduser().resolve()
            if not root.exists():
                continue
            for file in root.rglob("*"):
                if not file.is_file() or self.objects in file.parents:
                    continue
                if dry_run:
                    imported.append({"source": str(file), "digest": sha256_file(file)})
                else:
                    try:
                        imported.append(self.import_file(file))
                    except Exception as exc:
                        skipped.append({"source": str(file), "error": str(exc)})
        return {"dry_run": dry_run, "imported": imported, "skipped": skipped}
