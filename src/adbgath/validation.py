from __future__ import annotations

import re
from pathlib import Path

from .errors import ValidationError

SERIAL_RE = re.compile(r"^[A-Za-z0-9._:\-\[\]]{1,160}$")
PACKAGE_RE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")
USER_RE = re.compile(r"^(?:current|owner|primary|\d{1,6})$")
REMOTE_PATH_RE = re.compile(r"^/[A-Za-z0-9_./@+=,:\- ]{1,1024}$")
INTERFACE_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,64}$")
HOST_PORT_RE = re.compile(r"^[A-Za-z0-9.\-\[\]:]{1,255}:\d{1,5}$")
INTEGER_RE = re.compile(r"^\d{1,10}$")


def validate_serial(value: str) -> str:
    if not SERIAL_RE.fullmatch(value):
        raise ValidationError("Invalid ADB device serial.")
    return value


def validate_package(value: str) -> str:
    if not PACKAGE_RE.fullmatch(value):
        raise ValidationError(f"Invalid Android package name: {value!r}")
    return value


def validate_user(value: str | int | None) -> str | None:
    if value is None or value == "":
        return None
    text = str(value)
    if not USER_RE.fullmatch(text):
        raise ValidationError("Android user must be numeric, current, owner, or primary.")
    return text


def validate_remote_path(value: str) -> str:
    if not REMOTE_PATH_RE.fullmatch(value) or ".." in Path(value).parts:
        raise ValidationError(f"Invalid remote path: {value!r}")
    return value


def validate_interface(value: str) -> str:
    if not INTERFACE_RE.fullmatch(value):
        raise ValidationError("Invalid network interface name.")
    return value


def validate_host_port(value: str) -> str:
    if not HOST_PORT_RE.fullmatch(value):
        raise ValidationError("Expected HOST:PORT.")
    try:
        port = int(value.rsplit(":", 1)[1])
    except ValueError as exc:
        raise ValidationError("Invalid port.") from exc
    if not 1 <= port <= 65535:
        raise ValidationError("Port must be between 1 and 65535.")
    return value


def validate_positive_int(value: str | int, *, maximum: int = 86400) -> int:
    text = str(value)
    if not INTEGER_RE.fullmatch(text):
        raise ValidationError("Expected a positive integer.")
    number = int(text)
    if number < 1 or number > maximum:
        raise ValidationError(f"Value must be between 1 and {maximum}.")
    return number


def safe_local_path(value: str | Path, *, must_exist: bool = False) -> Path:
    path = Path(value).expanduser().resolve()
    if must_exist and not path.exists():
        raise ValidationError(f"Local path does not exist: {path}")
    return path


def ensure_within(path: Path, root: Path) -> Path:
    path = path.resolve()
    root = root.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValidationError(f"Path must remain inside workspace: {root}") from exc
    return path
