from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

BASELINE_VERSION: Final = 330
CURRENT_SCHEMA_VERSION: Final = 340


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
    backup = backup_dir / f"{database.stem}-pre-340-{stamp}.sqlite3"
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
