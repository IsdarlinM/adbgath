from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

SCHEMA_360 = r'''
CREATE TABLE IF NOT EXISTS artifact_objects (
  digest TEXT PRIMARY KEY,
  size INTEGER NOT NULL,
  stored_size INTEGER NOT NULL,
  compression TEXT NOT NULL,
  path TEXT NOT NULL UNIQUE,
  ref_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS artifact_refs (
  id TEXT PRIMARY KEY,
  digest TEXT NOT NULL REFERENCES artifact_objects(digest) ON DELETE CASCADE,
  project_id TEXT,
  session_id TEXT,
  logical_name TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifact_refs_digest ON artifact_refs(digest);
CREATE TABLE IF NOT EXISTS policy_rules (
  id TEXT PRIMARY KEY,
  role TEXT NOT NULL,
  action TEXT NOT NULL,
  effect TEXT NOT NULL CHECK(effect IN ('allow','deny')),
  created_at TEXT NOT NULL,
  UNIQUE(role, action)
);
CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY,
  actor TEXT NOT NULL,
  role TEXT NOT NULL,
  action TEXT NOT NULL,
  target TEXT,
  decision TEXT NOT NULL,
  details_json TEXT NOT NULL DEFAULT '{}',
  prev_hash TEXT,
  event_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_events_created ON audit_events(created_at DESC);
CREATE TABLE IF NOT EXISTS lab_agents (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  token_hash TEXT NOT NULL,
  certificate_fingerprint TEXT,
  endpoint TEXT,
  capabilities_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'enrolled',
  last_seen TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lab_pools (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lab_pool_members (
  pool_id TEXT NOT NULL REFERENCES lab_pools(id) ON DELETE CASCADE,
  agent_id TEXT NOT NULL REFERENCES lab_agents(id) ON DELETE CASCADE,
  device_serial TEXT NOT NULL,
  PRIMARY KEY(pool_id, agent_id, device_serial)
);
CREATE TABLE IF NOT EXISTS lab_jobs (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL REFERENCES lab_agents(id) ON DELETE CASCADE,
  action TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  requested_role TEXT NOT NULL,
  approved INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'queued',
  result_json TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lab_jobs_agent_status ON lab_jobs(agent_id, status, created_at);
CREATE TABLE IF NOT EXISTS plugin_publishers (
  name TEXT PRIMARY KEY,
  public_key_pem TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  revoked INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence_holds (
  project_id TEXT PRIMARY KEY,
  reason TEXT NOT NULL,
  actor TEXT NOT NULL,
  created_at TEXT NOT NULL
);
'''


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _event_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def patch_storage(module: Any) -> None:
    cls = module.ProjectStore
    if getattr(cls, "_adbgath_360_patched", False):
        return
    original_init = cls.__init__
    original_schema_status = getattr(cls, "schema_status", None)

    def initialized(self, path) -> None:
        original_init(self, path)
        with self.connect() as connection:
            connection.executescript(SCHEMA_360)
            if "schema_migrations" in {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
                checksum = hashlib.sha256(SCHEMA_360.encode()).hexdigest()
                connection.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version,name,checksum,applied_at) VALUES(?,?,?,?)",
                    (360, "distributed-lab-and-artifact-governance", checksum, _now()),
                )
                connection.execute("PRAGMA user_version=360")

    def schema_status(self) -> dict[str, Any]:
        base = original_schema_status(self) if original_schema_status else {}
        with self.connect() as connection:
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        return {**base, "current_version": 360, "database_version": version, "integrity": integrity}

    def register_artifact_object(self, *, digest: str, size: int, stored_size: int, compression: str, path: str) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO artifact_objects(digest,size,stored_size,compression,path,ref_count,created_at) VALUES(?,?,?,?,?,0,?)",
                (digest, int(size), int(stored_size), compression, path, _now()),
            )
            row = connection.execute("SELECT * FROM artifact_objects WHERE digest=?", (digest,)).fetchone()
        return dict(row)

    def get_artifact_object(self, digest: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM artifact_objects WHERE digest=?", (digest,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown artifact object: {digest}")
        return dict(row)

    def list_artifact_objects(self, limit: int = 1000) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM artifact_objects ORDER BY created_at DESC LIMIT ?", (max(1, min(int(limit), 100000)),)
            ).fetchall()]

    def add_artifact_reference(self, *, digest: str, logical_name: str, project_id=None, session_id=None, metadata=None) -> dict[str, Any]:
        ref_id = self._id("aref")
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO artifact_refs(id,digest,project_id,session_id,logical_name,metadata_json,created_at) VALUES(?,?,?,?,?,?,?)",
                (ref_id, digest, project_id, session_id, logical_name, json.dumps(metadata or {}, ensure_ascii=False), _now()),
            )
            connection.execute("UPDATE artifact_objects SET ref_count=ref_count+1 WHERE digest=?", (digest,))
            row = connection.execute("SELECT * FROM artifact_refs WHERE id=?", (ref_id,)).fetchone()
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        return item

    def list_artifact_references(self, *, project_id=None, limit: int = 1000) -> list[dict[str, Any]]:
        query = "SELECT * FROM artifact_refs"
        params: list[Any] = []
        if project_id:
            query += " WHERE project_id=?"
            params.append(project_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 100000)))
        with self.connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            result.append(item)
        return result

    def unreferenced_artifact_objects(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM artifact_objects WHERE ref_count<=0").fetchall()]

    def delete_artifact_object(self, digest: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM artifact_objects WHERE digest=? AND ref_count<=0", (digest,))

    def set_policy_rule(self, role: str, action: str, effect: str) -> dict[str, Any]:
        if effect not in {"allow", "deny"}:
            raise ValueError("policy effect must be allow or deny")
        rule_id = self._id("pol")
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO policy_rules(id,role,action,effect,created_at) VALUES(?,?,?,?,?) ON CONFLICT(role,action) DO UPDATE SET effect=excluded.effect,created_at=excluded.created_at",
                (rule_id, role, action, effect, _now()),
            )
            row = connection.execute("SELECT * FROM policy_rules WHERE role=? AND action=?", (role, action)).fetchone()
        return dict(row)

    def delete_policy_rule(self, role: str, action: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM policy_rules WHERE role=? AND action=?", (role, action))
            return cursor.rowcount > 0

    def list_policy_rules(self, *, role: str | None = None, action: str | None = None) -> list[dict[str, Any]]:
        clauses, params = [], []
        if role:
            clauses.append("role=?"); params.append(role)
        if action:
            clauses.append("action=?"); params.append(action)
        query = "SELECT * FROM policy_rules" + ((" WHERE " + " AND ".join(clauses)) if clauses else "") + " ORDER BY role,action"
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(query, tuple(params)).fetchall()]

    def append_audit_event(self, *, actor: str, role: str, action: str, target: str | None, decision: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
        created_at = _now()
        with self.connect() as connection:
            prev = connection.execute("SELECT event_hash FROM audit_events ORDER BY created_at DESC,id DESC LIMIT 1").fetchone()
            prev_hash = prev[0] if prev else None
            payload = {"actor": actor, "role": role, "action": action, "target": target, "decision": decision, "details": details or {}, "created_at": created_at, "prev_hash": prev_hash}
            event_hash = _event_hash(payload)
            event_id = self._id("aud")
            connection.execute(
                "INSERT INTO audit_events(id,actor,role,action,target,decision,details_json,prev_hash,event_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (event_id, actor, role, action, target, decision, json.dumps(details or {}, ensure_ascii=False), prev_hash, event_hash, created_at),
            )
        return {"id": event_id, **payload, "event_hash": event_hash}

    def list_audit_events(self, limit: int = 500) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM audit_events ORDER BY created_at DESC,id DESC LIMIT ?", (max(1, min(int(limit), 10000)),)).fetchall()
        result = []
        for row in rows:
            item = dict(row); item["details"] = json.loads(item.pop("details_json") or "{}"); result.append(item)
        return result

    def verify_audit_chain(self) -> dict[str, Any]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM audit_events ORDER BY created_at,id").fetchall()
        prev_hash = None
        checked = 0
        for row in rows:
            item = dict(row); details = json.loads(item["details_json"] or "{}")
            payload = {"actor": item["actor"], "role": item["role"], "action": item["action"], "target": item["target"], "decision": item["decision"], "details": details, "created_at": item["created_at"], "prev_hash": prev_hash}
            if item["prev_hash"] != prev_hash or _event_hash(payload) != item["event_hash"]:
                return {"ok": False, "checked": checked, "failed_id": item["id"]}
            prev_hash = item["event_hash"]; checked += 1
        return {"ok": True, "checked": checked, "head": prev_hash}

    def create_lab_agent(self, *, name: str, token_hash: str, certificate_fingerprint: str | None = None, endpoint: str | None = None) -> dict[str, Any]:
        agent_id = self._id("agt")
        with self.connect() as connection:
            connection.execute("INSERT INTO lab_agents(id,name,token_hash,certificate_fingerprint,endpoint,created_at) VALUES(?,?,?,?,?,?)", (agent_id, name, token_hash, certificate_fingerprint, endpoint, _now()))
        return self.get_lab_agent(agent_id)

    def get_lab_agent(self, identifier: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM lab_agents WHERE id=? OR name=? LIMIT 1", (identifier, identifier)).fetchone()
        if row is None: raise KeyError(f"Unknown lab agent: {identifier}")
        item = dict(row); item["capabilities"] = json.loads(item.pop("capabilities_json") or "{}"); item.pop("token_hash", None); return item

    def get_lab_agent_secret(self, identifier: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM lab_agents WHERE id=? OR name=? LIMIT 1", (identifier, identifier)).fetchone()
        if row is None: raise KeyError(f"Unknown lab agent: {identifier}")
        return dict(row)

    def list_lab_agents(self) -> list[dict[str, Any]]:
        with self.connect() as connection: rows = connection.execute("SELECT * FROM lab_agents ORDER BY name").fetchall()
        result=[]
        for row in rows:
            item=dict(row); item["capabilities"]=json.loads(item.pop("capabilities_json") or "{}"); item.pop("token_hash",None); result.append(item)
        return result

    def update_lab_agent_heartbeat(self, agent_id: str, *, capabilities: dict[str, Any], endpoint: str | None = None) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute("UPDATE lab_agents SET capabilities_json=?,endpoint=COALESCE(?,endpoint),status='online',last_seen=? WHERE id=?", (json.dumps(capabilities, ensure_ascii=False), endpoint, _now(), agent_id))
        return self.get_lab_agent(agent_id)

    def create_lab_pool(self, name: str) -> dict[str, Any]:
        pool_id=self._id("pool")
        with self.connect() as connection: connection.execute("INSERT INTO lab_pools(id,name,created_at) VALUES(?,?,?)",(pool_id,name,_now()))
        return {"id":pool_id,"name":name}

    def list_lab_pools(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            pools=[dict(r) for r in connection.execute("SELECT * FROM lab_pools ORDER BY name").fetchall()]
            for pool in pools:
                pool["members"]=[dict(r) for r in connection.execute("SELECT agent_id,device_serial FROM lab_pool_members WHERE pool_id=? ORDER BY agent_id,device_serial",(pool["id"],)).fetchall()]
        return pools

    def add_lab_pool_member(self, pool: str, agent: str, device_serial: str) -> dict[str, Any]:
        with self.connect() as connection:
            p=connection.execute("SELECT id FROM lab_pools WHERE id=? OR name=?",(pool,pool)).fetchone(); a=connection.execute("SELECT id FROM lab_agents WHERE id=? OR name=?",(agent,agent)).fetchone()
            if p is None or a is None: raise KeyError("Unknown pool or agent")
            connection.execute("INSERT OR IGNORE INTO lab_pool_members(pool_id,agent_id,device_serial) VALUES(?,?,?)",(p[0],a[0],device_serial))
            return {"pool_id":p[0],"agent_id":a[0],"device_serial":device_serial}

    def create_lab_job(self, *, agent_id: str, action: str, payload: dict[str, Any], requested_by: str, requested_role: str, approved: bool) -> dict[str, Any]:
        job_id=self._id("job"); now=_now()
        with self.connect() as connection:
            connection.execute("INSERT INTO lab_jobs(id,agent_id,action,payload_json,requested_by,requested_role,approved,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(job_id,agent_id,action,json.dumps(payload,ensure_ascii=False),requested_by,requested_role,1 if approved else 0,"queued",now,now))
        return self.get_lab_job(job_id)

    def get_lab_job(self, job_id: str) -> dict[str, Any]:
        with self.connect() as connection: row=connection.execute("SELECT * FROM lab_jobs WHERE id=?",(job_id,)).fetchone()
        if row is None: raise KeyError(f"Unknown lab job: {job_id}")
        item=dict(row); item["payload"]=json.loads(item.pop("payload_json")); item["result"]=json.loads(item.pop("result_json")) if item.get("result_json") else None; item["approved"]=bool(item["approved"]); return item

    def list_lab_jobs(self, limit: int=200) -> list[dict[str, Any]]:
        with self.connect() as connection: rows=connection.execute("SELECT id FROM lab_jobs ORDER BY created_at DESC LIMIT ?",(max(1,min(int(limit),5000)),)).fetchall()
        return [self.get_lab_job(r[0]) for r in rows]

    def claim_next_lab_job(self, agent_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row=connection.execute("SELECT id FROM lab_jobs WHERE agent_id=? AND status='queued' ORDER BY created_at LIMIT 1",(agent_id,)).fetchone()
            if row is None:
                connection.commit(); return None
            connection.execute("UPDATE lab_jobs SET status='running',updated_at=? WHERE id=? AND status='queued'",(_now(),row[0])); connection.commit()
        return self.get_lab_job(row[0])

    def complete_lab_job(self, job_id: str, *, result: dict[str, Any] | None = None, error: str | None = None) -> dict[str, Any]:
        status="failed" if error else "completed"
        with self.connect() as connection: connection.execute("UPDATE lab_jobs SET status=?,result_json=?,error=?,updated_at=? WHERE id=?",(status,json.dumps(result,ensure_ascii=False) if result is not None else None,error,_now(),job_id))
        return self.get_lab_job(job_id)

    def cancel_lab_job(self, job_id: str) -> dict[str, Any]:
        with self.connect() as connection: connection.execute("UPDATE lab_jobs SET status='cancelled',updated_at=? WHERE id=? AND status IN ('queued','running')",(_now(),job_id))
        return self.get_lab_job(job_id)

    def add_plugin_publisher(self, name: str, public_key_pem: str, fingerprint: str) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute("INSERT INTO plugin_publishers(name,public_key_pem,fingerprint,revoked,created_at) VALUES(?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET public_key_pem=excluded.public_key_pem,fingerprint=excluded.fingerprint,revoked=0,created_at=excluded.created_at", (name, public_key_pem, fingerprint, 0, _now()))
            row = connection.execute("SELECT * FROM plugin_publishers WHERE name=?", (name,)).fetchone()
        item=dict(row); item["revoked"]=bool(item["revoked"]); return item

    def get_plugin_publisher(self, name: str) -> dict[str, Any]:
        with self.connect() as connection: row=connection.execute("SELECT * FROM plugin_publishers WHERE name=?",(name,)).fetchone()
        if row is None: raise KeyError(f"Unknown plugin publisher: {name}")
        item=dict(row); item["revoked"]=bool(item["revoked"]); return item

    def list_plugin_publishers(self) -> list[dict[str, Any]]:
        with self.connect() as connection: rows=connection.execute("SELECT * FROM plugin_publishers ORDER BY name").fetchall()
        return [{**dict(r),"revoked":bool(r["revoked"])} for r in rows]

    def revoke_plugin_publisher(self, name: str) -> dict[str, Any]:
        with self.connect() as connection: connection.execute("UPDATE plugin_publishers SET revoked=1 WHERE name=?",(name,))
        return self.get_plugin_publisher(name)

    def set_evidence_hold(self, project_id: str, *, reason: str, actor: str) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute("INSERT INTO evidence_holds(project_id,reason,actor,created_at) VALUES(?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET reason=excluded.reason,actor=excluded.actor,created_at=excluded.created_at",(project_id,reason,actor,_now()))
            row=connection.execute("SELECT * FROM evidence_holds WHERE project_id=?",(project_id,)).fetchone()
        return dict(row)

    def release_evidence_hold(self, project_id: str) -> bool:
        with self.connect() as connection: cursor=connection.execute("DELETE FROM evidence_holds WHERE project_id=?",(project_id,)); return cursor.rowcount>0

    def list_evidence_holds(self) -> list[dict[str, Any]]:
        with self.connect() as connection: return [dict(r) for r in connection.execute("SELECT * FROM evidence_holds ORDER BY created_at DESC").fetchall()]

    cls.__init__=initialized; cls.schema_status=schema_status
    cls.register_artifact_object=register_artifact_object; cls.get_artifact_object=get_artifact_object; cls.list_artifact_objects=list_artifact_objects
    cls.add_artifact_reference=add_artifact_reference; cls.list_artifact_references=list_artifact_references; cls.unreferenced_artifact_objects=unreferenced_artifact_objects; cls.delete_artifact_object=delete_artifact_object
    cls.set_policy_rule=set_policy_rule; cls.delete_policy_rule=delete_policy_rule; cls.list_policy_rules=list_policy_rules
    cls.append_audit_event=append_audit_event; cls.list_audit_events=list_audit_events; cls.verify_audit_chain=verify_audit_chain
    cls.create_lab_agent=create_lab_agent; cls.get_lab_agent=get_lab_agent; cls.get_lab_agent_secret=get_lab_agent_secret; cls.list_lab_agents=list_lab_agents; cls.update_lab_agent_heartbeat=update_lab_agent_heartbeat
    cls.create_lab_pool=create_lab_pool; cls.list_lab_pools=list_lab_pools; cls.add_lab_pool_member=add_lab_pool_member
    cls.create_lab_job=create_lab_job; cls.get_lab_job=get_lab_job; cls.list_lab_jobs=list_lab_jobs; cls.claim_next_lab_job=claim_next_lab_job; cls.complete_lab_job=complete_lab_job; cls.cancel_lab_job=cancel_lab_job
    cls.add_plugin_publisher=add_plugin_publisher; cls.get_plugin_publisher=get_plugin_publisher; cls.list_plugin_publishers=list_plugin_publishers; cls.revoke_plugin_publisher=revoke_plugin_publisher
    cls.set_evidence_hold=set_evidence_hold; cls.release_evidence_hold=release_evidence_hold; cls.list_evidence_holds=list_evidence_holds
    cls._adbgath_360_patched=True
