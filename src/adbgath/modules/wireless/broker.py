from __future__ import annotations

import json
import threading
import time
from collections import deque
from datetime import UTC, datetime
from typing import Any


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class WirelessEventBroker:
    """Single shared wireless/device event broker for CLI and Web UI.

    One daemon thread performs adaptive reconciliation. This avoids one ADB/mDNS
    subprocess per browser client and provides an ordered event stream with a
    bounded in-memory history.
    """

    def __init__(self, manager: Any, adb: Any, *, interval: float = 2.0, max_events: int = 500) -> None:
        self.manager = manager
        self.adb = adb
        self.interval = max(0.5, float(interval))
        self._events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self._sequence = 0
        self._services: list[dict[str, Any]] = []
        self._devices: list[dict[str, Any]] = []
        self._running = False
        self._started_at: str | None = None
        self._updated_at: str | None = None
        self._last_error: str | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._condition = threading.Condition(threading.RLock())

    @staticmethod
    def _key(item: dict[str, Any], kind: str) -> str:
        if kind == "service":
            return f"{item.get('service')}|{item.get('instance')}|{item.get('endpoint')}"
        return str(item.get("serial", ""))

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        with self._condition:
            self._sequence += 1
            event = {
                "sequence": self._sequence,
                "type": event_type,
                "timestamp": _utc_now(),
                "data": data,
            }
            self._events.append(event)
            self._updated_at = event["timestamp"]
            self._condition.notify_all()

    def _diff_emit(self, old: list[dict[str, Any]], new: list[dict[str, Any]], kind: str) -> None:
        old_map = {self._key(item, kind): item for item in old}
        new_map = {self._key(item, kind): item for item in new}
        for key in sorted(new_map.keys() - old_map.keys()):
            self._emit(f"{kind}.added", new_map[key])
        for key in sorted(old_map.keys() - new_map.keys()):
            self._emit(f"{kind}.removed", old_map[key])
        for key in sorted(new_map.keys() & old_map.keys()):
            if json.dumps(new_map[key], sort_keys=True, default=str) != json.dumps(old_map[key], sort_keys=True, default=str):
                self._emit(f"{kind}.changed", {"before": old_map[key], "after": new_map[key]})

    def start(self) -> dict[str, Any]:
        with self._condition:
            if self._running:
                return self.snapshot()
            self._running = True
            self._started_at = _utc_now()
            self._stop.clear()
            self._ready.clear()
            self._thread = threading.Thread(target=self._run, name="adbgath-wireless-broker", daemon=True)
            self._thread.start()
        self._emit("broker.started", {"interval_seconds": self.interval})
        self._ready.wait(timeout=min(5.0, max(1.0, self.interval * 2)))
        return self.snapshot()

    def stop(self, *, join_timeout: float = 5.0) -> dict[str, Any]:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=join_timeout)
        with self._condition:
            was_running = self._running
            self._running = False
        if was_running:
            self._emit("broker.stopped", {})
        return self.snapshot()

    def _run(self) -> None:
        failures = 0
        first_iteration = True
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                discovery = self.manager.discover(refresh=True, detailed=True)
                services = list(discovery.get("services", []))
                devices = [device.to_dict() for device in self.adb.devices()]
                self._diff_emit(self._services, services, "service")
                self._diff_emit(self._devices, devices, "device")
                if not self._services and services:
                    self._emit("mdns.snapshot", {"services": services})
                if not self._devices and devices:
                    self._emit("device.snapshot", {"devices": devices})
                self._services = services
                self._devices = devices
                self._last_error = None
                failures = 0
            except Exception as exc:  # broker boundary
                failures += 1
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._emit("broker.error", {"error": self._last_error, "consecutive_failures": failures})
            finally:
                if first_iteration:
                    first_iteration = False
                    self._ready.set()
            elapsed = time.monotonic() - started
            backoff = min(15.0, self.interval * (2 ** min(failures, 3))) if failures else self.interval
            self._stop.wait(max(0.1, backoff - elapsed))
        with self._condition:
            self._running = False

    def snapshot(self, *, event_limit: int = 50) -> dict[str, Any]:
        with self._condition:
            return {
                "running": self._running,
                "sequence": self._sequence,
                "started_at": self._started_at,
                "updated_at": self._updated_at,
                "last_error": self._last_error,
                "interval_seconds": self.interval,
                "services": list(self._services),
                "devices": list(self._devices),
                "events": list(self._events)[-max(0, min(event_limit, 500)):],
            }

    def wait(self, *, after_sequence: int, timeout: float = 30.0) -> dict[str, Any]:
        self.start()
        with self._condition:
            if self._sequence <= after_sequence and self._running:
                self._condition.wait(timeout=max(0.0, min(timeout, 60.0)))
            events = [event for event in self._events if event["sequence"] > after_sequence]
            return {
                "running": self._running,
                "sequence": self._sequence,
                "events": events,
                "services": list(self._services),
                "devices": list(self._devices),
                "last_error": self._last_error,
            }
