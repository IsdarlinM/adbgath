from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from cryptography import x509

import adbgath
from adbgath.cli import build_parser
from adbgath.core.asyncproc import AsyncProcessSupervisor
from adbgath.core.migrations import CURRENT_SCHEMA_VERSION
from adbgath.core.policy360 import PolicyEngine
from adbgath.lab.controller import create_controller_app
from adbgath.lab.protocol import verify_token
from adbgath.webapp import create_app


def test_version_and_schema_are_360(service):
    assert adbgath.__version__ == "3.6.0"
    assert CURRENT_SCHEMA_VERSION == 360
    status = service.store.schema_status()
    assert status["database_version"] == 360
    assert status["integrity"] == "ok"
    assert any(item["version"] == 360 for item in status["migrations"])


def test_360_cli_commands_parse():
    parser = build_parser()
    cases = [
        ["artifact-store", "status"], ["correlate", "com.example.app"], ["policy", "show"],
        ["audit", "verify"], ["sbom", "--output", "sbom.json"], ["plugin", "keygen", "--private-key", "a", "--public-key", "b"],
        ["plugin", "sign", "--manifest", "m.json", "--plugin-file", "p.py", "--private-key", "k", "--output", "s.json"],
        ["plugin", "verify", "--bundle", "s.json", "--plugin-file", "p.py", "--public-key", "k.pub"],
        ["lab", "status"], ["lab", "pki-init", "--dir", "pki"], ["lab", "controller-cert", "--dir", "pki"],
        ["lab", "agent-enroll", "lab1", "--pki-dir", "pki", "--controller", "https://127.0.0.1:9443"],
        ["lab", "pool-create", "mobile"], ["lab", "pool-add", "mobile", "lab1", "SERIAL"], ["lab", "jobs"],
        ["lab", "job-submit", "--agent", "lab1", "--action", "devices"], ["lab", "job-cancel", "job_1"],
        ["lab", "controller", "--cert", "c", "--key", "k", "--ca", "ca"], ["lab", "agent-run", "--config", "agent.json", "--once"],
    ]
    for argv in cases:
        assert parser.parse_args(argv)


def test_every_registered_command_has_help_text():
    parser = build_parser()
    import argparse
    root = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    assert len(root.choices) >= 45
    for name, sub in root.choices.items():
        text = sub.format_help()
        assert "usage:" in text.lower(), name
        assert sub.prog in text, name
        for action in sub._actions:
            if isinstance(action, argparse._SubParsersAction):
                for child_name, child in action.choices.items():
                    child_text = child.format_help()
                    assert "usage:" in child_text.lower(), f"{name} {child_name}"


def test_content_addressed_store_deduplicates_and_verifies(service, tmp_path: Path):
    source = tmp_path / "evidence.log"
    source.write_text("same evidence\n" * 1000, encoding="utf-8")
    first = service.artifact_store("import", path=source, compress=True)
    second = service.artifact_store("import", path=source, compress=True)
    assert first["object"]["digest"] == second["object"]["digest"]
    assert second["deduplicated"] is True
    status = service.artifact_store("status")
    assert status["objects"] == 1
    assert status["references"] == 2
    assert service.artifact_store("verify")["ok"] is True
    out = tmp_path / "materialized.log"
    service.artifact_store("materialize", digest=first["object"]["digest"], output=out)
    assert out.read_bytes() == source.read_bytes()


def test_artifact_gc_only_removes_unreferenced(service, tmp_path: Path):
    source = tmp_path / "x.bin"; source.write_bytes(b"abc")
    result = service.artifact_store("import", path=source, compress=False)
    digest = result["object"]["digest"]
    assert service.artifact_store("gc", dry_run=False)["objects"] == []
    with service.store.connect() as con:
        con.execute("DELETE FROM artifact_refs WHERE digest=?", (digest,))
        con.execute("UPDATE artifact_objects SET ref_count=0 WHERE digest=?", (digest,))
    preview = service.artifact_store("gc", dry_run=True)
    assert digest in preview["objects"]
    applied = service.artifact_store("gc", dry_run=False)
    assert digest in applied["objects"]


