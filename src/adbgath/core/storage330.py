from __future__ import annotations

import json
from typing import Any

from .storage import ProjectStore as LegacyProjectStore
from .storage import utc_now

EXTRA_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS wireless_devices (
    id TEXT PRIMARY KEY,
    identity_key TEXT NOT NULL UNIQUE,
    serial TEXT,
    instance TEXT,
    alias TEXT,
    model TEXT,
    given_name TEXT,
    hostname TEXT,
    last_host TEXT,
    pairing_port INTEGER,
    connect_port INTEGER,
    state TEXT NOT NULL DEFAULT 'discovered',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS adb_metrics (
    id TEXT PRIMARY KEY,
    serial TEXT,
    command TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    returncode INTEGER NOT NULL,
    ok INTEGER NOT NULL,
    stdout_bytes INTEGER NOT NULL DEFAULT 0,
    stderr_bytes INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_adb_metrics_created_at ON adb_metrics(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_wireless_devices_last_seen ON wireless_devices(last_seen DESC);
"""


class ProjectStore(LegacyProjectStore):
    """3.3 storage extension for wireless targets and local ADB metrics."""

    def __init__(self, path):
        super().__init__(path)
        with self.connect() as connection:
            connection.executescript(EXTRA_SCHEMA)

    def upsert_wireless_device(self, item: dict[str, Any]) -> dict[str, Any]:
        now = str(item.get("last_seen") or utc_now())
        identity = str(
            item.get("serial") or item.get("instance") or item.get("hostname") or item.get("endpoint")
            or f"{item.get('host', '')}:{item.get('port', '')}"
        ).strip()
        if not identity:
            raise ValueError("Wireless device identity is required")
        with self.connect() as connection:
            existing = connection.execute("SELECT * FROM wireless_devices WHERE identity_key=?", (identity,)).fetchone()
            record_id = existing["id"] if existing else self._id("wls")
            first_seen = existing["first_seen"] if existing else now
            current_meta = json.loads(existing["metadata_json"] or "{}") if existing else {}
            current_meta.update(item.get("metadata") or {})
            values = {
                "serial": item.get("serial") or (existing["serial"] if existing else None),
                "instance": item.get("instance") or (existing["instance"] if existing else None),
                "alias": item.get("alias") if item.get("alias") is not None else (existing["alias"] if existing else None),
                "model": item.get("model") or (existing["model"] if existing else None),
                "given_name": item.get("given_name") or (existing["given_name"] if existing else None),
                "hostname": item.get("hostname") or (existing["hostname"] if existing else None),
                "last_host": item.get("host") or item.get("last_host") or (existing["last_host"] if existing else None),
                "pairing_port": item.get("pairing_port") or (existing["pairing_port"] if existing else None),
                "connect_port": item.get("connect_port") or (existing["connect_port"] if existing else None),
                "state": item.get("state") or (existing["state"] if existing else "discovered"),
            }
            connection.execute(
                "INSERT OR REPLACE INTO wireless_devices(id,identity_key,serial,instance,alias,model,given_name,"
                "hostname,last_host,pairing_port,connect_port,state,metadata_json,first_seen,last_seen) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record_id, identity, values["serial"], values["instance"], values["alias"], values["model"],
                    values["given_name"], values["hostname"], values["last_host"], values["pairing_port"],
                    values["connect_port"], values["state"], json.dumps(current_meta, ensure_ascii=False), first_seen, now,
                ),
            )
        return self.get_wireless_device(record_id)

    def get_wireless_device(self, identifier: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM wireless_devices WHERE id=? OR identity_key=? OR serial=? OR alias=? ORDER BY last_seen DESC LIMIT 1",
                (identifier, identifier, identifier, identifier),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown wireless device: {identifier}")
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        return item

    def list_wireless_devices(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM wireless_devices ORDER BY last_seen DESC").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            result.append(item)
        return result

    def set_wireless_alias(self, identifier: str, alias: str) -> dict[str, Any]:
        item = self.get_wireless_device(identifier)
        with self.connect() as connection:
            connection.execute("UPDATE wireless_devices SET alias=?,last_seen=? WHERE id=?", (alias, utc_now(), item["id"]))
        return self.get_wireless_device(item["id"])

    def forget_wireless_device(self, identifier: str) -> dict[str, Any]:
        item = self.get_wireless_device(identifier)
        with self.connect() as connection:
            connection.execute("DELETE FROM wireless_devices WHERE id=?", (item["id"],))
        return item

    def save_metric(self, metric: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO adb_metrics(id,serial,command,duration_ms,returncode,ok,stdout_bytes,stderr_bytes,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    self._id("met"), metric.get("serial"), metric.get("command", "unknown"), int(metric.get("duration_ms", 0)),
                    int(metric.get("returncode", 0)), 1 if metric.get("ok") else 0, int(metric.get("stdout_bytes", 0)),
                    int(metric.get("stderr_bytes", 0)), json.dumps(metric.get("metadata") or {}, ensure_ascii=False),
                    metric.get("timestamp") or utc_now(),
                ),
            )

    def list_metrics(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM adb_metrics ORDER BY created_at DESC LIMIT ?", (max(1, min(int(limit), 5000)),)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["ok"] = bool(item["ok"])
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            result.append(item)
        return result

    def metric_summary(self) -> dict[str, Any]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT command,COUNT(*) AS count,AVG(duration_ms) AS avg_ms,MAX(duration_ms) AS max_ms,"
                "SUM(CASE WHEN ok=1 THEN 1 ELSE 0 END) AS successes FROM adb_metrics GROUP BY command ORDER BY count DESC"
            ).fetchall()
        return {"commands": [{
            "command": row["command"], "count": row["count"], "successes": row["successes"],
            "failures": row["count"] - row["successes"], "average_duration_ms": round(row["avg_ms"] or 0, 2),
            "maximum_duration_ms": row["max_ms"] or 0,
        } for row in rows]}

    def clear_metrics(self) -> int:
        with self.connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM adb_metrics").fetchone()[0]
            connection.execute("DELETE FROM adb_metrics")
        return int(count)
