from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .core.diffing import diff_values
from .errors import ValidationError
from .modules.wireless import QrPairingCoordinator, WirelessEventBroker


def patch_service(module: Any) -> None:
    cls = module.AdbgathService
    if getattr(cls, "_adbgath_340_patched", False):
        return
    original_init = cls.__init__
    original_dispatch = cls.dispatch

    def initialized(self, adb=None, *, workspace=None):
        original_init(self, adb, workspace=workspace)
        self.wireless_broker = WirelessEventBroker(self.wireless, self.adb)
        self.qr_pairing = QrPairingCoordinator(self.wireless, workspace=self.workspace)

    def wireless_qr_create(self, *, ttl_seconds: int = 120, auto_connect: bool = True):
        return self.qr_pairing.create(ttl_seconds=ttl_seconds, auto_connect=auto_connect)

    def wireless_qr_status(self, session_id: str):
        return self.qr_pairing.get(session_id)

    def wireless_qr_cancel(self, session_id: str):
        return self.qr_pairing.cancel(session_id)

    def wireless_broker_start(self):
        return self.wireless_broker.start()

    def wireless_broker_stop(self):
        return self.wireless_broker.stop()

    def wireless_broker_status(self):
        return self.wireless_broker.snapshot()

    def inventory_capture(self, serial: str | None, *, name: str | None = None, user=None, keep: int = 100):
        serial = self._serial(serial)
        inventory = self.inventory(serial)
        inventory["captured_at"] = datetime.now(UTC).isoformat()
        selected_user = None
        if user is not None and hasattr(self, "resolve_user"):
            selected_user = self.resolve_user(serial, user)
        record = self.store.save_inventory_state(
            device_serial=serial,
            user_id=str(selected_user) if selected_user is not None else None,
            name=name or f"inventory-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}",
            inventory=inventory,
        )
        self.store.prune_inventory_states(keep_per_device=keep)
        return record

    def inventory_list(self, serial: str | None = None, *, limit: int = 100):
        return self.store.list_inventory_states(device_serial=serial, limit=limit)

    def inventory_diff(self, before: str, after: str):
        left = self.store.get_inventory_state(before)
        right = self.store.get_inventory_state(after)
        left_inv = left["inventory"]
        right_inv = right["inventory"]
        left_stable = {k: v for k, v in left_inv.items() if k != "captured_at"}
        right_stable = {k: v for k, v in right_inv.items() if k != "captured_at"}

        def package_map(value):
            return {str(item.get("name")): item for item in value.get("packages", []) if item.get("name")}

        lmap, rmap = package_map(left_inv), package_map(right_inv)
        added = [rmap[name] for name in sorted(rmap.keys() - lmap.keys())]
        removed = [lmap[name] for name in sorted(lmap.keys() - rmap.keys())]
        changed = [
            {"name": name, "before": lmap[name], "after": rmap[name]}
            for name in sorted(lmap.keys() & rmap.keys())
            if lmap[name] != rmap[name]
        ]
        return {
            "before": {k: v for k, v in left.items() if k != "inventory"},
            "after": {k: v for k, v in right.items() if k != "inventory"},
            "packages": {
                "added": added,
                "removed": removed,
                "changed": changed,
                "counts": {"added": len(added), "removed": len(removed), "changed": len(changed)},
            },
            "diff": diff_values(left_stable, right_stable),
        }

    def inventory_watch(self, serial: str | None, *, interval: int = 10, duration: int = 0, user=None):
        serial = self._serial(serial)
        interval = max(2, min(int(interval), 3600))
        duration = max(0, min(int(duration), 86400))
        started = time.monotonic()
        previous = self.inventory_capture(serial, name="watch-baseline", user=user)
        yield {"type": "baseline", "state": {k: v for k, v in previous.items() if k != "inventory"}}
        while not duration or time.monotonic() - started < duration:
            time.sleep(interval)
            current = self.inventory_capture(serial, user=user)
            if current["digest"] != previous["digest"]:
                yield {
                    "type": "change",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "data": self.inventory_diff(previous["id"], current["id"]),
                }
                previous = current

    def dispatch(self, action: str, payload: dict[str, Any]):
        if action == "wireless_qr_create":
            return wireless_qr_create(
                self,
                ttl_seconds=int(payload.get("ttl_seconds", 120)),
                auto_connect=bool(payload.get("auto_connect", True)),
            )
        if action == "wireless_broker":
            mode = str(payload.get("mode", "status"))
            if mode == "start":
                return wireless_broker_start(self)
            if mode == "stop":
                return wireless_broker_stop(self)
            if mode == "status":
                return wireless_broker_status(self)
            raise ValidationError(f"Unsupported wireless broker mode: {mode}")
        if action == "schema_status":
            return self.store.schema_status()
        if action == "inventory":
            mode = str(payload.get("mode", "export"))
            serial = payload.get("device")
            if mode == "export":
                return self.inventory(serial, output=payload.get("output"))
            if mode == "capture":
                return inventory_capture(self, serial, name=payload.get("name"), user=payload.get("user"))
            if mode == "list":
                return inventory_list(self, serial, limit=int(payload.get("limit", 100)))
            if mode == "diff":
                return inventory_diff(self, str(payload.get("before", "")), str(payload.get("after", "")))
            raise ValidationError(f"Unsupported inventory mode: {mode}")
        return original_dispatch(self, action, payload)

    cls.__init__ = initialized
    cls.wireless_qr_create = wireless_qr_create
    cls.wireless_qr_status = wireless_qr_status
    cls.wireless_qr_cancel = wireless_qr_cancel
    cls.wireless_broker_start = wireless_broker_start
    cls.wireless_broker_stop = wireless_broker_stop
    cls.wireless_broker_status = wireless_broker_status
    cls.inventory_capture = inventory_capture
    cls.inventory_list = inventory_list
    cls.inventory_diff = inventory_diff
    cls.inventory_watch = inventory_watch
    cls.dispatch = dispatch
    cls._adbgath_340_patched = True
