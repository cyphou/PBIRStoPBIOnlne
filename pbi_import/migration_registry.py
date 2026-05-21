"""
Migration Registry — SQLite-based central registry for migration tracking.

Tracks all migration operations across servers, workspaces, and time periods.
Provides a single source of truth for what was migrated, when, and where.
"""

import json
import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT NOT NULL,
    item_name TEXT NOT NULL,
    item_type TEXT NOT NULL,
    source_server TEXT NOT NULL,
    source_path TEXT NOT NULL,
    target_workspace_id TEXT,
    target_workspace_name TEXT,
    target_item_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    phase TEXT,
    content_hash TEXT,
    started_at TEXT,
    completed_at TEXT,
    error_message TEXT,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_migrations_status ON migrations(status);
CREATE INDEX IF NOT EXISTS idx_migrations_source ON migrations(source_server, source_path);
CREATE INDEX IF NOT EXISTS idx_migrations_target ON migrations(target_workspace_id);

CREATE TABLE IF NOT EXISTS migration_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT UNIQUE NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    servers TEXT,
    total_items INTEGER DEFAULT 0,
    completed_items INTEGER DEFAULT 0,
    failed_items INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running'
);
"""


class MigrationRegistry:
    """SQLite-based central migration registry."""

    def __init__(self, db_path: str = "migration_registry.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(_SCHEMA)

    def register_item(
        self,
        item_id: str,
        item_name: str,
        item_type: str,
        source_server: str,
        source_path: str,
        content_hash: str = "",
    ) -> int:
        """Register an item for migration."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO migrations
                   (item_id, item_name, item_type, source_server, source_path, content_hash, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
                (item_id, item_name, item_type, source_server, source_path, content_hash),
            )
            return cursor.lastrowid or 0

    def update_status(
        self,
        row_id: int,
        status: str,
        target_workspace_id: str | None = None,
        target_item_id: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update migration status for an item."""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with sqlite3.connect(self.db_path) as conn:
            if status == "completed":
                conn.execute(
                    """UPDATE migrations SET status=?, target_workspace_id=?,
                       target_item_id=?, completed_at=? WHERE id=?""",
                    (status, target_workspace_id, target_item_id, now, row_id),
                )
            elif status == "failed":
                conn.execute(
                    """UPDATE migrations SET status=?, error_message=?, completed_at=?
                       WHERE id=?""",
                    (status, error_message, now, row_id),
                )
            else:
                conn.execute(
                    """UPDATE migrations SET status=?, started_at=? WHERE id=?""",
                    (status, now, row_id),
                )

    def start_run(self, run_id: str, servers: list[str]) -> None:
        """Record the start of a migration run."""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO migration_runs (run_id, started_at, servers, status)
                   VALUES (?, ?, ?, 'running')""",
                (run_id, now, json.dumps(servers)),
            )

    def finish_run(self, run_id: str) -> None:
        """Record the completion of a migration run."""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """UPDATE migration_runs SET completed_at=?, status='completed'
                   WHERE run_id=?""",
                (now, run_id),
            )

    def summary(self) -> dict:
        """Get overall migration summary."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            # Item status counts
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM migrations GROUP BY status"
            ).fetchall()
            status_counts = {r["status"]: r["cnt"] for r in rows}

            # Type counts
            rows = conn.execute(
                "SELECT item_type, COUNT(*) as cnt FROM migrations GROUP BY item_type"
            ).fetchall()
            type_counts = {r["item_type"]: r["cnt"] for r in rows}

            # Server counts
            rows = conn.execute(
                "SELECT source_server, COUNT(*) as cnt FROM migrations GROUP BY source_server"
            ).fetchall()
            server_counts = {r["source_server"]: r["cnt"] for r in rows}

            # Run history
            runs = conn.execute(
                "SELECT * FROM migration_runs ORDER BY started_at DESC LIMIT 10"
            ).fetchall()

        return {
            "by_status": status_counts,
            "by_type": type_counts,
            "by_server": server_counts,
            "total_items": sum(status_counts.values()),
            "recent_runs": [dict(r) for r in runs],
        }

    def query(self, status: str | None = None, server: str | None = None) -> list[dict]:
        """Query migrations with optional filters."""
        conditions: list[str] = []
        params: list[str] = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if server:
            conditions.append("source_server = ?")
            params.append(server)

        where = " WHERE " + " AND ".join(conditions) if conditions else ""

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM migrations{where} ORDER BY id", params,
            ).fetchall()

        return [dict(r) for r in rows]

    def export(self, output_dir: str) -> Path:
        """Export registry to JSON."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        data = {
            "summary": self.summary(),
            "migrations": self.query(),
        }

        path = out / "migration_registry_export.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return path
