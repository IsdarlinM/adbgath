from __future__ import annotations

import os
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .errors import AdbgathError, ValidationError
from .models import CommandResult
from .modules.wireless import WirelessManager


def patch_service(module: Any) -> None:
    cls = module.AdbgathService
    original_init = cls.__init__
    original_dispatch = cls.dispatch
    original_doctor = cls.doctor

    def initialized(self, adb=None, *, workspace=None) -> None:
        original_init(self, adb, workspace=workspace)
        if hasattr(self.adb, "set_metric_sink"):
            self.adb.set_metric_sink(self.store.save_metric)
        home = Path(os.environ.get("ADBGATH_HOME", Path.home() / ".adbgath")).expanduser().resolve()
        self.wireless = WirelessManager(self.adb, self.store, home=home)
        self._device_detail_cache: dict[str, tuple[float, bool | None]] = {}

    def devices(self, *, fast: bool = False, details: bool = True) -> list[dict[str, Any]]:
        targets = self.adb.devices()
        if fast or not details:
            return [target.to_dict() for target in targets]

        def root_status(serial: str) -> bool | None:
            cached = self._device_detail_cache.get(serial)
            if cached and time.monotonic() - cached[0] < 15:
                return cached[1]
            try:
                result = self.adb.run(["shell", "su", "-c", "id"], serial=serial, timeout=3, check=False)
                value = result.ok and "uid=0" in result.stdout
            except AdbgathError:
                value = None
            self._device_detail_cache[serial] = (time.monotonic(), value)
            return value

        online = [target for target in targets if target.state == "device"]
        if online:
            with ThreadPoolExecutor(max_workers=min(8, len(online)), thread_name_prefix="adbgath-device") as executor:
                futures = {executor.submit(root_status, target.serial): target for target in online}
                for future in as_completed(futures):
                    futures[future].rooted = future.result()
        return [target.to_dict() for target in targets]

    def connect(self, target: str) -> CommandResult:
        return self.wireless.connect(target)

    def disconnect(self, target: str) -> CommandResult:
        return self.wireless.disconnect(target)

    def wireless_discover(self, *, refresh: bool = False, detailed: bool = True) -> dict[str, Any]:
        return self.wireless.discover(refresh=refresh, detailed=detailed)

    def wireless_pair(self, target: str, pairing_code: str) -> CommandResult:
        return self.wireless.pair(target, pairing_code)

    def wireless_status(self, *, discover: bool = True) -> dict[str, Any]:
        return self.wireless.status(discover=discover)

    def wireless_diagnose(self, *, fix: bool = False, persist: bool = False) -> dict[str, Any]:
        return self.wireless.diagnose(fix=fix, persist=persist)

    def wireless_known(self) -> list[dict[str, Any]]:
        return self.wireless.known()

    def wireless_forget(self, identifier: str) -> dict[str, Any]:
        return self.wireless.forget(identifier)

    def wireless_alias(self, identifier: str, alias: str) -> dict[str, Any]:
        return self.wireless.alias(identifier, alias)

    def wireless_auto_connect(self) -> dict[str, Any]:
        return self.wireless.auto_connect()

    def wireless_tcpip(self, serial: str | None, port: int = 5555) -> CommandResult:
        return self.wireless.tcpip(self._explicit_serial(serial), port)

    def wireless_watch(self, *, interval: int = 3, duration: int = 0) -> Iterator[dict[str, Any]]:
        return self.wireless.watch(interval=interval, duration=duration)

    def metrics(self, mode: str = "summary", *, limit: int = 200) -> Any:
        if mode == "summary":
            return self.store.metric_summary()
        if mode == "list":
            return self.store.list_metrics(limit)
        if mode == "clear":
            return {"cleared": self.store.clear_metrics()}
        raise ValidationError(f"Unsupported metrics mode: {mode}")

    def doctor(self, *, fix: bool = False) -> dict[str, Any]:
        result = original_doctor(self, fix=fix)
        try:
            wireless = self.wireless_status(discover=False)
            server = wireless.get("server_status", {})
            result.setdefault("checks", []).extend(
                [
                    {
                        "name": "adb-mdns-enabled",
                        "ok": server.get("mdns_enabled") is True,
                        "value": server.get("mdns_enabled", "unknown"),
                        "optional": True,
                    },
                    {
                        "name": "adb-mdns-backend",
                        "ok": str(server.get("mdns_backend", "")).upper() == "LIBADBMDNS",
                        "value": server.get("mdns_backend", "unknown"),
                        "optional": True,
                    },
                ]
            )
        except AdbgathError as exc:
            result.setdefault("checks", []).append(
                {"name": "adb-mdns", "ok": False, "value": str(exc), "optional": True}
            )
        return result

    def dispatch(self, action: str, payload: dict[str, Any]) -> Any:
        serial = payload.get("device")
        if action == "devices":
            return self.devices(fast=bool(payload.get("fast", False)), details=bool(payload.get("details", True)))
        if action in {"connect", "wireless_connect"}:
            return self.connect(payload.get("target", "")).to_dict()
        if action in {"disconnect", "wireless_disconnect"}:
            return self.disconnect(payload.get("target", "")).to_dict()
        if action == "wireless_status":
            return self.wireless_status(discover=bool(payload.get("discover", True)))
        if action == "wireless_discover":
            return self.wireless_discover(
                refresh=bool(payload.get("refresh", True)), detailed=bool(payload.get("detailed", True))
            )
        if action == "wireless_pair":
            return self.wireless_pair(payload.get("target", ""), payload.get("pairing_code", "")).to_dict()
        if action == "wireless_diagnose":
            return self.wireless_diagnose(
                fix=bool(payload.get("fix", False)), persist=bool(payload.get("persist", False))
            )
        if action == "wireless_auto_connect":
            return self.wireless_auto_connect()
        if action == "wireless_known":
            return self.wireless_known()
        if action == "wireless_forget":
            return self.wireless_forget(str(payload.get("identifier", "")))
        if action == "wireless_alias":
            return self.wireless_alias(str(payload.get("identifier", "")), str(payload.get("alias", "")))
        if action == "wireless_tcpip":
            return self.wireless_tcpip(serial, int(payload.get("port", 5555))).to_dict()
        if action == "metrics":
            return self.metrics(str(payload.get("mode", "summary")), limit=int(payload.get("limit", 200)))
        return original_dispatch(self, action, payload)

    cls.__init__ = initialized
    cls.devices = devices
    cls.connect = connect
    cls.disconnect = disconnect
    cls.wireless_discover = wireless_discover
    cls.wireless_pair = wireless_pair
    cls.wireless_status = wireless_status
    cls.wireless_diagnose = wireless_diagnose
    cls.wireless_known = wireless_known
    cls.wireless_forget = wireless_forget
    cls.wireless_alias = wireless_alias
    cls.wireless_auto_connect = wireless_auto_connect
    cls.wireless_tcpip = wireless_tcpip
    cls.wireless_watch = wireless_watch
    cls.metrics = metrics
    cls.doctor = doctor
    cls.dispatch = dispatch
