from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    device_serial TEXT,
    package_name TEXT,
    status TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    started_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    rule_id TEXT NOT NULL,
    title TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    finding_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL,
    media_type TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL,
    result_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS snapshots (
    id TEXT PRIMARY KEY,
    project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    device_serial TEXT,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS device_groups (
    name TEXT NOT NULL,
    serial TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(name, serial)
);
CREATE TABLE IF NOT EXISTS frida_sessions (
    id TEXT PRIMARY KEY,
    device_serial TEXT NOT NULL,
    package_name TEXT,
    mode TEXT NOT NULL,
    script_name TEXT,
    status TEXT NOT NULL,
    command_json TEXT NOT NULL DEFAULT '[]',
    stdout_path TEXT,
    stderr_path TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    completed_at TEXT
);
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class ProjectStore:
    def __init__(self, database: Path) -> None:
        self.database = database
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = sqlite3.connect(self.database, timeout=30)
            connection.row_factory = sqlite3.Row
            try:
                yield connection
                connection.commit()
            finally:
                connection.close()

    @staticmethod
    def _id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:16]}"

    def create_project(self, name: str, *, description: str = "", scope: str = "") -> dict[str, Any]:
        now = utc_now()
        project_id = self._id("prj")
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO projects(id,name,description,scope,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (project_id, name.strip(), description.strip(), scope.strip(), now, now),
            )
        return self.get_project(project_id)

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        return [dict(row) for row in rows]

    def get_project(self, project_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown project: {project_id}")
        return dict(row)

    def create_session(
        self,
        project_id: str,
        *,
        device_serial: str | None = None,
        package_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.get_project(project_id)
        session_id = self._id("ses")
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO sessions(id,project_id,device_serial,package_name,status,metadata_json,started_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (session_id, project_id, device_serial, package_name, "running", json.dumps(metadata or {}), now),
            )
        return self.get_session(session_id)

    def complete_session(self, session_id: str, *, status: str = "completed") -> dict[str, Any]:
        now = utc_now()
        with self.connect() as connection:
            connection.execute("UPDATE sessions SET status=?, completed_at=? WHERE id=?", (status, now, session_id))
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown session: {session_id}")
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json"))
        return item

    def list_sessions(self, project_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM sessions"
        params: tuple[Any, ...] = ()
        if project_id:
            query += " WHERE project_id=?"
            params = (project_id,)
        query += " ORDER BY started_at DESC"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json"))
            result.append(item)
        return result

    def save_finding(
        self,
        finding: dict[str, Any],
        *,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        finding_id = finding.get("id") or self._id("fnd")
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO findings(id,project_id,session_id,rule_id,title,severity,confidence,status,"
                "finding_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    finding_id,
                    project_id,
                    session_id,
                    finding.get("rule_id", finding_id),
                    finding.get("title", "Untitled finding"),
                    finding.get("severity", "info"),
                    finding.get("confidence", "medium"),
                    finding.get("status", "open"),
                    json.dumps(finding, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return {**finding, "id": finding_id}

    def list_findings(self, project_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT finding_json,id,status FROM findings"
        params: tuple[Any, ...] = ()
        if project_id:
            query += " WHERE project_id=?"
            params = (project_id,)
        query += " ORDER BY created_at DESC"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        result = []
        for row in rows:
            item = json.loads(row["finding_json"])
            item["id"] = row["id"]
            item["status"] = row["status"]
            result.append(item)
        return result

    def update_finding_status(self, finding_id: str, status: str) -> None:
        if status not in {"open", "validated", "false-positive", "accepted", "fixed"}:
            raise ValueError("Unsupported finding status")
        with self.connect() as connection:
            connection.execute("UPDATE findings SET status=?, updated_at=? WHERE id=?", (status, utc_now(), finding_id))

    def save_artifact(
        self,
        *,
        path: str,
        sha256: str,
        size: int,
        media_type: str,
        project_id: str | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        artifact_id = self._id("art")
        created_at = utc_now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO artifacts(id,project_id,session_id,path,sha256,size,media_type,metadata_json,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    artifact_id,
                    project_id,
                    session_id,
                    path,
                    sha256,
                    int(size),
                    media_type,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    created_at,
                ),
            )
        return {
            "id": artifact_id,
            "project_id": project_id,
            "session_id": session_id,
            "path": path,
            "sha256": sha256,
            "size": int(size),
            "media_type": media_type,
            "metadata": metadata or {},
            "created_at": created_at,
        }

    def list_artifacts(self, project_id: str | None = None, session_id: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if project_id:
            clauses.append("project_id=?")
            params.append(project_id)
        if session_id:
            clauses.append("session_id=?")
            params.append(session_id)
        query = "SELECT * FROM artifacts"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC"
        with self.connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json"))
            result.append(item)
        return result

    def save_snapshot(
        self,
        name: str,
        data: dict[str, Any],
        *,
        project_id: str | None = None,
        device_serial: str | None = None,
    ) -> dict[str, Any]:
        snapshot_id = self._id("snp")
        created_at = utc_now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO snapshots(id,project_id,name,device_serial,snapshot_json,created_at) VALUES(?,?,?,?,?,?)",
                (snapshot_id, project_id, name, device_serial, json.dumps(data, ensure_ascii=False), created_at),
            )
        return {"id": snapshot_id, "name": name, "device_serial": device_serial, "created_at": created_at, "data": data}

    def get_snapshot(self, identifier: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM snapshots WHERE id=? OR name=? ORDER BY created_at DESC LIMIT 1",
                (identifier, identifier),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown snapshot: {identifier}")
        item = dict(row)
        item["data"] = json.loads(item.pop("snapshot_json"))
        return item

    def list_snapshots(self, project_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT id,project_id,name,device_serial,created_at FROM snapshots"
        params: tuple[Any, ...] = ()
        if project_id:
            query += " WHERE project_id=?"
            params = (project_id,)
        query += " ORDER BY created_at DESC"
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(query, params).fetchall()]

    def save_job(self, job: dict[str, Any]) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO jobs(id,action,status,progress,payload_json,result_json,error,created_at,"
                "updated_at,started_at,completed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    job["id"],
                    job["action"],
                    job["status"],
                    job.get("progress", 0),
                    json.dumps(job.get("payload", {}), ensure_ascii=False),
                    json.dumps(job.get("result"), ensure_ascii=False) if job.get("result") is not None else None,
                    job.get("error"),
                    job.get("created_at", now),
                    now,
                    job.get("started_at"),
                    job.get("completed_at"),
                ),
            )

    def list_jobs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._decode_job(dict(row)) for row in rows]

    def get_job(self, job_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown job: {job_id}")
        return self._decode_job(dict(row))

    @staticmethod
    def _decode_job(item: dict[str, Any]) -> dict[str, Any]:
        item["payload"] = json.loads(item.pop("payload_json"))
        raw_result = item.pop("result_json")
        item["result"] = json.loads(raw_result) if raw_result else None
        return item


    def create_frida_session(
        self,
        *,
        device_serial: str,
        package_name: str | None,
        mode: str,
        script_name: str | None,
        command: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session_id = self._id("frd")
        created_at = utc_now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO frida_sessions(id,device_serial,package_name,mode,script_name,status,command_json,"
                "metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    session_id,
                    device_serial,
                    package_name,
                    mode,
                    script_name,
                    "running",
                    json.dumps(command, ensure_ascii=False),
                    json.dumps(metadata or {}, ensure_ascii=False),
                    created_at,
                ),
            )
        return self.get_frida_session(session_id)

    def complete_frida_session(
        self,
        session_id: str,
        *,
        status: str,
        stdout_path: str | None = None,
        stderr_path: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if status not in {"completed", "failed", "cancelled", "timeout"}:
            raise ValueError("Unsupported Frida session status")
        with self.connect() as connection:
            current = connection.execute(
                "SELECT metadata_json FROM frida_sessions WHERE id=?", (session_id,)
            ).fetchone()
            if current is None:
                raise KeyError(f"Unknown Frida session: {session_id}")
            merged = json.loads(current["metadata_json"] or "{}")
            merged.update(metadata or {})
            connection.execute(
                "UPDATE frida_sessions SET status=?,stdout_path=?,stderr_path=?,metadata_json=?,completed_at=? "
                "WHERE id=?",
                (
                    status,
                    stdout_path,
                    stderr_path,
                    json.dumps(merged, ensure_ascii=False),
                    utc_now(),
                    session_id,
                ),
            )
        return self.get_frida_session(session_id)

    def get_frida_session(self, session_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM frida_sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown Frida session: {session_id}")
        return self._decode_frida_session(dict(row))

    def list_frida_sessions(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM frida_sessions ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 1000)),)
            ).fetchall()
        return [self._decode_frida_session(dict(row)) for row in rows]

    @staticmethod
    def _decode_frida_session(item: dict[str, Any]) -> dict[str, Any]:
        item["command"] = json.loads(item.pop("command_json") or "[]")
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        return item

    def add_group_device(self, name: str, serial: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO device_groups(name,serial,created_at) VALUES(?,?,?)",
                (name.strip(), serial.strip(), utc_now()),
            )

    def remove_group_device(self, name: str, serial: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM device_groups WHERE name=? AND serial=?", (name, serial))

    def list_group(self, name: str) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT serial FROM device_groups WHERE name=? ORDER BY serial", (name,)
            ).fetchall()
        return [row["serial"] for row in rows]

    def list_groups(self) -> dict[str, list[str]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT name,serial FROM device_groups ORDER BY name,serial").fetchall()
        result: dict[str, list[str]] = {}
        for row in rows:
            result.setdefault(row["name"], []).append(row["serial"])
        return result
