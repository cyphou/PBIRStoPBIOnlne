"""
Endorsement Manager — auto-promote or certify migrated PBI content.

Uses assessment scores to determine endorsement level and applies
promotion/certification via the PBI REST API.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class EndorsementManager:
    """Manage endorsement (Promoted/Certified) of PBI content."""

    # Assessment score thresholds for auto-endorsement
    CERTIFY_THRESHOLD = 90  # score >= 90 → Certified
    PROMOTE_THRESHOLD = 70  # score >= 70 → Promoted

    def __init__(self, pbi_client: Any):
        self.client = pbi_client

    def plan(
        self,
        published_items: list[dict],
        assessments: dict,
    ) -> list[dict]:
        """Generate endorsement plan based on assessment scores.

        Args:
            published_items: items already published to PBI Online.
            assessments: per-item assessment results from the assessment phase.
        """
        plan: list[dict] = []

        for item in published_items:
            name = item.get("name", "")
            score = self._get_score(name, assessments)
            endorsement = self._determine_endorsement(score)

            plan.append({
                "name": name,
                "dataset_id": item.get("dataset_id", ""),
                "report_id": item.get("report_id", ""),
                "score": score,
                "endorsement": endorsement,
            })

        return plan

    def apply(
        self,
        plan: list[dict],
        workspace_id: str,
        dry_run: bool = False,
    ) -> dict:
        """Apply endorsement levels to published content."""
        results: dict[str, list[dict]] = {"endorsed": [], "skipped": [], "failed": []}

        for entry in plan:
            endorsement = entry.get("endorsement")
            if not endorsement:
                results["skipped"].append({"name": entry["name"], "reason": "below threshold"})
                continue

            if dry_run:
                logger.info(
                    "[DRY RUN] Would %s '%s' (score=%d)",
                    endorsement, entry["name"], entry["score"],
                )
                results["endorsed"].append({**entry, "dry_run": True})
                continue

            try:
                artifact_id = entry.get("dataset_id") or entry.get("report_id", "")
                self.client.set_endorsement(
                    workspace_id=workspace_id,
                    artifact_id=artifact_id,
                    endorsement=endorsement,
                )
                results["endorsed"].append(entry)
            except Exception as e:
                results["failed"].append({"name": entry["name"], "error": str(e)})

        logger.info(
            "Endorsements: %d applied, %d skipped, %d failed",
            len(results["endorsed"]), len(results["skipped"]), len(results["failed"]),
        )
        return results

    def _determine_endorsement(self, score: int) -> str | None:
        """Determine endorsement level from assessment score."""
        if score >= self.CERTIFY_THRESHOLD:
            return "Certified"
        if score >= self.PROMOTE_THRESHOLD:
            return "Promoted"
        return None

    @staticmethod
    def _get_score(name: str, assessments: dict) -> int:
        """Look up the overall assessment score for an item."""
        for item in assessments.get("items", []):
            if item.get("Name") == name or item.get("name") == name:
                return item.get("overall_score", 0)
        return 0
