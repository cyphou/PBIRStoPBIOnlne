"""
Subscription Migrator — recreates PBIRS email subscriptions as PBI Online subscriptions.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SubscriptionMigrator:
    """Migrate PBIRS subscriptions to PBI Online."""

    # Supported delivery types in PBI Online
    SUPPORTED_DELIVERY = {"Email"}

    def __init__(self, pbi_client: Any):
        self.client = pbi_client

    def migrate_all(
        self,
        subscriptions: dict,
        published_items: dict,
        workspace_id: str,
        dry_run: bool = False,
    ) -> dict:
        """Migrate subscriptions to PBI Online."""
        subs = subscriptions.get("subscriptions", [])
        results: dict[str, list] = {"migrated": [], "skipped": [], "failed": []}

        for sub in subs:
            delivery = sub.get("DeliveryExtension", "")

            # Skip unsupported delivery types
            if delivery not in self.SUPPORTED_DELIVERY:
                results["skipped"].append({
                    "description": sub.get("Description", ""),
                    "delivery": delivery,
                    "reason": f"Delivery type '{delivery}' not supported in PBI Online",
                })
                continue

            # Find published report for this subscription
            report_path = sub.get("Report", "")
            published = self._find_published_item(report_path, published_items)
            if not published:
                results["skipped"].append({
                    "description": sub.get("Description", ""),
                    "reason": f"Source report not published: {report_path}",
                })
                continue

            try:
                result = self._create_subscription(sub, published, workspace_id, dry_run)
                results["migrated"].append(result)
            except Exception as e:
                logger.error("Failed to migrate subscription: %s", e)
                results["failed"].append({
                    "description": sub.get("Description", ""),
                    "error": str(e),
                })

        return results

    def _create_subscription(
        self,
        source_sub: dict,
        published: dict,
        workspace_id: str,
        dry_run: bool,
    ) -> dict:
        """Create a PBI Online subscription from PBIRS subscription data."""
        report_id = published.get("report_id", "")
        description = source_sub.get("Description", "")

        if dry_run:
            logger.info("[DRY RUN] Would create subscription for report %s", published.get("name"))
            return {"description": description, "status": "dry_run"}

        # Map schedule
        schedule = self._map_schedule(source_sub.get("Schedule", {}))

        # Map recipients
        recipients = self._extract_recipients(source_sub)

        self.client.create_subscription(
            report_id=report_id,
            title=description,
            frequency=schedule.get("frequency", "Daily"),
            start_time=schedule.get("start_time", "08:00:00"),
            emails=recipients,
        )

        return {
            "description": description,
            "report": published.get("name"),
            "status": "migrated",
        }

    @staticmethod
    def _map_schedule(ssrs_schedule: dict) -> dict:
        """Map SSRS schedule to PBI Online schedule."""
        recurrence = ssrs_schedule.get("RecurrencePattern", "")
        if "Daily" in recurrence:
            return {"frequency": "Daily", "start_time": ssrs_schedule.get("StartDateTime", "08:00:00")}
        if "Weekly" in recurrence:
            return {"frequency": "Weekly", "start_time": ssrs_schedule.get("StartDateTime", "08:00:00")}
        if "Monthly" in recurrence:
            return {"frequency": "Monthly", "start_time": ssrs_schedule.get("StartDateTime", "08:00:00")}
        return {"frequency": "Daily", "start_time": "08:00:00"}

    @staticmethod
    def _extract_recipients(sub: dict) -> list[str]:
        """Extract email recipients from SSRS subscription."""
        params = sub.get("ParameterValues", [])
        for p in params:
            if p.get("Name") == "TO":
                return [e.strip() for e in p.get("Value", "").split(";") if e.strip()]
        return []

    @staticmethod
    def _find_published_item(report_path: str, published_items: dict) -> dict | None:
        """Find a published item by its source PBIRS path."""
        for items in published_items.values():
            if isinstance(items, list):
                for item in items:
                    if item.get("source_path") == report_path or item.get("name") in report_path:
                        return item
        return None