def test_policy_rbac_and_destructive_approval(service):
    policy = PolicyEngine(service.store)
    assert policy.decide("viewer", "devices").allowed
    assert not policy.decide("viewer", "install", approved=True).allowed
    denied = policy.decide("operator", "install", approved=False)
    assert not denied.allowed and denied.requires_approval
    assert policy.decide("operator", "install", approved=True).allowed
    assert not policy.decide("administrator", "web", remote=True, approved=True).allowed
    service.policy_operation("set", role="viewer", action="security", effect="deny", approved=True)
    assert not service.policy_operation("check", role="viewer", action="security")["allowed"]


def test_audit_chain_is_tamper_evident(service):
    service.store.append_audit_event(actor="a", role="operator", action="devices", target=None, decision="allow")
    service.store.append_audit_event(actor="b", role="operator", action="security", target="SERIAL", decision="allow")
    assert service.audit_operation("verify")["ok"] is True
    with service.store.connect() as con:
        con.execute("UPDATE audit_events SET action='tampered' WHERE actor='a'")
    assert service.audit_operation("verify")["ok"] is False


def test_plugin_ed25519_sign_and_verify(service, tmp_path: Path):
    private = tmp_path / "publisher.key"; public = tmp_path / "publisher.pub"
    service.plugin_keygen(str(private), str(public))
    plugin = tmp_path / "plugin.py"; plugin.write_text("VALUE = 1\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"; manifest.write_text(json.dumps({"name":"demo","version":"1.0.0","permissions":["read_device"]}), encoding="utf-8")
    bundle = tmp_path / "plugin.sig.json"
    service.plugin_sign(str(manifest), str(plugin), str(private), str(bundle))
    assert service.plugin_verify_signed(str(bundle), str(plugin), str(public))["ok"] is True
    plugin.write_text("VALUE = 2\n", encoding="utf-8")
    assert service.plugin_verify_signed(str(bundle), str(plugin), str(public))["ok"] is False


def test_lab_pki_agent_enrollment_pool_and_jobs(service, tmp_path: Path):
    pki = tmp_path / "pki"
    ca = service.lab_pki_init(str(pki))
    assert Path(ca["ca_cert"]).is_file()
    controller = service.lab_controller_certificate(str(pki), hosts=["127.0.0.1"])
    cert = x509.load_pem_x509_certificate(Path(controller["cert"]).read_bytes())
    assert cert.subject.rfc4514_string()
    enrollment = service.lab_agent_enroll("lab-one", pki_dir=str(pki), controller="https://127.0.0.1:9443")
    config = json.loads(Path(enrollment["config"]).read_text(encoding="utf-8"))
    secret = service.store.get_lab_agent_secret(enrollment["agent"]["id"])
    assert verify_token(config["token"], secret["token_hash"])
    pool = service.lab_pool_manage("create", name="phones")
    member = service.lab_pool_manage("add", pool=pool["id"], agent="lab-one", device="SERIAL-1")
    assert member["device_serial"] == "SERIAL-1"
    job = service.lab_job_submit(agent="lab-one", action="devices", payload={}, role="viewer", actor="tester", approved=False)
    assert job["status"] == "queued"
    with pytest.raises(Exception):
        service.lab_job_submit(agent="lab-one", action="install", payload={"files":["x.apk"]}, role="operator", actor="tester", approved=False)


def test_controller_requires_agent_token_and_delivers_job(service, tmp_path: Path):
    pki = tmp_path / "pki"; service.lab_pki_init(pki); enrollment = service.lab_agent_enroll("a1", pki_dir=str(pki), controller="https://127.0.0.1:9443")
    agent_id = enrollment["agent"]["id"]; token = enrollment["token_displayed_once"]
    service.lab_job_submit(agent="a1", action="devices", payload={}, role="viewer", actor="tester", approved=False)
    client = TestClient(create_controller_app(service))
    assert client.get(f"/api/agent/{agent_id}/next-job").status_code == 401
    headers={"Authorization":f"Bearer {token}"}
    heartbeat=client.post(f"/api/agent/{agent_id}/heartbeat",headers=headers,json={"capabilities":{"devices":[]}})
    assert heartbeat.status_code == 200
    fetched=client.get(f"/api/agent/{agent_id}/next-job",headers=headers).json()["job"]
    assert fetched["action"] == "devices"
    done=client.post(f"/api/agent/{agent_id}/job/{fetched['id']}/result",headers=headers,json={"result":{"ok":True}})
    assert done.json()["job"]["status"] == "completed"


def test_async_supervisor_success_timeout_and_output_bound(tmp_path: Path):
    async def run():
        supervisor = AsyncProcessSupervisor(max_concurrency=2, output_limit=1024 * 1024)
        ok = await supervisor.run([sys.executable, "-c", "print('ok')"], timeout=5)
        assert ok.ok and ok.stdout.strip() == "ok"
        timed = await supervisor.run([sys.executable, "-c", "import time; time.sleep(2)"], timeout=0.1)
        assert not timed.ok and timed.returncode == 124 and timed.metadata["timed_out"]
    asyncio.run(run())


def test_sbom_generation(service, tmp_path: Path):
    for fmt in ("cyclonedx", "spdx"):
        out=tmp_path/f"sbom-{fmt}.json"; result=service.sbom_generate(fmt,str(out)); data=json.loads(out.read_text())
        assert result["components"] > 0
        assert data.get("bomFormat") == "CycloneDX" if fmt == "cyclonedx" else data.get("spdxVersion") == "SPDX-2.3"


def test_lab_web_ui_and_api(service):
    client = TestClient(create_app(service=service))
    root = client.get("/")
    assert root.status_code == 200 and "Distributed Lab" in root.text and "3.6.0" in root.text
    page = client.get("/lab"); assert page.status_code == 200 and "mTLS agents" in page.text
    assert client.get("/api/lab/status").status_code == 200
    assert client.get("/api/lab/audit/verify").json()["data"]["ok"] is True
    assert client.get("/api/artifact-store/status").status_code == 200
    assert client.post("/api/lab/policy/check", json={"role":"viewer","action":"devices"}).json()["data"]["allowed"] is True


def test_real_mtls_controller_agent_cycle(service, tmp_path: Path):
    import json as _json
    import socket, ssl, threading, time
    import uvicorn
    from adbgath.lab.agent import LabAgent

    pki = tmp_path / "pki-real"
    service.lab_pki_init(str(pki))
    controller = service.lab_controller_certificate(str(pki), hosts=["127.0.0.1"])
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    enrollment = service.lab_agent_enroll("mtls-agent", pki_dir=str(pki), controller=f"https://127.0.0.1:{port}")
    queued = service.lab_job_submit(agent="mtls-agent", action="devices", payload={}, role="viewer", actor="pytest", approved=False)
    config = uvicorn.Config(
        create_controller_app(service), host="127.0.0.1", port=port, log_level="error", access_log=False,
        ssl_certfile=controller["cert"], ssl_keyfile=controller["key"], ssl_ca_certs=controller["ca_cert"], ssl_cert_reqs=ssl.CERT_REQUIRED,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started
    try:
        cfg = _json.loads(Path(enrollment["config"]).read_text(encoding="utf-8"))
        worker = LabAgent(service, agent_id=cfg["agent_id"], token=cfg["token"], controller=cfg["controller"], cert=cfg["cert"], key=cfg["key"], ca=cfg["ca"])
        result = worker.cycle()
        assert result["job"]["status"] == "completed"
        assert service.store.get_lab_job(queued["id"])["status"] == "completed"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_trusted_plugin_publishers_and_revocation(service, tmp_path: Path):
    private = tmp_path / "publisher.key"; public = tmp_path / "publisher.pub"
    service.plugin_keygen(str(private), str(public))
    trusted = service.plugin_publisher("add", name="trusted-lab", public_key=str(public))
    assert trusted["revoked"] is False
    plugin = tmp_path / "plugin.py"; plugin.write_text("VALUE=1\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"; manifest.write_text(json.dumps({"name":"trusted-demo","version":"1","permissions":["read_device"]}), encoding="utf-8")
    bundle = tmp_path / "sig.json"; service.plugin_sign(str(manifest), str(plugin), str(private), str(bundle))
    assert service.plugin_verify_trusted(str(bundle), str(plugin), "trusted-lab")["ok"] is True
    service.plugin_publisher("revoke", name="trusted-lab")
    rejected = service.plugin_verify_trusted(str(bundle), str(plugin), "trusted-lab")
    assert rejected["ok"] is False and "revoked" in rejected["reason"]


def test_governance_vault_and_legal_hold(service, tmp_path: Path):
    project = service.store.create_project("Sensitive", scope="authorized")
    hold = service.governance("hold", project_id=project["id"], reason="retain evidence", actor="tester")
    assert hold["project_id"] == project["id"]
    assert service.governance("holds")[0]["reason"] == "retain evidence"
    source = tmp_path / "secret.txt"; source.write_text("confidential evidence", encoding="utf-8")
    sealed = tmp_path / "secret.adbgathvault"; restored = tmp_path / "restored.txt"
    result = service.governance("seal", path=str(source), output=str(sealed), passphrase="correct horse battery staple")
    assert result["algorithm"] == "AES-256-GCM"
    service.governance("unseal", path=str(sealed), output=str(restored), passphrase="correct horse battery staple")
    assert restored.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    with pytest.raises(Exception):
        service.governance("unseal", path=str(sealed), output=str(tmp_path / "bad"), passphrase="wrong password here")
    assert service.governance("release", project_id=project["id"], actor="tester")["released"] is True


def test_pool_orchestration_queues_one_job_per_member(service, tmp_path: Path):
    pki = tmp_path / "pki-pool"; service.lab_pki_init(str(pki))
    for name in ("agent-a", "agent-b"):
        service.lab_agent_enroll(name, pki_dir=str(pki), controller="https://127.0.0.1:9443")
    pool = service.lab_pool_manage("create", name="pool-a")
    service.lab_pool_manage("add", pool=pool["id"], agent="agent-a", device="SERIAL-A")
    service.lab_pool_manage("add", pool=pool["id"], agent="agent-b", device="SERIAL-B")
    result = service.lab_pool_submit(pool="pool-a", action="devices", payload={}, role="viewer", actor="tester", approved=False)
    assert result["count"] == 2
    assert {job["payload"]["device"] for job in result["jobs"]} == {"SERIAL-A", "SERIAL-B"}


def test_cli340_service_factory_regression(tmp_path, capsys):
    from adbgath.cli import main

    rc = main(["--no-banner", "--json", "--workspace", str(tmp_path), "schema"])
    assert rc == 0
    output = capsys.readouterr().out
    assert "schema_version" in output or "current_version" in output



def test_cli360_service_factory_regression(tmp_path, capsys):
    from adbgath.cli import main

    rc = main(["--no-banner", "--json", "--workspace", str(tmp_path), "policy", "show"])
    assert rc == 0
    output = capsys.readouterr().out
    assert "roles" in output or "policy" in output



def test_web_entrypoint_serve_no_recursion(tmp_path, monkeypatch):
    import uvicorn
    from adbgath import webapp

    captured = {}
    def fake_run(app, **kwargs):
        captured["app"] = app
        captured["kwargs"] = kwargs

    monkeypatch.setattr(uvicorn, "run", fake_run)
    webapp.serve(host="127.0.0.1", port=8877, open_browser=False, workspace=tmp_path)
    assert captured["app"].title == "adbgath Web"
    assert captured["kwargs"]["port"] == 8877

