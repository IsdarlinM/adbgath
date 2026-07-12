from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from adbgath import __version__

from ..errors import AdbgathError, ValidationError
from .files import sha256_file

RELEASE_API = "https://api.github.com/repos/IsdarlinM/adbgath/releases/latest"
MAX_ARCHIVE_ENTRIES = 20_000
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
PRESERVED_DIRECTORIES = ("workspace", "projects", "config")


class SecureUpdater:
    def __init__(self, install_root: Path, *, repository_api: str = RELEASE_API) -> None:
        self.install_root = install_root.expanduser().resolve()
        parsed = urllib.parse.urlparse(repository_api)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValidationError("The release API must use an absolute HTTPS URL.")
        self.repository_api = repository_api
        self.backup_root = self.install_root.parent / f"{self.install_root.name}.rollback"

    def check(self) -> dict[str, Any]:
        request = urllib.request.Request(  # noqa: S310 - constructor is restricted to validated HTTPS URLs
            self.repository_api,
            headers={"Accept": "application/vnd.github+json", "User-Agent": f"adbgath/{__version__}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - validated HTTPS URL
                payload = json.load(response)
        except Exception as exc:
            raise AdbgathError(f"Unable to check releases: {exc}") from exc
        tag = str(payload.get("tag_name", "")).lstrip("v")
        assets = [
            {"name": item.get("name"), "url": item.get("browser_download_url"), "size": item.get("size")}
            for item in payload.get("assets", [])
        ]
        return {
            "current": __version__,
            "latest": tag,
            "update_available": bool(tag and tag != __version__),
            "release": payload.get("html_url"),
            "assets": assets,
        }

    def plan(self, archive: str | Path | None = None, checksum: str | None = None) -> dict[str, Any]:
        result = {
            "install_root": str(self.install_root),
            "backup_root": str(self.backup_root),
            "preserved": list(PRESERVED_DIRECTORIES),
            "steps": [
                "verify SHA-256",
                "validate ZIP paths, entry types, and decompressed size",
                "extract to a same-volume staging directory",
                "validate package structure and declared version",
                "copy persistent data into the staged release",
                "create a rollback copy",
                "atomically swap application directories",
                "run an isolated version smoke test",
                "restore automatically if validation fails",
            ],
        }
        if archive:
            path = Path(archive).expanduser().resolve()
            actual = sha256_file(path) if path.is_file() else None
            result.update(
                archive=str(path),
                exists=path.is_file(),
                sha256=actual,
                checksum_matches=(actual.lower() == checksum.lower()) if actual and checksum else None,
            )
        return result

    @staticmethod
    def _validate_archive(archive_handle: zipfile.ZipFile, staging: Path) -> None:
        members = archive_handle.infolist()
        if len(members) > MAX_ARCHIVE_ENTRIES:
            raise ValidationError("The update archive contains too many entries.")
        total_size = 0
        for member in members:
            total_size += member.file_size
            if total_size > MAX_UNCOMPRESSED_BYTES:
                raise ValidationError("The update archive exceeds the decompressed size limit.")
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValidationError("Symbolic links are not permitted in update archives.")
            destination = (staging / member.filename).resolve()
            if destination != staging and staging not in destination.parents:
                raise ValidationError("Unsafe path in update archive.")

    @staticmethod
    def _payload_root(staging: Path) -> Path:
        candidates = [path for path in staging.iterdir() if path.is_dir()]
        payload = candidates[0] if len(candidates) == 1 else staging
        pyproject = payload / "pyproject.toml"
        package = payload / "src" / "adbgath"
        if not pyproject.is_file() or not package.is_dir():
            raise ValidationError("The update archive does not contain a valid adbgath source tree.")
        try:
            metadata = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            version = str(metadata["project"]["version"])
        except (KeyError, OSError, tomllib.TOMLDecodeError) as exc:
            raise ValidationError("The update archive has invalid project metadata.") from exc
        init_file = package / "__init__.py"
        if not init_file.is_file() or version not in init_file.read_text(encoding="utf-8"):
            raise ValidationError("The package version and project metadata are inconsistent.")
        return payload

    @staticmethod
    def _smoke_test(root: Path) -> str:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(root / "src")
        result = subprocess.run(
            [sys.executable, "-c", "import adbgath; print(adbgath.__version__)"],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            detail = (result.stderr or result.stdout).strip()[-500:]
            raise ValidationError(f"Updated package smoke test failed: {detail}")
        return result.stdout.strip()

    def install(self, archive: str | Path, checksum: str) -> dict[str, Any]:
        source = Path(archive).expanduser().resolve()
        if not source.is_file() or source.suffix.lower() != ".zip":
            raise ValidationError("Update installation requires a local ZIP release archive.")
        actual = sha256_file(source)
        if actual.lower() != checksum.strip().lower():
            raise ValidationError("Update checksum verification failed.")

        parent = self.install_root.parent
        parent.mkdir(parents=True, exist_ok=True)
        extraction = Path(tempfile.mkdtemp(prefix=".adbgath-extract-", dir=parent))
        prepared = Path(tempfile.mkdtemp(prefix=".adbgath-release-", dir=parent))
        previous = parent / f".{self.install_root.name}.previous"
        swapped = False
        try:
            with zipfile.ZipFile(source) as archive_handle:
                self._validate_archive(archive_handle, extraction)
                archive_handle.extractall(extraction)
            payload = self._payload_root(extraction)
            shutil.rmtree(prepared)
            shutil.copytree(payload, prepared)

            for name in PRESERVED_DIRECTORIES:
                current = self.install_root / name
                destination = prepared / name
                if current.exists():
                    if destination.exists():
                        shutil.rmtree(destination) if destination.is_dir() else destination.unlink()
                    shutil.copytree(current, destination) if current.is_dir() else shutil.copy2(current, destination)

            candidate_version = self._smoke_test(prepared)
            if self.backup_root.exists():
                shutil.rmtree(self.backup_root)
            if self.install_root.exists():
                shutil.copytree(self.install_root, self.backup_root)
            if previous.exists():
                shutil.rmtree(previous) if previous.is_dir() else previous.unlink()
            if self.install_root.exists():
                os.replace(self.install_root, previous)
            os.replace(prepared, self.install_root)
            swapped = True
            installed_version = self._smoke_test(self.install_root)
            if previous.exists():
                shutil.rmtree(previous)
            return {
                "ok": True,
                "installed_from": str(source),
                "sha256": actual,
                "candidate_version": candidate_version,
                "installed_version": installed_version,
                "rollback": str(self.backup_root),
                "preserved": list(PRESERVED_DIRECTORIES),
            }
        except Exception:
            if swapped and previous.exists():
                if self.install_root.exists():
                    shutil.rmtree(self.install_root)
                os.replace(previous, self.install_root)
            raise
        finally:
            shutil.rmtree(extraction, ignore_errors=True)
            shutil.rmtree(prepared, ignore_errors=True)

    def rollback(self) -> dict[str, Any]:
        if not self.backup_root.is_dir():
            raise AdbgathError("No rollback backup is available.")
        current_backup = self.install_root.parent / f"{self.install_root.name}.failed-update"
        if current_backup.exists():
            shutil.rmtree(current_backup)
        if self.install_root.exists():
            os.replace(self.install_root, current_backup)
        try:
            shutil.copytree(self.backup_root, self.install_root)
            restored_version = self._smoke_test(self.install_root)
        except Exception:
            if self.install_root.exists():
                shutil.rmtree(self.install_root)
            if current_backup.exists():
                os.replace(current_backup, self.install_root)
            raise
        return {
            "ok": True,
            "restored": str(self.install_root),
            "restored_version": restored_version,
            "failed_update_backup": str(current_backup),
        }
