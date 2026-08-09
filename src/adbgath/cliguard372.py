from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _json_object(module: Any, raw: str, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise module.AdbgathError(f"{label} must be valid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise module.AdbgathError(f"{label} must be a JSON object.")
    return value


def patch_cli_input_errors(module: Any) -> None:
    """Convert user-controlled Lab JSON/config failures into normal CLI errors."""
    if getattr(module, "_adbgath_372_cli_input_guard_patched", False):
        return

    original_run = module.run

    def run(args):
        if getattr(args, "command", None) == "lab":
            mode = getattr(args, "lab_mode", None)
            if mode in {"job-submit", "pool-submit"}:
                _json_object(module, str(getattr(args, "payload", "{}")), label="--payload")
            elif mode == "agent-run":
                source = Path(str(getattr(args, "config", ""))).expanduser()
                try:
                    raw = source.read_text(encoding="utf-8")
                except OSError as exc:
                    raise module.AdbgathError(f"Unable to read Lab agent config '{source}': {exc}") from exc
                config = _json_object(module, raw, label="Lab agent config")
                required = {"agent_id", "token", "controller", "cert", "key", "ca"}
                missing = sorted(required - set(config))
                if missing:
                    raise module.AdbgathError(
                        "Lab agent config is missing required fields: " + ", ".join(missing)
                    )
        return original_run(args)

    module.run = run
    module._adbgath_372_cli_input_guard_patched = True
