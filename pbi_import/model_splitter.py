"""
Model Splitter — separates thin reports from shared datasets.

When migrating, PBIRS bundles data models inside .pbix files. This module
detects when multiple reports share the same dataset and recommends splitting
into thin reports + shared semantic model for PBI Online best practices.
"""

import json
import logging
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


class ModelSplitter:
    """Detect shared datasets and recommend thin report / shared model splits."""

    def analyse(self, catalog: list[dict]) -> dict:
        """Analyse catalog for shared datasets.

        Returns split recommendations keyed by dataset connection.
        """
        # Group reports by dataset reference
        ds_to_reports: dict[str, list[dict]] = defaultdict(list)

        for item in catalog:
            if item.get("Type") not in ("PowerBIReport", "Report"):
                continue

            ds_ref = (
                item.get("DataSetReference")
                or item.get("SharedDataSetPath")
                or item.get("Name", "")
            )
            ds_to_reports[ds_ref].append({
                "name": item.get("Name", ""),
                "path": item.get("Path", ""),
                "type": item.get("Type", ""),
            })

        recommendations: list[dict] = []
        for ds_ref, reports in ds_to_reports.items():
            if len(reports) > 1:
                recommendations.append({
                    "dataset_reference": ds_ref,
                    "report_count": len(reports),
                    "reports": reports,
                    "action": "split",
                    "reason": f"{len(reports)} reports share this dataset — "
                              "split into shared semantic model + thin reports",
                })
            else:
                recommendations.append({
                    "dataset_reference": ds_ref,
                    "report_count": 1,
                    "reports": reports,
                    "action": "keep",
                    "reason": "Single report — no split needed",
                })

        result = {
            "recommendations": recommendations,
            "summary": {
                "total_datasets": len(recommendations),
                "split_recommended": sum(1 for r in recommendations if r["action"] == "split"),
                "total_reports_affected": sum(
                    r["report_count"] for r in recommendations if r["action"] == "split"
                ),
            },
        }

        logger.info(
            "Model split analysis: %d datasets, %d need splitting (%d reports affected)",
            result["summary"]["total_datasets"],
            result["summary"]["split_recommended"],
            result["summary"]["total_reports_affected"],
        )
        return result

    def save(self, output_dir: str, result: dict) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "model_split_recommendations.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        return path
