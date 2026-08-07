from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ..core.policy360 import PolicyEngine


class LabAgent:
    """Outbound-only lab worker. It never exposes a remote shell or raw command endpoint."""

    def __init__(self, service: Any, *, agent_id: str, token: str, controller: str, cert: str, key: str, ca: str) -> None:
        self.service = service
        self.agent_id = agent_id
        self.token = token
        self.controller = controller.rstrip("/")
        if not self.controller.startswith("https://"):
            raise ValueError("controller URL must use https://")
        self.context = ssl.create_default_context(cafile=str(Path(ca).expanduser()))
        self.context.load_cert_chain(str(Path(cert).expanduser()), str(Path(key).expanduser()))
        self.policy = PolicyEngine(service.store)

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            f"{self.controller}{path}",
            data=data,
            method=method,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, context=self.context, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def heartbeat(self) -> dict[str, Any]:
        try:
            devices = self.service.devices(fast=True, details=False)
        except Exception as exc:
            devices = [{"error": str(exc)}]
        capabilities = {"version": "3.6.0", "devices": devices, "operations": sorted(self.remote_actions())}
        return self._request("POST", f"/api/agent/{self.agent_id}/heartbeat", {"capabilities": capabilities})

    def remote_actions(self) -> set[str]:
        from ..core.operations import OPERATIONS
        deny = {"web", "update", "plugin", "wireless_qr_create", "wireless_broker", "lab_controller", "lab_agent_run"}
        return {name for name in OPERATIONS if name not in deny}

    def execute_job(self, job: dict[str, Any]) -> dict[str, Any]:
        action = str(job.get("action", ""))
        if action not in self.remote_actions():
            return {"error": "operation is not allowlisted for lab agents"}
        decision = self.policy.decide(str(job.get("requested_role", "viewer")), action, remote=True, approved=bool(job.get("approved")))
        if not decision.allowed:
            return {"error": f"policy denied: {decision.reason}"}
        try:
            result = self.service.dispatch(action, dict(job.get("payload") or {}))
            if hasattr(result, "to_dict"):
                result = result.to_dict()
            return {"result": result}
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}

    def cycle(self) -> dict[str, Any]:
        heartbeat = self.heartbeat()
        response = self._request("GET", f"/api/agent/{self.agent_id}/next-job")
        job = response.get("job")
        if not job:
            return {"heartbeat": heartbeat, "job": None}
        outcome = self.execute_job(job)
        completed = self._request("POST", f"/api/agent/{self.agent_id}/job/{job['id']}/result", outcome)
        return {"heartbeat": heartbeat, "job": completed.get("job")}

    def run(self, *, interval: int = 5, once: bool = False) -> None:
        while True:
            try:
                self.cycle()
            except (urllib.error.URLError, TimeoutError, OSError):
                pass
            if once:
                return
            time.sleep(max(1, min(int(interval), 300)))
