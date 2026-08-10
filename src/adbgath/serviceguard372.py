from __future__ import annotations

import json
from typing import Any

from .errors import ValidationError


def _integer(value: Any, *, label: str, minimum: int = 1, maximum: int = 10000) -> int:
    if isinstance(value, bool):
        raise ValidationError(f"{label} must be an integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValidationError(f"{label} must be an integer.") from exc
    if parsed < minimum:
        raise ValidationError(f"{label} must be at least {minimum}.")
    if parsed > maximum:
        raise ValidationError(f"{label} must be at most {maximum}.")
    return parsed


def _object(value: Any, *, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"{label} must be valid JSON: {exc.msg}.") from exc
        if not isinstance(parsed, dict):
            raise ValidationError(f"{label} must be a JSON object.")
        return parsed
    raise ValidationError(f"{label} must be a JSON object.")


def _input_failure(module: Any, label: str, function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except module.AdbgathError:
        raise
    except FileNotFoundError as exc:
        raise ValidationError(f"{label}: file not found: {exc.filename or exc}") from exc
    except FileExistsError as exc:
        raise ValidationError(f"{label}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{label}: invalid JSON: {exc.msg}.") from exc
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{label}: {exc}") from exc
    except OSError as exc:
        raise module.AdbgathError(f"{label} failed: {exc}") from exc


def patch_service(module: Any) -> None:
    """Harden advanced 3.6/3.7 actions that historically parsed raw values directly."""
    cls = module.AdbgathService
    if getattr(cls, "_adbgath_372_service_exception_guard_patched", False):
        return

    original_dispatch = cls.dispatch
    original_plugin_sign = getattr(cls, "plugin_sign", None)
    original_plugin_verify = getattr(cls, "plugin_verify_signed", None)
    original_plugin_publisher = getattr(cls, "plugin_publisher", None)
    original_plugin_verify_trusted = getattr(cls, "plugin_verify_trusted", None)
    original_lab_pki_init = getattr(cls, "lab_pki_init", None)
    original_lab_controller_certificate = getattr(cls, "lab_controller_certificate", None)
    original_lab_agent_enroll = getattr(cls, "lab_agent_enroll", None)

    def dispatch(self, action: str, payload: dict[str, Any]):
        if not isinstance(payload, dict):
            raise ValidationError("Operation payload must be a JSON object.")
        normalized = dict(payload)
        if action in {"audit", "lab_jobs"}:
            normalized["limit"] = _integer(
                normalized.get("limit", 200),
                label="Result limit",
                minimum=1,
                maximum=10000,
            )
        if action in {"lab_pool_submit", "lab_job_submit"}:
            normalized["payload"] = _object(normalized.get("payload", {}), label="Lab job payload")
        return original_dispatch(self, action, normalized)

    def plugin_sign(self, *args, **kwargs):
        return _input_failure(module, "Plugin signing input", original_plugin_sign.__get__(self, cls), *args, **kwargs)

    def plugin_verify_signed(self, *args, **kwargs):
        return _input_failure(module, "Plugin verification input", original_plugin_verify.__get__(self, cls), *args, **kwargs)

    def plugin_publisher(self, *args, **kwargs):
        return _input_failure(module, "Plugin publisher input", original_plugin_publisher.__get__(self, cls), *args, **kwargs)

    def plugin_verify_trusted(self, *args, **kwargs):
        try:
            return original_plugin_verify_trusted.__get__(self, cls)(*args, **kwargs)
        except KeyError as exc:
            raise ValidationError("Unknown trusted plugin publisher.") from exc
        except module.AdbgathError:
            raise
        except (FileNotFoundError, TypeError, ValueError) as exc:
            raise ValidationError(f"Trusted plugin verification input is invalid: {exc}") from exc
        except OSError as exc:
            raise module.AdbgathError(f"Trusted plugin verification failed: {exc}") from exc

    def lab_pki_init(self, *args, **kwargs):
        return _input_failure(module, "Lab CA initialization", original_lab_pki_init.__get__(self, cls), *args, **kwargs)

    def lab_controller_certificate(self, *args, **kwargs):
        return _input_failure(
            module,
            "Lab controller certificate input",
            original_lab_controller_certificate.__get__(self, cls),
            *args,
            **kwargs,
        )

    def lab_agent_enroll(self, *args, **kwargs):
        return _input_failure(module, "Lab agent enrollment input", original_lab_agent_enroll.__get__(self, cls), *args, **kwargs)

    cls.dispatch = dispatch
    if original_plugin_sign is not None:
        cls.plugin_sign = plugin_sign
    if original_plugin_verify is not None:
        cls.plugin_verify_signed = plugin_verify_signed
    if original_plugin_publisher is not None:
        cls.plugin_publisher = plugin_publisher
    if original_plugin_verify_trusted is not None:
        cls.plugin_verify_trusted = plugin_verify_trusted
    if original_lab_pki_init is not None:
        cls.lab_pki_init = lab_pki_init
    if original_lab_controller_certificate is not None:
        cls.lab_controller_certificate = lab_controller_certificate
    if original_lab_agent_enroll is not None:
        cls.lab_agent_enroll = lab_agent_enroll
    cls._adbgath_372_service_exception_guard_patched = True
