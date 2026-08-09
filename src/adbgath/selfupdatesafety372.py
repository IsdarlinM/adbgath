from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .errors import ValidationError


def _candidate_preflight(stage_root: Path) -> dict[str, Any]:
    """Import and initialize the staged package in a fresh isolated interpreter.

    This runs before the updater backs up or swaps the installed package.  It is
    intentionally stronger than a plain import: it also builds the CLI parser
    and constructs the Web application with an isolated temporary auth/workspace
    root.  A candidate with a broken compatibility patch therefore never
    replaces the currently installed package.
    """
    stage_root = stage_root.resolve()
    if not (stage_root / "adbgath" / "__init__.py").is_file():
        raise ValidationError("Update candidate preflight could not find the staged adbgath package.")

    with tempfile.TemporaryDirectory(prefix="adbgath-candidate-preflight-") as temp:
        temp_root = Path(temp).resolve()
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment["ADBGATH_SERVER_HOME"] = str(temp_root / "server")
        environment["ADBGATH_WORKSPACE"] = str(temp_root / "workspace")
        script = r'''
import json
import sys
from pathlib import Path

stage = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(stage))

import adbgath
from adbgath.cli import build_parser
from adbgath.webapp import create_app

package_file = Path(adbgath.__file__).resolve()
if stage not in package_file.parents:
    raise RuntimeError(f"candidate import escaped staging root: {package_file}")
parser = build_parser()
if parser is None:
    raise RuntimeError("CLI parser construction returned no parser")
app = create_app(workspace=Path(sys.argv[2]) / "workspace")
if app is None:
    raise RuntimeError("Web application construction returned no app")
print(json.dumps({"version": adbgath.__version__, "package": str(package_file), "routes": len(app.routes)}))
'''
        result = subprocess.run(
            [sys.executable, "-I", "-c", script, str(stage_root), str(temp_root)],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
            env=environment,
        )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise ValidationError(
            "Update candidate preflight failed; the installed package was not modified: " + detail
        )
    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise ValidationError("Update candidate preflight returned an invalid result.") from exc
    if not isinstance(payload, dict) or not payload.get("version"):
        raise ValidationError("Update candidate preflight did not report a package version.")
    return payload


def patch_self_update_safety(module: Any) -> None:
    """Add a pre-swap candidate smoke test to the 3.6 managed updater."""
    cls = module.ManagedSelfUpdater
    if getattr(cls, "_adbgath_372_candidate_preflight_patched", False):
        return

    original_entry_points = cls._entry_points
    original_backup = cls._backup

    def entry_points(self, dist_info: Path) -> str:
        path = Path(dist_info).resolve()
        try:
            installed_package, _ = self._installed_locations()
            installed_site = installed_package.parent.resolve()
        except Exception:
            installed_site = None
        stage_root = path.parent.resolve()
        if installed_site is not None and stage_root != installed_site and (stage_root / "adbgath").is_dir():
            self._candidate_stage_372 = stage_root
        return original_entry_points(path)

    def backup_after_preflight(self, package: Path, dist_infos: list[Path]) -> None:
        stage_root = getattr(self, "_candidate_stage_372", None)
        if stage_root is None:
            raise ValidationError("Updater lost the staged package before candidate preflight.")
        result = _candidate_preflight(Path(stage_root))
        self._candidate_preflight_372 = result
        original_backup(self, package, dist_infos)

    cls._entry_points = entry_points
    cls._backup = backup_after_preflight
    cls._adbgath_372_candidate_preflight_patched = True
