"""
Refresh Scheduler — configures dataset refresh schedules in PBI Online.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class RefreshScheduler:
    """Set up dataset refresh schedules in PBI Online."""

    def __init__(self, pbi_client: Any):
        self.client = pbi_client

    def configure_refreshes(
        self,
        published_items: list[dict],
        schedules: list[dict],
        dry_run: bool = False,
    ) -> dict:
        """Configure refresh schedules for published datasets."""
        results: dict[str, list] = {"configured": [], "skipped": [], "failed": []}

        for item in published_items:
            dataset_id = item.get("dataset_id", "")
            if not dataset_id:
                continue

            # Find matching PBIRS schedule
            schedule = self._find_schedule(item, schedules)
            if not schedule:
                results["skipped"].append({
                    "name": item.get("name"),
                    "reason": "No matching PBIRS schedule found",
                })
                continue

            try:
                result = self._configure_refresh(dataset_id, item, schedule, dry_run)
                results["configured"].append(result)
            except Exception as e:
                logger.error("Failed to configure refresh for %s: %s", item.get("name"), e)
                results["failed"].append({
                    "name": item.get("name"),
                    "error": str(e),
                })

        return results

    def _configure_refresh(
        self,
        dataset_id: str,
        item: dict,
        schedule: dict,
        dry_run: bool,
    ) -> dict:
        """Configure a single dataset refresh schedule."""
        name = item.get("name", "")

        if dry_run:
            logger.info("[DRY RUN] Would configure refresh for %s", name)
            return {"name": name, "status": "dry_run"}

        # Map PBIRS schedule to PBI Online refresh schedule
        pbi_schedule = self._map_schedule(schedule)

        self.client.update_refresh_schedule(
            dataset_id=dataset_id,
            enabled=True,
            frequency=pbi_schedule["frequency"],
            time_zone=pbi_schedule.get("time_zone", "UTC"),
            times=pbi_schedule.get("times", ["08:00"]),
        )

        logger.info("Configured refresh for %s: %s", name, pbi_schedule)
        return {"name": name, "status": "configured", "schedule": pbi_schedule}

    @staticmethod
    def _map_schedule(pbirs_schedule: dict) -> dict:
        """Map PBIRS cache refresh plan to PBI Online refresh schedule."""
        recurrence = pbirs_schedule.get("RecurrencePattern", "Daily")
        start_time = pbirs_schedule.get("StartDateTime", "08:00")

        # PBI Online supports up to 8 refreshes per day (Pro) or 48 (Premium)
        if "Minute" in recurrence or "Hourly" in recurrence:
            return {
                "frequency": "Daily",
                "times": ["06:00", "09:00", "12:00", "15:00", "18:00"],
            }
        if "Daily" in recurrence:
            return {"frequency": "Daily", "times": [start_time[:5]]}
        if "Weekly" in recurrence:
            return {"frequency": "Weekly", "times": [start_time[:5]]}

        return {"frequency": "Daily", "times": ["08:00"]}

    @staticmethod
    def _find_schedule(item: dict, schedules: list[dict]) -> dict | None:
        """Find a PBIRS schedule that applies to the given item."""
        for schedule in schedules:
            if schedule.get("ReportId") == item.get("source_id"):
                return schedule
        return None
