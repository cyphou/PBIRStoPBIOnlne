"""
Event Log — structured JSONL log of per-item migration events.

One JSON object per line: ``{"ts","phase","event","item","status","details"}``.
Designed to be tailed by metrics exporters and dashboards.
"""

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class EventLog:
    """Append-only JSONL event log."""

    def __init__(self, path: str | os.PathLike | None):
        self.path = Path(path) if path else None
        self._lock = threading.Lock()
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(
        self,
        phase: str,
        event: str,
        item: str = "",
        status: str = "",
        **details: Any,
    ) -> None:
        """Append a single event line."""
        if not self.path:
            return

        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "phase": phase,
            "event": event,
            "item": item,
            "status": status,
        }
        if details:
            record["details"] = details

        line = json.dumps(record, default=str)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")


_NOOP = EventLog(None)


def noop() -> EventLog:
    """Return a singleton no-op log used when ``--event-log`` is unset."""
    return _NOOP
