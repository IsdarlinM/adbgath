from __future__ import annotations

import time
from typing import Any


def patch_capabilities(module: Any) -> None:
    cls = module.CapabilityDetector
    if getattr(cls, "_adbgath_340_patched", False):
        return
    original_init = cls.__init__
    original_detect = cls.detect

    def initialized(self, adb, *, ttl_seconds: int = 30):
        original_init(self, adb)
        self.ttl_seconds = max(5, int(ttl_seconds))
        self._cache = {}

    def invalidate(self, serial: str | None = None):
        if serial is None:
            self._cache.clear()
        else:
            self._cache.pop(serial, None)

    def detect(self, serial: str, *, refresh: bool = False):
        now = time.monotonic()
        cached = self._cache.get(serial)
        if not refresh and cached and now - cached[0] < self.ttl_seconds:
            return {**cached[1], "cache": {"ttl_seconds": self.ttl_seconds}}
        result = original_detect(self, serial)
        fingerprint = self._shell(serial, ["getprop", "ro.build.fingerprint"])
        result.setdefault("device", {})["build_fingerprint"] = fingerprint
        result.setdefault("features", {})["wireless_qr_pairing"] = {
            "available": bool(result.get("features", {}).get("wireless_pairing", {}).get("available")),
            "requirement": "Android 11+, ADB mDNS, and qrcode",
        }
        result["cache"] = {"ttl_seconds": self.ttl_seconds}
        self._cache[serial] = (now, result)
        return result

    cls.__init__ = initialized
    cls.invalidate = invalidate
    cls.detect = detect
    cls._adbgath_340_patched = True
