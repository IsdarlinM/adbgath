from __future__ import annotations

import ssl
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from ..core.policy360 import PolicyEngine
from .protocol import verify_token


class Heartbeat(BaseModel):
    capabilities: dict[str, Any] = Field(default_factory=dict)
    endpoint: str | None = None


class JobResult(BaseModel):
    result: Any | None = None
    error: str | None = None


def create_controller_app(service: Any) -> FastAPI:
    app = FastAPI(title="ADB-Gath Lab Controller", docs_url=None, redoc_url=None)
    policy = PolicyEngine(service.store)

    def authenticate(agent_id: str, authorization: str | None) -> dict[str, Any]:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Agent token required")
        token = authorization[7:].strip()
        try:
            record = service.store.get_lab_agent_secret(agent_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown agent") from exc
        if not verify_token(token, record["token_hash"]):
            raise HTTPException(status_code=403, detail="Invalid agent token")
        return record

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "service": "adbgath-controller"}

    @app.post("/api/agent/{agent_id}/heartbeat")
    async def heartbeat(agent_id: str, body: Heartbeat, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        authenticate(agent_id, authorization)
        updated = service.store.update_lab_agent_heartbeat(agent_id, capabilities=body.capabilities, endpoint=body.endpoint)
        service.store.append_audit_event(actor=agent_id, role="agent", action="agent.heartbeat", target=agent_id, decision="allow", details={"capability_keys": sorted(body.capabilities)})
        return {"ok": True, "agent": updated}

    @app.get("/api/agent/{agent_id}/next-job")
    async def next_job(agent_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        authenticate(agent_id, authorization)
        job = service.store.claim_next_lab_job(agent_id)
        if job is None:
            return {"ok": True, "job": None}
        decision = policy.decide(job["requested_role"], job["action"], remote=True, approved=job["approved"])
        if not decision.allowed:
            service.store.complete_lab_job(job["id"], error=f"policy denied: {decision.reason}")
            service.store.append_audit_event(actor=job["requested_by"], role=job["requested_role"], action=job["action"], target=agent_id, decision="deny", details=decision.to_dict())
            return {"ok": True, "job": None}
        return {"ok": True, "job": job}

    @app.post("/api/agent/{agent_id}/job/{job_id}/result")
    async def job_result(agent_id: str, job_id: str, body: JobResult, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        authenticate(agent_id, authorization)
        job = service.store.get_lab_job(job_id)
        if job["agent_id"] != agent_id:
            raise HTTPException(status_code=403, detail="Job does not belong to this agent")
        completed = service.store.complete_lab_job(job_id, result=body.result, error=body.error)
        service.store.append_audit_event(actor=agent_id, role="agent", action=f"job.{completed['status']}", target=job_id, decision="allow", details={"action": job["action"]})
        return {"ok": True, "job": completed}

    return app


def serve_controller(service: Any, *, host: str, port: int, cert: str, key: str, ca: str) -> None:
    import uvicorn

    for path in (cert, key, ca):
        if not Path(path).expanduser().is_file():
            raise FileNotFoundError(path)
    uvicorn.run(
        create_controller_app(service),
        host=host,
        port=int(port),
        ssl_certfile=str(Path(cert).expanduser()),
        ssl_keyfile=str(Path(key).expanduser()),
        ssl_ca_certs=str(Path(ca).expanduser()),
        ssl_cert_reqs=ssl.CERT_REQUIRED,
        access_log=False,
    )
