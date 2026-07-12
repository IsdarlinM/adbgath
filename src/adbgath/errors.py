from __future__ import annotations


class AdbgathError(RuntimeError):
    """Base exception for expected adbgath failures."""


class DependencyError(AdbgathError):
    """Raised when an external dependency is unavailable."""


class ValidationError(AdbgathError):
    """Raised when user-controlled input is unsafe or invalid."""


class CommandExecutionError(AdbgathError):
    """Raised when an external command returns a failure status."""

    def __init__(self, message: str, *, returncode: int = 1, stderr: str = "") -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr
