"""
Sensitivity Labeler — propagates Microsoft Purview sensitivity labels to PBI content.

Maps PBIRS folder-level or item-level classification tags to Purview
Information Protection labels and applies them via the PBI REST API.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Common sensitivity label mappings (label GUID must be configured per tenant)
DEFAULT_LABEL_MAP: dict[str, str] = {
    "Public": "",
    "Internal": "",
    "Confidential": "",
    "Highly Confidential": "",
}


class SensitivityLabeler:
    """Apply Microsoft Purview sensitivity labels to migrated PBI content."""

    def __init__(
        self,
        pbi_client: Any,
        label_map: dict[str, str] | None = None,
    ):
        self.client = pbi_client
        self.label_map = label_map or {}

    @classmethod
    def from_file(cls, pbi_client: Any, path: str) -> "SensitivityLabeler":
        """Load label mapping from a JSON config file."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(pbi_client, data.get("label_map", data))

    def classify_catalog(self, catalog: list[dict]) -> list[dict]:
        """Scan catalog items and propose sensitivity classifications.

        Heuristics:
        - Path contains ``/Confidential/`` → Confidential
        - Path contains ``/HR/`` or ``/Finance/`` → Highly Confidential
        - Description mentions sensitive keywords → Confidential
        - Default → Internal
        """
        results: list[dict] = []
        for item in catalog:
            classification = self._classify_item(item)
            results.append({
                "name": item.get("Name", ""),
                "path": item.get("Path", ""),
                "proposed_label": classification,
                "label_id": self.label_map.get(classification, ""),
            })
        return results

    def apply_labels(
        self,
        published_items: list[dict],
        classifications: list[dict],
        dry_run: bool = False,
    ) -> dict:
        """Apply sensitivity labels to published PBI content."""
        results: dict[str, list[dict]] = {"applied": [], "skipped": [], "failed": []}

        class_lookup = {c["name"]: c for c in classifications}

        for item in published_items:
            name = item.get("name", "")
            cls_info = class_lookup.get(name)
            if not cls_info or not cls_info.get("label_id"):
                results["skipped"].append({"name": name, "reason": "no label mapping"})
                continue

            if dry_run:
                logger.info("[DRY RUN] Would apply label '%s' to %s", cls_info["proposed_label"], name)
                results["applied"].append({"name": name, "label": cls_info["proposed_label"], "dry_run": True})
                continue

            try:
                artifact_id = item.get("report_id") or item.get("dataset_id", "")
                artifact_type = "reports" if item.get("report_id") else "datasets"
                self.client.set_sensitivity_label(
                    artifact_type=artifact_type,
                    artifact_id=artifact_id,
                    label_id=cls_info["label_id"],
                )
                results["applied"].append({"name": name, "label": cls_info["proposed_label"]})
            except Exception as e:
                results["failed"].append({"name": name, "error": str(e)})

        logger.info(
            "Sensitivity labels: %d applied, %d skipped, %d failed",
            len(results["applied"]), len(results["skipped"]), len(results["failed"]),
        )
        return results

    def _classify_item(self, item: dict) -> str:
        """Classify an item based on path and metadata heuristics."""
        path = item.get("Path", "").lower()
        desc = item.get("Description", "").lower()

        highly_conf_keywords = ["/hr/", "/finance/", "/payroll/", "/legal/", "/pii/"]
        conf_keywords = ["/confidential/", "/restricted/", "/internal-only/"]
        sensitive_desc = ["confidential", "restricted", "pii", "personal", "salary"]

        if any(k in path for k in highly_conf_keywords):
            return "Highly Confidential"
        if any(k in path for k in conf_keywords):
            return "Confidential"
        if any(k in desc for k in sensitive_desc):
            return "Confidential"
        if "/public/" in path:
            return "Public"
        return "Internal"
