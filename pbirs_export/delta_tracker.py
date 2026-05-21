"""
Delta Tracker — tracks content changes between migration runs for incremental sync.

Uses a local SQLite database (stdlib) to store content hashes and modification
timestamps so that only changed/new items are migrated on subsequent runs.
"""

import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS content_state (
    item_id     TEXT PRIMARY KEY,
    path        TEXT NOT NULL,
    content_type TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    modified_date TEXT NOT NULL,
    migrated_at  TEXT NOT NULL,
    workspace_id TEXT,
    target_id    TEXT
);
CREATE INDEX IF NOT EXISTS idx_path ON content_state(path);
"""


class DeltaTracker:
    """Track content state across migration runs for incremental/delta sync."""

    def __init__(self, db_path: str = ".migration_state.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    # Change detection
    # ------------------------------------------------------------------

    def detect_changes(self, catalog: list[dict]) -> dict[str, list[dict]]:
        """Compare *catalog* against stored state.

        Returns ``{"new": [...], "modified": [...], "unchanged": [...], "deleted": [...]}``.
        """
        result: dict[str, list[dict]] = {
            "new": [], "modified": [], "unchanged": [], "deleted": [],
        }

        current_ids: set[str] = set()
        for item in catalog:
            item_id = item.get("Id", "")
            current_ids.add(item_id)
            content_hash = self._hash_item(item)
            row = self._get(item_id)

            if row is None:
                result["new"].append(item)
            elif row["content_hash"] != content_hash:
                result["modified"].append(item)
            else:
                result["unchanged"].append(item)

        # Detect deletions
        stored_ids = {r["item_id"] for r in self._all()}
        for deleted_id in stored_ids - current_ids:
            row = self._get(deleted_id)
            if row:
                result["deleted"].append(dict(row))

        logger.info(
            "Delta: %d new, %d modified, %d unchanged, %d deleted",
            len(result["new"]), len(result["modified"]),
            len(result["unchanged"]), len(result["deleted"]),
        )
        return result

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def record(
        self,
        item: dict,
        workspace_id: str = "",
        target_id: str = "",
    ) -> None:
        """Record an item as successfully migrated."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO content_state
               (item_id, path, content_type, content_hash, modified_date, migrated_at, workspace_id, target_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item.get("Id", ""),
                item.get("Path", ""),
                item.get("Type", ""),
                self._hash_item(item),
                item.get("ModifiedDate", now),
                now,
                workspace_id,
                target_id,
            ),
        )
        self._conn.commit()

    def remove(self, item_id: str) -> None:
        """Remove an item from the state database."""
        self._conn.execute("DELETE FROM content_state WHERE item_id = ?", (item_id,))
        self._conn.commit()

    def get_state(self, item_id: str) -> dict | None:
        """Return stored state for an item, or None."""
        row = self._get(item_id)
        return dict(row) if row else None

    def summary(self) -> dict:
        """Return a summary of stored state."""
        cur = self._conn.execute(
            "SELECT content_type, COUNT(*) as cnt FROM content_state GROUP BY content_type"
        )
        by_type = {r["content_type"]: r["cnt"] for r in cur.fetchall()}
        cur2 = self._conn.execute("SELECT COUNT(*) as total FROM content_state")
        total = cur2.fetchone()["total"]
        return {"total": total, "by_type": by_type}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get(self, item_id: str) -> sqlite3.Row | None:
        cur = self._conn.execute(
            "SELECT * FROM content_state WHERE item_id = ?", (item_id,)
        )
        return cur.fetchone()

    def _all(self) -> list[sqlite3.Row]:
        cur = self._conn.execute("SELECT * FROM content_state")
        return cur.fetchall()

    @staticmethod
    def _hash_item(item: dict) -> str:
        """Compute a stable hash of item metadata for change detection."""
        keys = ("Name", "Path", "Type", "ModifiedDate", "Size", "Description")
        data = json.dumps({k: item.get(k, "") for k in keys}, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:16]
