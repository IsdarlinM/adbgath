"""adbgath package."""

__version__ = "3.6.0"

from .compat360 import apply as _apply_360

_apply_360()
del _apply_360
