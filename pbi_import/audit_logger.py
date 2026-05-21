"""
Audit Logger — immutable migration audit trail for compliance reporting.

Writes append-only JSONL audit log entries with timestamps, actor,
action, item details, and outcome. Supports log rotation and summary queries.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class AuditLogger:
    """Append-only audit trail for migration actions."""

    def __init__(self, log_dir: str = "audit_logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self.log_dir / "migration_audit.jsonl"

    def log(
        self,
        action: str,
        item_name: str = "",
        item_type: str = "",
        item_path: str = "",
        outcome: str = "success",
        detail: str = "",
        actor: str = "",
    ) -> dict:
        """Write an audit entry."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "item_name": item_name,
            "item_type": item_type,
            "item_path": item_path,
            "outcome": outcome,
            "detail": detail,
            "actor": actor or os.getenv("USERNAME", "system"),
        }

        with open(self._log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

        return entry

    def log_phase(self, phase: str, status: str, detail: str = "") -> dict:
        """Log a phase-level event."""
        return self.log(
            action=f"phase:{phase}",
            outcome=status,
            detail=detail,
        )

    def log_item(
        self,
        action: str,
        item: dict,
        outcome: str = "success",
        detail: str = "",
    ) -> dict:
        """Log an item-level event."""
        return self.log(
            action=action,
            item_name=item.get("Name", item.get("name", "")),
            item_type=item.get("Type", item.get("type", "")),
            item_path=item.get("Path", item.get("path", "")),
            outcome=outcome,
            detail=detail,
        )

    def query(
        self,
        action: str | None = None,
        outcome: str | None = None,
        since: str | None = None,
    ) -> list[dict]:
        """Query audit entries with optional filters."""
        entries: list[dict] = []
        if not self._log_file.exists():
            return entries

        with open(self._log_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if action and entry.get("action") != action:
                    continue
                if outcome and entry.get("outcome") != outcome:
                    continue
                if since and entry.get("timestamp", "") < since:
                    continue
                entries.append(entry)

        return entries

    def summary(self) -> dict:
        """Return a summary of all audit entries."""
        entries = self.query()
        by_action: dict[str, int] = {}
        by_outcome: dict[str, int] = {}
        for e in entries:
            by_action[e.get("action", "")] = by_action.get(e.get("action", ""), 0) + 1
            by_outcome[e.get("outcome", "")] = by_outcome.get(e.get("outcome", ""), 0) + 1

        return {
            "total_entries": len(entries),
            "by_action": by_action,
            "by_outcome": by_outcome,
            "first_entry": entries[0]["timestamp"] if entries else None,
            "last_entry": entries[-1]["timestamp"] if entries else None,
        }

    def export_report(self, output_path: str) -> Path:
        """Export audit trail as a JSON report."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "summary": self.summary(),
            "entries": self.query(),
        }
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        logger.info("Audit report exported to %s", out)
        return out
