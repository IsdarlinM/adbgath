from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.parse
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adbgath import __version__

from ..errors import AdbgathError, ValidationError
from .files import sha256_file
from .updater import SecureUpdater

COMMIT_API = "https://api.github.com/repos/IsdarlinM/adbgath/commits/main"
RAW_PYPROJECT = "https://raw.githubusercontent.com/IsdarlinM/adbgath/{commit}/pyproject.toml"
ARCHIVE_URL = "https://github.com/IsdarlinM/adbgath/archive/{commit}.zip"
_ALLOWED_DOWNLOAD_HOSTS = {"github.com", "codeload.github.com", "raw.githubusercontent.com", "api.github.com"}
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp, path)


class ManagedSelfUpdater:
    """Update an installed ADB-Gath venv without replacing its runtime/tool directories."""

    def __init__(self, install_root: Path) -> None:
        self.install_root = install_root.expanduser().resolve()
        self.state_file = self.install_root / "config" / "update-state.json"
        self.backup_root = self.install_root / "update-backup"

    @staticmethod
    def _request(url: str, *, timeout: int = 30):
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_DOWNLOAD_HOSTS:
            raise ValidationError("Updater URL is outside the allowed GitHub HTTPS origins.")
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/vnd.github+json", "User-Agent": f"adbgath/{__version__}"},
        )
        try:
            response = urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - fixed HTTPS GitHub origins
        except Exception as exc:
            raise AdbgathError(f"Unable to contact the ADB-Gath update source: {exc}") from exc
        final = urllib.parse.urlparse(response.geturl())
        if final.scheme != "https" or final.hostname not in _ALLOWED_DOWNLOAD_HOSTS:
            response.close()
            raise ValidationError("Updater redirect left the allowed GitHub HTTPS origins.")
        return response

    def _remote(self) -> dict[str, Any]:
        with self._request(COMMIT_API) as response:
            payload = json.load(response)
        commit = str(payload.get("sha", "")).lower()
        if not _SHA_RE.fullmatch(commit):
            raise ValidationError("GitHub returned an invalid main-branch commit SHA.")

        metadata_url = RAW_PYPROJECT.format(commit=commit)
        with self._request(metadata_url) as response:
            raw = response.read(2 * 1024 * 1024)
        try:
            project = tomllib.loads(raw.decode("utf-8"))["project"]
            version = str(project["version"])
            dependencies = [str(item) for item in project.get("dependencies", [])]
        except (KeyError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            raise ValidationError("Remote pyproject.toml metadata is invalid.") from exc
        return {
            "version": version,
            "commit": commit,
            "archive": ARCHIVE_URL.format(commit=commit),
            "dependencies": dependencies,
            "source": "github-main",
        }

    def _state(self) -> dict[str, Any]:
        if not self.state_file.is_file():
            return {}
        try:
            value = json.loads(self.state_file.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def check(self) -> dict[str, Any]:
        remote = self._remote()
        state = self._state()
        same_commit = state.get("commit") == remote["commit"]
        same_version = __version__ == remote["version"]
        return {
            "current": __version__,
            "latest": remote["version"],
            "current_commit": state.get("commit"),
            "latest_commit": remote["commit"],
            "update_available": not (same_commit and same_version),
            "source": remote["source"],
        }

    @staticmethod
    def _installed_locations() -> tuple[Path, list[Path]]:
        if Path(sys.prefix).resolve() == Path(sys.base_prefix).resolve():
            raise AdbgathError(
                "Automatic self-update requires the managed virtual-environment installation. "
                "For a source checkout, use git pull and rerun the installer."
            )
        spec = importlib.util.find_spec("adbgath")
        if spec is None or not spec.submodule_search_locations:
            raise AdbgathError("Unable to locate the installed adbgath package.")
        package = Path(next(iter(spec.submodule_search_locations))).resolve()
        prefix = Path(sys.prefix).resolve()
        if package != prefix and prefix not in package.parents:
            raise AdbgathError(
                "The active adbgath package is outside the managed virtual environment. "
                "Refusing to overwrite a source checkout or editable installation."
            )
        site = package.parent
        dist_infos = sorted(site.glob("adbgath-*.dist-info"))
        if not dist_infos:
            raise AdbgathError("Unable to locate installed adbgath distribution metadata.")
        return package, dist_infos

    def _download(self, url: str, destination: Path) -> str:
        total = 0
        with self._request(url, timeout=60) as response, destination.open("wb") as handle:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                total += len(block)
                if total > _MAX_DOWNLOAD_BYTES:
                    raise ValidationError("Update archive exceeds the download size limit.")
                handle.write(block)
        return sha256_file(destination)

    @staticmethod
    def _run(command: list[str], *, cwd: Path | None = None, timeout: int = 600) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()[-2000:]
            raise AdbgathError(f"Update command failed ({result.returncode}): {detail}")
        return result

    @staticmethod
    def _entry_points(dist_info: Path) -> str:
        target = dist_info / "entry_points.txt"
        return target.read_text(encoding="utf-8") if target.is_file() else ""

    def _backup(self, package: Path, dist_infos: list[Path]) -> None:
        if self.backup_root.exists():
            shutil.rmtree(self.backup_root)
        self.backup_root.mkdir(parents=True)
        shutil.copytree(package, self.backup_root / package.name)
        for item in dist_infos:
            shutil.copytree(item, self.backup_root / item.name)
        _atomic_json(
            self.backup_root / "manifest.json",
            {
                "kind": "managed-package",
                "version": __version__,
                "package": package.name,
                "dist_infos": [item.name for item in dist_infos],
                "created_at": _now(),
            },
        )

    def _restore_backup(self) -> dict[str, Any]:
        manifest_path = self.backup_root / "manifest.json"
        if not manifest_path.is_file():
            raise AdbgathError("No managed update rollback backup is available.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        package, dist_infos = self._installed_locations()
        site = package.parent
        saved_package = self.backup_root / str(manifest.get("package", "adbgath"))
        if not saved_package.is_dir():
            raise AdbgathError("Managed rollback backup is incomplete.")

        previous = site / ".adbgath-rollback-current"
        if previous.exists():
            shutil.rmtree(previous)
        os.replace(package, previous)
        try:
            shutil.copytree(saved_package, package)
            for item in dist_infos:
                shutil.rmtree(item, ignore_errors=True)
            for name in manifest.get("dist_infos", []):
                saved = self.backup_root / str(name)
                if saved.is_dir():
                    shutil.copytree(saved, site / saved.name)
            version = self._smoke_installed()
            shutil.rmtree(previous, ignore_errors=True)
            return {"ok": True, "restored_version": version, "backup": str(self.backup_root)}
        except Exception:
            shutil.rmtree(package, ignore_errors=True)
            if previous.exists():
                os.replace(previous, package)
            raise

    @staticmethod
    def _smoke_installed() -> str:
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        result = subprocess.run(
            [sys.executable, "-c", "import adbgath; print(adbgath.__version__)"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env=environment,
        )
        if result.returncode != 0 or not result.stdout.strip():
            detail = (result.stderr or result.stdout).strip()[-1000:]
            raise ValidationError(f"Updated installation smoke test failed: {detail}")
        return result.stdout.strip()

    def apply(self, *, force: bool = False) -> dict[str, Any]:
        remote = self._remote()
        state = self._state()
        if not force and state.get("commit") == remote["commit"] and __version__ == remote["version"]:
            return {
                "ok": True,
                "updated": False,
                "reason": "already-current",
                "version": __version__,
                "commit": remote["commit"],
            }

        package, dist_infos = self._installed_locations()
        site = package.parent
        temp_root = Path(tempfile.mkdtemp(prefix="adbgath-update-"))
        archive = temp_root / "source.zip"
        extraction = temp_root / "source"
        wheel_dir = temp_root / "wheel"
        wheel_stage = temp_root / "wheel-stage"
        extraction.mkdir(); wheel_dir.mkdir(); wheel_stage.mkdir()
        previous = site / ".adbgath-update-previous"
        replacement = site / ".adbgath-update-new"
        swapped = False
        try:
            archive_sha256 = self._download(remote["archive"], archive)
            with zipfile.ZipFile(archive) as handle:
                SecureUpdater._validate_archive(handle, extraction)
                handle.extractall(extraction)
            payload = SecureUpdater._payload_root(extraction)
            metadata = tomllib.loads((payload / "pyproject.toml").read_text(encoding="utf-8"))["project"]
            if str(metadata.get("version")) != remote["version"]:
                raise ValidationError("Remote commit metadata changed during update preparation.")

            self._run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "wheel",
                    "--disable-pip-version-check",
                    "--no-deps",
                    "--no-build-isolation",
                    "--wheel-dir",
                    str(wheel_dir),
                    str(payload),
                ],
                cwd=payload,
            )
            wheels = sorted(wheel_dir.glob("adbgath-*.whl"))
            if len(wheels) != 1:
                raise ValidationError("Updater did not produce exactly one ADB-Gath wheel.")
            with zipfile.ZipFile(wheels[0]) as handle:
                SecureUpdater._validate_archive(handle, wheel_stage)
                handle.extractall(wheel_stage)
            staged_package = wheel_stage / "adbgath"
            staged_dist_infos = sorted(wheel_stage.glob("adbgath-*.dist-info"))
            if not staged_package.is_dir() or len(staged_dist_infos) != 1:
                raise ValidationError("Built update wheel is missing package or distribution metadata.")

            current_entries = self._entry_points(dist_infos[0])
            staged_entries = self._entry_points(staged_dist_infos[0])
            if current_entries and staged_entries != current_entries:
                raise ValidationError(
                    "The update changes console entry points. Run the platform installer in repair mode instead."
                )

            installed_requirements = sorted(item.strip() for item in (importlib.metadata.requires("adbgath") or []))
            remote_requirements = sorted(item.strip() for item in remote["dependencies"])
            if remote_requirements != installed_requirements:
                self._run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "--disable-pip-version-check",
                        "--upgrade-strategy",
                        "only-if-needed",
                        *remote_requirements,
                    ],
                    timeout=900,
                )

            self._backup(package, dist_infos)
            shutil.rmtree(replacement, ignore_errors=True)
            shutil.rmtree(previous, ignore_errors=True)
            shutil.copytree(staged_package, replacement)
            os.replace(package, previous)
            os.replace(replacement, package)
            swapped = True

            for item in dist_infos:
                shutil.rmtree(item, ignore_errors=True)
            shutil.copytree(staged_dist_infos[0], site / staged_dist_infos[0].name)

            installed_version = self._smoke_installed()
            if installed_version != remote["version"]:
                raise ValidationError(
                    f"Installed version {installed_version!r} does not match prepared version {remote['version']!r}."
                )
            shutil.rmtree(previous, ignore_errors=True)
            _atomic_json(
                self.state_file,
                {
                    "version": installed_version,
                    "commit": remote["commit"],
                    "archive_sha256": archive_sha256,
                    "updated_at": _now(),
                    "forced": bool(force),
                },
            )
            return {
                "ok": True,
                "updated": True,
                "previous_version": __version__,
                "installed_version": installed_version,
                "commit": remote["commit"],
                "archive_sha256": archive_sha256,
                "backup": str(self.backup_root),
                "workspace_preserved": True,
                "restart_required": True,
                "forced": bool(force),
            }
        except Exception:
            if swapped:
                try:
                    self._restore_backup()
                except Exception:
                    pass
            raise
        finally:
            shutil.rmtree(replacement, ignore_errors=True)
            if previous.exists() and not swapped:
                shutil.rmtree(previous, ignore_errors=True)
            shutil.rmtree(temp_root, ignore_errors=True)

    def rollback(self) -> dict[str, Any]:
        return self._restore_backup()


def patch_self_update(module: Any) -> None:
    cls = module.AdbgathService
    if getattr(cls, "_adbgath_selfupdate_360_patched", False):
        return
    original = cls.update_operation

    def update_operation(self, mode: str = "auto", *, archive=None, checksum=None):
        root = Path(os.environ.get("ADBGATH_HOME", Path(__file__).resolve().parents[3])).expanduser().resolve()
        updater = ManagedSelfUpdater(root)
        if mode == "auto":
            return updater.apply(force=False)
        if mode == "force":
            return updater.apply(force=True)
        if mode == "check":
            return updater.check()
        if mode == "rollback" and (updater.backup_root / "manifest.json").is_file():
            return updater.rollback()
        return original(self, mode, archive=archive, checksum=checksum)

    cls.update_operation = update_operation
    cls._adbgath_selfupdate_360_patched = True
