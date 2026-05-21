"""
Checkpoint Manager — tracks export/import progress for resume capability.

Writes a ``.checkpoint.json`` file alongside the output directory.  On a
subsequent run the downloader reads the checkpoint and skips items that were
already successfully processed, enabling interrupted pipelines to pick up
where they left off.
"""

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CHECKPOINT_FILE = ".checkpoint.json"


class CheckpointManager:
    """Track completed items so interrupted exports/imports can resume."""

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.path = self.output_dir / _CHECKPOINT_FILE
        self._data: dict[str, Any] = self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_done(self, item_id: str) -> bool:
        """Return True if *item_id* was already processed successfully."""
        return item_id in self._data.get("completed", {})

    def mark_done(self, item_id: str, metadata: dict | None = None) -> None:
        """Record *item_id* as successfully processed."""
        completed = self._data.setdefault("completed", {})
        completed[item_id] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **(metadata or {}),
        }
        self._save()

    def mark_failed(self, item_id: str, error: str) -> None:
        """Record *item_id* as failed (will be retried on next run)."""
        failed = self._data.setdefault("failed", {})
        failed[item_id] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "error": error,
        }
        # Remove from completed if it was there from a previous run
        self._data.get("completed", {}).pop(item_id, None)
        self._save()

    def reset(self) -> None:
        """Clear all checkpoint data (start fresh)."""
        self._data = {"completed": {}, "failed": {}, "started_at": self._now()}
        self._save()
        logger.info("Checkpoint reset — will re-download all items")

    @property
    def completed_count(self) -> int:
        return len(self._data.get("completed", {}))

    @property
    def failed_count(self) -> int:
        return len(self._data.get("failed", {}))

    @property
    def completed_ids(self) -> set[str]:
        return set(self._data.get("completed", {}).keys())

    def summary(self) -> dict:
        """Return a summary of checkpoint state."""
        return {
            "completed": self.completed_count,
            "failed": self.failed_count,
            "started_at": self._data.get("started_at"),
            "last_updated": self._data.get("last_updated"),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> dict:
        """Load checkpoint from disk or return empty state."""
        if self.path.exists():
            try:
                with open(self.path, encoding="utf-8") as f:
                    data = json.load(f)
                logger.info(
                    "Resuming from checkpoint: %d completed, %d failed",
                    len(data.get("completed", {})),
                    len(data.get("failed", {})),
                )
                return data
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Corrupt checkpoint file, starting fresh: %s", e)
        return {"completed": {}, "failed": {}, "started_at": self._now()}

    def _save(self) -> None:
        """Persist checkpoint to disk."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._data["last_updated"] = self._now()
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)
        try:
            tmp.replace(self.path)
        except OSError:
            # Windows may briefly lock the target; fall back to unlink+rename
            if self.path.exists():
                self.path.unlink()
            tmp.rename(self.path)

    @staticmethod
    def _now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
