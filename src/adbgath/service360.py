from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core.artifacts360 import ContentAddressedStore
from .core.policy360 import PolicyEngine
from .core.sbom360 import write_sbom
from .core.governance360 import seal_file, unseal_file
from .core.signing360 import generate_signing_keypair, sign_plugin, verify_plugin
from .errors import ValidationError
from .lab.pki import init_ca, issue_certificate
from .lab.protocol import new_token, token_hash
from cryptography.hazmat.primitives import serialization
import hashlib


def patch_service(module: Any) -> None:
    cls = module.AdbgathService
    if getattr(cls, "_adbgath_360_patched", False):
        return
    original_init = cls.__init__
    original_dispatch = cls.dispatch

    def initialized(self, adb=None, *, workspace=None):
        original_init(self, adb, workspace=workspace)
        self.cas = ContentAddressedStore(Path(self.workspace), self.store)
        self.policy = PolicyEngine(self.store)

    def artifact_store(self, mode: str = "status", **payload: Any):
        if mode == "status":
            objects = self.store.list_artifact_objects(limit=100000)
            refs = self.store.list_artifact_references(limit=100000)
            return {
                "objects": len(objects), "references": len(refs),
                "logical_bytes": sum(int(item["size"]) for item in objects),
                "stored_bytes": sum(int(item["stored_size"]) for item in objects),
                "root": str(self.cas.objects),
            }
        if mode == "import":
            path = payload.get("path")
            if not path: raise ValidationError("artifact import requires path")
            return self.cas.import_file(path, project_id=payload.get("project_id"), compress=payload.get("compress"))
        if mode == "list":
            return {"objects": self.store.list_artifact_objects(), "references": self.store.list_artifact_references(project_id=payload.get("project_id"))}
        if mode == "verify":
            return self.cas.verify(payload.get("digest") or None)
        if mode == "materialize":
            if not payload.get("digest") or not payload.get("output"): raise ValidationError("artifact materialize requires digest and output")
            return {"path": str(self.cas.materialize(str(payload["digest"]), str(payload["output"])))}
        if mode == "migrate":
            paths = payload.get("paths") or ([payload.get("path")] if payload.get("path") else [self.workspace / "artifacts", self.workspace / "projects"])
            return self.cas.migrate_legacy(paths, dry_run=bool(payload.get("dry_run", False)))
        if mode == "gc":
            return self.cas.gc(dry_run=bool(payload.get("dry_run", True)))
        raise ValidationError(f"Unsupported artifact-store mode: {mode}")

    def correlate(self, serial: str | None, package: str, *, apk: str | None = None):
        if not package: raise ValidationError("package is required")
        serial = self._serial(serial)
        app = self.app_summary(serial, package)
        runtime = self.runtime(serial, "summary", package)
        static = self.static_analyze(apk) if apk else None
        evidence = []
        confidence = 0.45
        if app: evidence.append({"source": "device-app-summary", "data": app}); confidence += 0.15
        if runtime: evidence.append({"source": "runtime", "data": runtime}); confidence += 0.15
        if static: evidence.append({"source": "static-apk", "data": static}); confidence += 0.2
        correlations = []
        if static and isinstance(static, dict):
            findings = static.get("findings") or []
            for finding in findings:
                correlations.append({"title": finding.get("title") or finding.get("id") or "Static finding", "static": finding, "runtime_observed": bool(runtime), "confidence": round(min(0.99, confidence), 2)})
        return {"package": package, "device": serial, "confidence": round(min(0.99, confidence), 2), "evidence": evidence, "correlations": correlations}

    def policy_operation(self, mode: str, *, role: str = "viewer", action: str = "", effect: str = "allow", approved: bool = False):
        mode = str(mode)
        if mode == "show":
            return {"roles": {r: self.policy.effective_patterns(r) for r in ("viewer","analyst","operator","administrator")}, "overrides": self.store.list_policy_rules()}
        if mode == "check":
            return self.policy.decide(role, action, approved=approved).to_dict()
        if mode in {"set", "delete"}:
            if not approved:
                raise ValidationError("Policy changes require approved=true")
            if role != "administrator" and mode == "set" and action == "*":
                raise ValidationError("Wildcard policy changes are restricted to administrator")
            result = self.store.set_policy_rule(role, action, effect) if mode == "set" else {"deleted": self.store.delete_policy_rule(role, action)}
            self.store.append_audit_event(actor="local-operator", role="administrator", action=f"policy.{mode}", target=f"{role}:{action}", decision="allow", details={"effect": effect})
            return result
        raise ValidationError(f"Unsupported policy mode: {mode}")

    def audit_operation(self, mode: str = "list", *, limit: int = 200):
        if mode == "list": return self.store.list_audit_events(limit)
        if mode == "verify": return self.store.verify_audit_chain()
        raise ValidationError(f"Unsupported audit mode: {mode}")

    def lab_status(self):
        return {"agents": self.store.list_lab_agents(), "pools": self.store.list_lab_pools(), "jobs": self.store.list_lab_jobs(200), "audit": self.store.verify_audit_chain()}

    def lab_pki_init(self, directory: str):
        return init_ca(directory)

    def lab_controller_certificate(self, directory: str, *, name: str = "adbgath-controller", hosts: list[str] | None = None):
        return issue_certificate(directory, name=name, client=False, hosts=hosts or ["127.0.0.1", "localhost"])

    def lab_agent_enroll(self, name: str, *, pki_dir: str, controller: str):
        cert = issue_certificate(pki_dir, name=name, client=True)
        token = new_token()
        agent = self.store.create_lab_agent(name=name, token_hash=token_hash(token), certificate_fingerprint=cert["fingerprint_sha256"], endpoint=controller)
        config_path = Path(pki_dir).expanduser().resolve() / f"agent-{name}.json"
        config = {"agent_id": agent["id"], "name": name, "controller": controller, "token": token, "cert": cert["cert"], "key": cert["key"], "ca": cert["ca_cert"]}
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        try: config_path.chmod(0o600)
        except OSError: pass
        return {"agent": agent, "config": str(config_path), "token_displayed_once": token}

    def lab_pool_manage(self, mode: str, *, name: str = "", pool: str = "", agent: str = "", device: str = ""):
        if mode == "create": return self.store.create_lab_pool(name)
        if mode == "add": return self.store.add_lab_pool_member(pool, agent, device)
        if mode == "list": return self.store.list_lab_pools()
        raise ValidationError(f"Unsupported pool mode: {mode}")

    def lab_pool_submit(self, *, pool: str, action: str, payload: dict[str, Any], role: str, actor: str, approved: bool):
        pools = [item for item in self.store.list_lab_pools() if item["id"] == pool or item["name"] == pool]
        if not pools:
            raise ValidationError(f"Unknown lab pool: {pool}")
        jobs=[]
        for member in pools[0]["members"]:
            member_payload={**payload, "device": member["device_serial"]}
            jobs.append(lab_job_submit(self, agent=member["agent_id"], action=action, payload=member_payload, role=role, actor=actor, approved=approved))
        return {"pool": pools[0]["name"], "jobs": jobs, "count": len(jobs)}

    def lab_job_submit(self, *, agent: str, action: str, payload: dict[str, Any], role: str, actor: str, approved: bool):
        agent_record = self.store.get_lab_agent(agent)
        decision = self.policy.decide(role, action, remote=True, approved=approved)
        self.store.append_audit_event(actor=actor, role=role, action=action, target=agent_record["id"], decision="allow" if decision.allowed else "deny", details=decision.to_dict())
        if not decision.allowed: raise ValidationError(f"Policy denied lab job: {decision.reason}")
        return self.store.create_lab_job(agent_id=agent_record["id"], action=action, payload=payload, requested_by=actor, requested_role=role, approved=approved)

    def plugin_publisher(self, mode: str, *, name: str = "", public_key: str = ""):
        if mode == "list": return self.store.list_plugin_publishers()
        if mode == "add":
            if not name or not public_key: raise ValidationError("publisher add requires name and public key")
            pem=Path(public_key).expanduser().resolve(strict=True).read_text(encoding="utf-8")
            key=serialization.load_pem_public_key(pem.encode("utf-8"))
            der=key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
            return self.store.add_plugin_publisher(name, pem, hashlib.sha256(der).hexdigest())
        if mode == "revoke": return self.store.revoke_plugin_publisher(name)
        raise ValidationError(f"Unsupported publisher mode: {mode}")

    def plugin_verify_trusted(self, bundle_path: str, plugin_file: str, publisher: str):
        record=self.store.get_plugin_publisher(publisher)
        if record["revoked"]: return {"ok":False,"reason":"publisher is revoked","publisher":publisher}
        temp=self.workspace / "tmp" / f"publisher-{publisher}.pem"; temp.parent.mkdir(parents=True,exist_ok=True); temp.write_text(record["public_key_pem"],encoding="utf-8")
        result=plugin_verify_signed(self,bundle_path,plugin_file,str(temp)); temp.unlink(missing_ok=True); return {**result,"publisher":publisher,"fingerprint":record["fingerprint"]}

    def governance(self, mode: str, **payload: Any):
        if mode == "holds": return self.store.list_evidence_holds()
        if mode == "hold":
            project=str(payload.get("project_id", "")); reason=str(payload.get("reason", "")); actor=str(payload.get("actor", "local-operator"))
            if not project or not reason: raise ValidationError("hold requires project_id and reason")
            result=self.store.set_evidence_hold(project,reason=reason,actor=actor); self.store.append_audit_event(actor=actor,role="administrator",action="evidence.hold",target=project,decision="allow",details={"reason":reason}); return result
        if mode == "release":
            project=str(payload.get("project_id", "")); actor=str(payload.get("actor", "local-operator")); result={"released":self.store.release_evidence_hold(project)}; self.store.append_audit_event(actor=actor,role="administrator",action="evidence.release-hold",target=project,decision="allow"); return result
        passphrase=str(payload.get("passphrase", ""))
        if mode == "seal": return seal_file(str(payload.get("path", "")),str(payload.get("output", "")),passphrase)
        if mode == "unseal": return unseal_file(str(payload.get("path", "")),str(payload.get("output", "")),passphrase)
        raise ValidationError(f"Unsupported governance mode: {mode}")

    def plugin_keygen(self, private_key: str, public_key: str):
        return generate_signing_keypair(private_key, public_key)

    def plugin_sign(self, manifest_path: str, plugin_file: str, private_key: str, output: str):
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        bundle = sign_plugin(manifest, plugin_file, private_key)
        target = Path(output).expanduser().resolve(); target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps(bundle, indent=2)+"\n", encoding="utf-8")
        return {"output": str(target), "bundle": bundle}

    def plugin_verify_signed(self, bundle_path: str, plugin_file: str, public_key: str):
        bundle = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
        return verify_plugin(bundle, plugin_file, public_key)

    def sbom_generate(self, format_name: str, output: str):
        return write_sbom(output, format_name)

    def dispatch(self, action: str, payload: dict[str, Any]):
        if action == "artifact_store": return artifact_store(self, str(payload.get("mode", "status")), **{k:v for k,v in payload.items() if k != "mode"})
        if action == "correlate": return correlate(self, payload.get("device"), str(payload.get("package", "")), apk=payload.get("apk") or None)
        if action == "policy": return policy_operation(self, str(payload.get("mode", "show")), role=str(payload.get("role", "viewer")), action=str(payload.get("action", "")), effect=str(payload.get("effect", "allow")), approved=bool(payload.get("approved", False)))
        if action == "audit": return audit_operation(self, str(payload.get("mode", "list")), limit=int(payload.get("limit", 200)))
        if action == "lab_status": return lab_status(self)
        if action == "lab_agents": return self.store.list_lab_agents()
        if action == "lab_agent_enroll": return lab_agent_enroll(self, str(payload.get("name", "")), pki_dir=str(payload.get("pki_dir", "")), controller=str(payload.get("controller", "")))
        if action == "lab_pool_manage": return lab_pool_manage(self, str(payload.get("mode", "list")), name=str(payload.get("name", "")), pool=str(payload.get("pool", "")), agent=str(payload.get("agent", "")), device=str(payload.get("device", "")))
        if action == "lab_pools": return self.store.list_lab_pools()
        if action == "lab_jobs": return self.store.list_lab_jobs(int(payload.get("limit", 200)))
        if action == "lab_pool_submit":
            raw=payload.get("payload", {}); job_payload=json.loads(raw) if isinstance(raw,str) else dict(raw or {})
            return lab_pool_submit(self,pool=str(payload.get("pool", "")),action=str(payload.get("action", "")),payload=job_payload,role=str(payload.get("role", "operator")),actor=str(payload.get("actor", "local-operator")),approved=bool(payload.get("approved", False)))
        if action == "lab_job_submit":
            raw=payload.get("payload", {}); job_payload=json.loads(raw) if isinstance(raw,str) else dict(raw or {})
            return lab_job_submit(self, agent=str(payload.get("agent", "")), action=str(payload.get("action", "")), payload=job_payload, role=str(payload.get("role", "operator")), actor=str(payload.get("actor", "local-operator")), approved=bool(payload.get("approved", False)))
        if action == "lab_job_cancel": return self.store.cancel_lab_job(str(payload.get("job_id", "")))
        if action == "plugin_publisher": return plugin_publisher(self,str(payload.get("mode", "list")),name=str(payload.get("name", "")),public_key=str(payload.get("public_key", "")))
        if action == "plugin_verify_trusted": return plugin_verify_trusted(self,str(payload.get("bundle", "")),str(payload.get("plugin_file", "")),str(payload.get("publisher", "")))
        if action == "governance": return governance(self,str(payload.get("mode", "holds")),**{k:v for k,v in payload.items() if k!="mode"})
        if action == "plugin_keygen": return plugin_keygen(self, str(payload.get("private_key", "")), str(payload.get("public_key", "")))
        if action == "plugin_sign": return plugin_sign(self, str(payload.get("manifest", "")), str(payload.get("plugin_file", "")), str(payload.get("private_key", "")), str(payload.get("output", "")))
        if action == "plugin_verify": return plugin_verify_signed(self, str(payload.get("bundle", "")), str(payload.get("plugin_file", "")), str(payload.get("public_key", "")))
        if action == "sbom_generate": return sbom_generate(self, str(payload.get("format", "cyclonedx")), str(payload.get("output", "sbom.json")))
        return original_dispatch(self, action, payload)

    cls.__init__=initialized; cls.artifact_store=artifact_store; cls.correlate=correlate; cls.policy_operation=policy_operation; cls.audit_operation=audit_operation
    cls.lab_status=lab_status; cls.lab_pki_init=lab_pki_init; cls.lab_controller_certificate=lab_controller_certificate; cls.lab_agent_enroll=lab_agent_enroll; cls.lab_pool_manage=lab_pool_manage; cls.lab_pool_submit=lab_pool_submit; cls.lab_job_submit=lab_job_submit
    cls.plugin_publisher=plugin_publisher; cls.plugin_verify_trusted=plugin_verify_trusted; cls.governance=governance
    cls.plugin_keygen=plugin_keygen; cls.plugin_sign=plugin_sign; cls.plugin_verify_signed=plugin_verify_signed; cls.sbom_generate=sbom_generate; cls.dispatch=dispatch; cls._adbgath_360_patched=True
