"""
Rollback Engine — reverts PBI Online changes if migration fails.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class RollbackEngine:
    """Rollback published content from PBI Online workspace."""

    def __init__(self, pbi_client: Any):
        self.client = pbi_client

    def rollback(
        self,
        workspace_id: str,
        published_items: dict,
        dry_run: bool = False,
    ) -> dict:
        """Rollback all published items from a workspace."""
        results: dict[str, list] = {"deleted": [], "failed": []}

        # Delete reports
        for item in published_items.get("reports", {}).get("success", []):
            report_id = item.get("report_id", "")
            if not report_id:
                continue
            try:
                if dry_run:
                    logger.info("[DRY RUN] Would delete report %s", item.get("name"))
                else:
                    self.client.delete_report(workspace_id, report_id)
                results["deleted"].append({"name": item.get("name"), "type": "report"})
            except Exception as e:
                results["failed"].append({"name": item.get("name"), "error": str(e)})

        # Delete datasets
        for item in published_items.get("datasets", {}).get("success", []):
            dataset_id = item.get("dataset_id", "")
            if not dataset_id:
                continue
            try:
                if dry_run:
                    logger.info("[DRY RUN] Would delete dataset %s", item.get("name"))
                else:
                    self.client.delete_dataset(workspace_id, dataset_id)
                results["deleted"].append({"name": item.get("name"), "type": "dataset"})
            except Exception as e:
                results["failed"].append({"name": item.get("name"), "error": str(e)})

        logger.info(
            "Rollback complete: %d deleted, %d failed",
            len(results["deleted"]),
            len(results["failed"]),
        )
        return results
