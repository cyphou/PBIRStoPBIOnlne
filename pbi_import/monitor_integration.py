"""
Azure Monitor Integration — sends migration telemetry to Azure Monitor / Log Analytics.

Uses the Azure Monitor Ingestion API (Data Collection Endpoint) to push
custom logs for migration tracking, alerting, and dashboarding.
Stdlib-only: uses urllib for HTTP requests.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


class MonitorIntegration:
    """Send migration telemetry to Azure Monitor."""

    def __init__(
        self,
        dce_endpoint: str | None = None,
        dcr_rule_id: str | None = None,
        stream_name: str = "Custom-MigrationLogs_CL",
        client: Any | None = None,
    ):
        """
        Args:
            dce_endpoint: Data Collection Endpoint URL.
            dcr_rule_id: Data Collection Rule immutable ID.
            stream_name: custom log stream name.
            client: HTTP client with auth (must support ``post(url, json=...)``.
        """
        self.dce_endpoint = dce_endpoint
        self.dcr_rule_id = dcr_rule_id
        self.stream_name = stream_name
        self.client = client
        self._buffer: list[dict] = []

    def log_event(
        self,
        event_type: str,
        item_name: str = "",
        status: str = "",
        details: dict | None = None,
    ) -> None:
        """Buffer a log event for batch sending."""
        entry = {
            "TimeGenerated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "EventType": event_type,
            "ItemName": item_name,
            "Status": status,
            "Details": json.dumps(details or {}),
        }
        self._buffer.append(entry)

    def log_phase(self, phase: str, status: str, duration_seconds: float = 0, **kwargs: str) -> None:
        """Log a migration phase event."""
        self.log_event(
            event_type=f"phase_{phase}",
            status=status,
            details={"duration_seconds": duration_seconds, **kwargs},
        )

    def flush(self, dry_run: bool = False) -> dict:
        """Send buffered events to Azure Monitor.

        Args:
            dry_run: log locally instead of sending.
        """
        if not self._buffer:
            return {"status": "empty", "events": 0}

        events = list(self._buffer)
        self._buffer.clear()

        if dry_run or not self.dce_endpoint:
            logger.info("[DRY RUN] Would send %d events to Azure Monitor", len(events))
            return {"status": "dry_run", "events": len(events)}

        url = (
            f"{self.dce_endpoint}/dataCollectionRules/{self.dcr_rule_id}"
            f"/streams/{self.stream_name}?api-version=2023-01-01"
        )

        try:
            self.client.post(url, json=events)
            logger.info("Sent %d events to Azure Monitor", len(events))
            return {"status": "sent", "events": len(events)}
        except Exception as e:
            logger.error("Failed to send to Azure Monitor: %s", e)
            # Re-buffer failed events
            self._buffer.extend(events)
            return {"status": "failed", "events": len(events), "error": str(e)}

    def from_results(self, results: dict) -> None:
        """Populate events from migration results."""
        summary = results.get("summary", {})

        self.log_event(
            event_type="migration_summary",
            status="completed",
            details=summary,
        )

        # Individual item results
        for item in results.get("items", []):
            self.log_event(
                event_type="item_migration",
                item_name=item.get("name", ""),
                status=item.get("status", ""),
                details={
                    "type": item.get("type", ""),
                    "workspace": item.get("workspace_id", ""),
                },
            )

    def save_local(self, output_dir: str) -> Path:
        """Save buffered events locally as JSON."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "monitor_events.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._buffer, f, indent=2)
        return path
