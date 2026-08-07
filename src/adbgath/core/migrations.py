from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

BASELINE_VERSION: Final = 330
CURRENT_SCHEMA_VERSION: Final = 360


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        340,
        "inventory states and schema metadata",
        """
        CREATE TABLE IF NOT EXISTS inventory_states (
            id TEXT PRIMARY KEY,
            device_serial TEXT NOT NULL,
            user_id TEXT,
            name TEXT NOT NULL,
            digest TEXT NOT NULL,
            inventory_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_inventory_states_device_created
            ON inventory_states(device_serial, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_inventory_states_digest
            ON inventory_states(digest);
        """,
    ),
    Migration(
        360,
        "distributed lab, policy, audit, and content-addressed artifacts",
        """
        CREATE TABLE IF NOT EXISTS artifact_objects (digest TEXT PRIMARY KEY,size INTEGER NOT NULL,stored_size INTEGER NOT NULL,compression TEXT NOT NULL,path TEXT NOT NULL UNIQUE,ref_count INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS artifact_refs (id TEXT PRIMARY KEY,digest TEXT NOT NULL REFERENCES artifact_objects(digest) ON DELETE CASCADE,project_id TEXT,session_id TEXT,logical_name TEXT NOT NULL,metadata_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_artifact_refs_digest ON artifact_refs(digest);
        CREATE TABLE IF NOT EXISTS policy_rules (id TEXT PRIMARY KEY,role TEXT NOT NULL,action TEXT NOT NULL,effect TEXT NOT NULL CHECK(effect IN ('allow','deny')),created_at TEXT NOT NULL,UNIQUE(role,action));
        CREATE TABLE IF NOT EXISTS audit_events (id TEXT PRIMARY KEY,actor TEXT NOT NULL,role TEXT NOT NULL,action TEXT NOT NULL,target TEXT,decision TEXT NOT NULL,details_json TEXT NOT NULL DEFAULT '{}',prev_hash TEXT,event_hash TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_audit_events_created ON audit_events(created_at DESC);
        CREATE TABLE IF NOT EXISTS lab_agents (id TEXT PRIMARY KEY,name TEXT NOT NULL UNIQUE,token_hash TEXT NOT NULL,certificate_fingerprint TEXT,endpoint TEXT,capabilities_json TEXT NOT NULL DEFAULT '{}',status TEXT NOT NULL DEFAULT 'enrolled',last_seen TEXT,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS lab_pools (id TEXT PRIMARY KEY,name TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS lab_pool_members (pool_id TEXT NOT NULL REFERENCES lab_pools(id) ON DELETE CASCADE,agent_id TEXT NOT NULL REFERENCES lab_agents(id) ON DELETE CASCADE,device_serial TEXT NOT NULL,PRIMARY KEY(pool_id,agent_id,device_serial));
        CREATE TABLE IF NOT EXISTS lab_jobs (id TEXT PRIMARY KEY,agent_id TEXT NOT NULL REFERENCES lab_agents(id) ON DELETE CASCADE,action TEXT NOT NULL,payload_json TEXT NOT NULL,requested_by TEXT NOT NULL,requested_role TEXT NOT NULL,approved INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'queued',result_json TEXT,error TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_lab_jobs_agent_status ON lab_jobs(agent_id,status,created_at);
        CREATE TABLE IF NOT EXISTS plugin_publishers (name TEXT PRIMARY KEY,public_key_pem TEXT NOT NULL,fingerprint TEXT NOT NULL,revoked INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS evidence_holds (project_id TEXT PRIMARY KEY,reason TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL);
        """,
    ),
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def ensure_migration_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


def apply_migrations(connection: sqlite3.Connection) -> list[dict[str, object]]:
    ensure_migration_table(connection)
    existing = {
        int(row[0]): {"name": row[1], "checksum": row[2], "applied_at": row[3]}
        for row in connection.execute(
            "SELECT version,name,checksum,applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()
    }
    applied: list[dict[str, object]] = []
    if not existing:
        connection.execute(
            "INSERT INTO schema_migrations(version,name,checksum,applied_at) VALUES(?,?,?,?)",
            (BASELINE_VERSION, "ADB-Gath 3.3 baseline", "baseline", _now()),
        )
        existing[BASELINE_VERSION] = {
            "name": "ADB-Gath 3.3 baseline",
            "checksum": "baseline",
            "applied_at": _now(),
        }

    for migration in MIGRATIONS:
        current = existing.get(migration.version)
        if current:
            if current["checksum"] != migration.checksum:
                raise RuntimeError(
                    f"Database migration {migration.version} checksum mismatch; refusing unsafe schema drift."
                )
            continue
        with connection:
            connection.executescript(migration.sql)
            connection.execute(
                "INSERT INTO schema_migrations(version,name,checksum,applied_at) VALUES(?,?,?,?)",
                (migration.version, migration.name, migration.checksum, _now()),
            )
            connection.execute(f"PRAGMA user_version={migration.version}")
        applied.append(
            {
                "version": migration.version,
                "name": migration.name,
                "checksum": migration.checksum,
            }
        )
    if not MIGRATIONS:
        connection.execute(f"PRAGMA user_version={BASELINE_VERSION}")
    return applied


def backup_database(database: Path, *, keep: int = 3) -> Path | None:
    if not database.is_file() or database.stat().st_size == 0:
        return None
    backup_dir = database.parent / "database-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = backup_dir / f"{database.stem}-pre-{CURRENT_SCHEMA_VERSION}-{stamp}.sqlite3"
    source = sqlite3.connect(database)
    target = sqlite3.connect(backup)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    backups = sorted(backup_dir.glob(f"{database.stem}-pre-*.sqlite3"), key=lambda item: item.stat().st_mtime, reverse=True)
    for stale in backups[max(1, keep):]:
        stale.unlink(missing_ok=True)
    return backup


def restore_database(database: Path, backup: Path | None) -> None:
    if backup is None or not backup.is_file():
        database.unlink(missing_ok=True)
        return
    source = sqlite3.connect(backup)
    target = sqlite3.connect(database)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
