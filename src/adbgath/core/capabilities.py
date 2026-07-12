from __future__ import annotations

import os
import platform
import shutil
from typing import Any

from ..errors import AdbgathError


class CapabilityDetector:
    def __init__(self, adb: Any) -> None:
        self.adb = adb

    def _shell(self, serial: str, args: list[str], *, timeout: int = 10) -> str:
        result = self.adb.run(["shell", *args], serial=serial, timeout=timeout, check=False)
        return result.stdout.strip()

    def detect(self, serial: str) -> dict[str, Any]:
        sdk_raw = self._shell(serial, ["getprop", "ro.build.version.sdk"])
        try:
            sdk = int(sdk_raw)
        except ValueError:
            sdk = 0
        abi = self._shell(serial, ["getprop", "ro.product.cpu.abi"])
        build_type = self._shell(serial, ["getprop", "ro.build.type"])
        selinux = self._shell(serial, ["getenforce"])
        free_space = self._shell(serial, ["df", "-k", "/data"])
        root = self.adb.run(["shell", "su", "-c", "id"], serial=serial, timeout=5, check=False)
        run_as = self.adb.run(["shell", "run-as", "--help"], serial=serial, timeout=5, check=False)
        tcpdump = self.adb.run(
            ["shell", "sh", "-c", "command -v tcpdump || test -x /data/local/tmp/tcpdump"],
            serial=serial,
            timeout=5,
            check=False,
        )
        mdns = self.adb.run(["mdns", "check"], timeout=10, check=False)
        host_tools = {
            name: shutil.which(name)
            for name in ["frida", "frida-ps", "bundletool", "java", "apkanalyzer", "aapt", "aapt2", "apksigner"]
        }
        return {
            "serial": serial,
            "host": {
                "os": os.name,
                "platform": platform.platform(),
                "architecture": platform.machine(),
                "tools": {name: {"available": bool(path), "path": path} for name, path in host_tools.items()},
            },
            "device": {
                "sdk": sdk,
                "abi": abi,
                "build_type": build_type,
                "selinux": selinux,
                "root": root.ok and "uid=0" in root.stdout,
                "run_as": run_as.ok,
                "tcpdump": tcpdump.ok,
                "mdns": mdns.ok,
                "free_space_raw": free_space,
            },
            "features": {
                "logcat_pid": {"available": sdk >= 24, "requirement": "Android API 24+"},
                "screenrecord": {"available": sdk >= 19, "requirement": "Android API 19+"},
                "bugreport": {"available": True, "requirement": "ADB"},
                "wireless_pairing": {"available": sdk >= 30 and mdns.ok, "requirement": "Android 11+ and mDNS"},
                "packet_capture": {"available": root.ok and tcpdump.ok, "requirement": "root + tcpdump"},
                "private_backup": {"available": run_as.ok, "requirement": "debuggable package with run-as"},
                "frida": {"available": bool(host_tools["frida"]), "requirement": "frida-tools"},
                "bundletool": {
                    "available": bool(host_tools["bundletool"]) or bool(host_tools["java"]),
                    "requirement": "bundletool or Java + bundletool.jar",
                },
            },
        }

    @staticmethod
    def require(capabilities: dict[str, Any], feature: str) -> None:
        item = capabilities.get("features", {}).get(feature)
        if not item or not item.get("available"):
            requirement = item.get("requirement", "unsupported capability") if item else "unknown capability"
            raise AdbgathError(f"Feature {feature!r} is unavailable: {requirement}")
