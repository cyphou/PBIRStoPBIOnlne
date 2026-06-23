"""Pipeline-level checkpoint — tracks completed phases for ``--resume``.

This complements the per-item ``pbirs_export.checkpoint.CheckpointManager`` by
recording which **phases** of the 5-phase pipeline have completed so that an
interrupted ``--full`` run can be resumed without re-doing earlier phases.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CHECKPOINT_FILE = "pipeline.checkpoint.json"


class PipelineCheckpoint:
    """Track per-phase completion across a multi-phase migration run."""

    def __init__(self, root_dir: str):
        self.root = Path(root_dir)
        self.path = self.root / _CHECKPOINT_FILE
        self._data: dict[str, Any] = self._load()

    def is_complete(self, phase: str) -> bool:
        return phase in self._data.get("completed_phases", {})

    def mark_complete(self, phase: str, exit_code: int) -> None:
        completed = self._data.setdefault("completed_phases", {})
        completed[phase] = {
            "timestamp": _now(),
            "exit_code": int(exit_code),
        }
        self._save()

    def mark_failed(self, phase: str, error: str) -> None:
        failed = self._data.setdefault("failed_phases", {})
        failed[phase] = {"timestamp": _now(), "error": error}
        self._save()

    def reset(self) -> None:
        self._data = {"completed_phases": {}, "failed_phases": {}, "started_at": _now()}
        self._save()
        logger.info("Pipeline checkpoint reset")

    def summary(self) -> dict:
        return {
            "completed": list(self._data.get("completed_phases", {}).keys()),
            "failed": list(self._data.get("failed_phases", {}).keys()),
            "started_at": self._data.get("started_at"),
            "last_updated": self._data.get("last_updated"),
        }

    def _load(self) -> dict:
        if self.path.exists():
            try:
                with self.path.open(encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Corrupt pipeline checkpoint, starting fresh: %s", e)
        return {"completed_phases": {}, "failed_phases": {}, "started_at": _now()}

    def _save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._data["last_updated"] = _now()
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)
        try:
            tmp.replace(self.path)
        except OSError:
            if self.path.exists():
                self.path.unlink()
            tmp.rename(self.path)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
