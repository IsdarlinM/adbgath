from __future__ import annotations

import hashlib
import stat
import zipfile
from pathlib import Path

import pytest

from adbgath.core.updater import SecureUpdater
from adbgath.errors import ValidationError


def make_source(root: Path, version: str, marker: str) -> Path:
    package = root / "src" / "adbgath"
    package.mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        f'''[build-system]\nrequires=["setuptools"]\nbuild-backend="setuptools.build_meta"\n\n[project]\nname="adbgath"\nversion="{version}"\n''',
        encoding="utf-8",
    )
    (package / "__init__.py").write_text(f'__version__ = "{version}"\nMARKER = "{marker}"\n', encoding="utf-8")
    return root


def zip_tree(source: Path, target: Path) -> str:
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in source.rglob("*"):
            if item.is_file():
                archive.write(item, Path(source.name) / item.relative_to(source))
    return hashlib.sha256(target.read_bytes()).hexdigest()


def test_secure_updater_install_preserves_data_and_rollback(tmp_path: Path):
    install_root = make_source(tmp_path / "installed", "3.2.8", "old")
    workspace = install_root / "workspace"
    workspace.mkdir()
    (workspace / "evidence.txt").write_text("preserve-me", encoding="utf-8")
    release_root = make_source(tmp_path / "release", "3.2.9", "new")
    archive = tmp_path / "release.zip"
    checksum = zip_tree(release_root, archive)

    updater = SecureUpdater(install_root)
    result = updater.install(archive, checksum)
    assert result["installed_version"] == "3.2.9"
    assert 'MARKER = "new"' in (install_root / "src" / "adbgath" / "__init__.py").read_text(encoding="utf-8")
    assert (install_root / "workspace" / "evidence.txt").read_text(encoding="utf-8") == "preserve-me"

    rolled_back = updater.rollback()
    assert rolled_back["restored_version"] == "3.2.8"
    assert 'MARKER = "old"' in (install_root / "src" / "adbgath" / "__init__.py").read_text(encoding="utf-8")


def test_secure_updater_rejects_checksum_mismatch(tmp_path: Path):
    install_root = make_source(tmp_path / "installed", "3.2.8", "old")
    release_root = make_source(tmp_path / "release", "3.2.9", "new")
    archive = tmp_path / "release.zip"
    zip_tree(release_root, archive)
    with pytest.raises(ValidationError, match="checksum"):
        SecureUpdater(install_root).install(archive, "0" * 64)


def test_secure_updater_rejects_symlink_entries(tmp_path: Path):
    install_root = make_source(tmp_path / "installed", "3.2.8", "old")
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        info = zipfile.ZipInfo("release/link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zipped.writestr(info, "../../outside")
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(ValidationError, match="Symbolic links"):
        SecureUpdater(install_root).install(archive, checksum)


def test_secure_updater_requires_https_release_api(tmp_path: Path):
    with pytest.raises(ValidationError, match="HTTPS"):
        SecureUpdater(tmp_path / "install", repository_api="http://example.test/releases")


class DummyPlugin:
    name = "controlled-observer"
    version = "1.0.0"
    permissions = ("read_device", "filesystem")

    @staticmethod
    def check_requirements():
        return []

    @staticmethod
    def execute(context):
        return {"serial": context.serial, "package": context.package, "mode": "observation-only"}


def test_plugin_requires_explicit_permissions(service):
    service.plugins = {DummyPlugin.name: DummyPlugin()}
    with pytest.raises(ValidationError, match="explicit permission"):
        service.plugin_operation(
            {
                "mode": "run",
                "name": DummyPlugin.name,
                "device": "emulator-5554",
                "allow_permissions": ["read_device"],
            }
        )
    result = service.plugin_operation(
        {
            "mode": "run",
            "name": DummyPlugin.name,
            "device": "emulator-5554",
            "package": "com.example.app",
            "allow_permissions": ["read_device", "filesystem"],
        }
    )
    assert result["result"] == {
        "serial": "emulator-5554",
        "package": "com.example.app",
        "mode": "observation-only",
    }
