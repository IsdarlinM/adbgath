from __future__ import annotations

import hashlib
import json
from typing import Any

from .migrations import CURRENT_SCHEMA_VERSION, apply_migrations, backup_database, restore_database


def patch_storage(module: Any) -> None:
    cls = module.ProjectStore
    if getattr(cls, "_adbgath_340_patched", False):
        return
    original_init = cls.__init__

    def initialized(self, path) -> None:
        database = module.Path(path).expanduser().resolve() if hasattr(module, "Path") else path
        backup = backup_database(database)
        try:
            original_init(self, path)
            with self.connect() as connection:
                self.applied_migrations = apply_migrations(connection)
                integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
                if integrity.lower() != "ok":
                    raise RuntimeError(f"SQLite integrity validation failed after migration: {integrity}")
        except Exception:
            restore_database(database, backup)
            raise

    def schema_status(self) -> dict[str, Any]:
        with self.connect() as connection:
            user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            migrations = [
                dict(row)
                for row in connection.execute(
                    "SELECT version,name,checksum,applied_at FROM schema_migrations ORDER BY version"
                ).fetchall()
            ]
        return {
            "current_version": CURRENT_SCHEMA_VERSION,
            "database_version": user_version,
            "integrity": integrity,
            "migrations": migrations,
            "applied_on_startup": list(getattr(self, "applied_migrations", [])),
        }

    def save_inventory_state(self, *, device_serial: str, user_id: str | None, name: str, inventory: dict[str, Any]):
        inventory_id = self._id("inv")
        created_at = module.utc_now()
        encoded = json.dumps(inventory, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        stable = {key: value for key, value in inventory.items() if key != "captured_at"}
        stable_encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(stable_encoded.encode("utf-8")).hexdigest()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO inventory_states(id,device_serial,user_id,name,digest,inventory_json,created_at) VALUES(?,?,?,?,?,?,?)",
                (inventory_id, device_serial, user_id, name.strip() or created_at, digest, encoded, created_at),
            )
        return {
            "id": inventory_id,
            "device_serial": device_serial,
            "user_id": user_id,
            "name": name.strip() or created_at,
            "digest": digest,
            "created_at": created_at,
            "inventory": inventory,
        }

    def get_inventory_state(self, identifier: str):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM inventory_states WHERE id=? OR name=? ORDER BY created_at DESC LIMIT 1",
                (identifier, identifier),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown inventory state: {identifier}")
        item = dict(row)
        item["inventory"] = json.loads(item.pop("inventory_json"))
        return item

    def list_inventory_states(self, *, device_serial: str | None = None, limit: int = 100):
        query = "SELECT id,device_serial,user_id,name,digest,created_at FROM inventory_states"
        params: list[Any] = []
        if device_serial:
            query += " WHERE device_serial=?"
            params.append(device_serial)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 1000)))
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(query, tuple(params)).fetchall()]

    def prune_inventory_states(self, *, keep_per_device: int = 100) -> int:
        keep = max(2, min(int(keep_per_device), 10000))
        removed = 0
        with self.connect() as connection:
            serials = [row[0] for row in connection.execute("SELECT DISTINCT device_serial FROM inventory_states")]
            for serial in serials:
                stale = connection.execute(
                    "SELECT id FROM inventory_states WHERE device_serial=? ORDER BY created_at DESC LIMIT -1 OFFSET ?",
                    (serial, keep),
                ).fetchall()
                if stale:
                    connection.executemany("DELETE FROM inventory_states WHERE id=?", [(row[0],) for row in stale])
                    removed += len(stale)
        return removed

    cls.__init__ = initialized
    cls.schema_status = schema_status
    cls.save_inventory_state = save_inventory_state
    cls.get_inventory_state = get_inventory_state
    cls.list_inventory_states = list_inventory_states
    cls.prune_inventory_states = prune_inventory_states
    cls._adbgath_340_patched = True
