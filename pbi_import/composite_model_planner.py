"""
Composite Model Planner — plans composite model architecture for PBI Online.

Analyses datasets to recommend composite models that combine Import and
DirectQuery partitions, or chain multiple semantic models together.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class CompositeModelPlanner:
    """Plan composite model architecture for migrated datasets."""

    def plan(self, catalog: list[dict]) -> dict:
        """Analyse catalog and produce composite model recommendations.

        Each item with multiple datasources or mixed query modes is a candidate.
        """
        candidates: list[dict] = []
        non_candidates: list[str] = []

        for item in catalog:
            if item.get("Type") not in ("PowerBIReport", "DataSet"):
                continue

            datasources = item.get("DataSources", [])
            if len(datasources) < 2:
                non_candidates.append(item.get("Name", ""))
                continue

            # Check for mixed-mode potential
            ds_types = {ds.get("DataSourceType", "unknown") for ds in datasources}
            has_import = any(
                t in ("Sql", "OleDb", "File", "Excel") for t in ds_types
            )
            has_directquery = any(
                t in ("AzureSqlDatabase", "AzureSynapse", "AnalysisServices")
                for t in ds_types
            )

            if has_import and has_directquery:
                model_type = "mixed"
            elif len(ds_types) > 1:
                model_type = "multi_source"
            else:
                non_candidates.append(item.get("Name", ""))
                continue

            partitions: list[dict] = []
            for ds in datasources:
                ds_type = ds.get("DataSourceType", "unknown")
                mode = "DirectQuery" if ds_type in (
                    "AzureSqlDatabase", "AzureSynapse", "AnalysisServices",
                ) else "Import"
                partitions.append({
                    "datasource": ds.get("Name", ""),
                    "type": ds_type,
                    "recommended_mode": mode,
                })

            candidates.append({
                "name": item.get("Name", ""),
                "path": item.get("Path", ""),
                "model_type": model_type,
                "datasource_count": len(datasources),
                "partitions": partitions,
                "requires_premium": True,  # Composite models require Premium/PPU
            })

        result = {
            "candidates": candidates,
            "non_candidates": non_candidates,
            "summary": {
                "total_analysed": len(candidates) + len(non_candidates),
                "composite_candidates": len(candidates),
                "mixed_mode": sum(1 for c in candidates if c["model_type"] == "mixed"),
                "multi_source": sum(1 for c in candidates if c["model_type"] == "multi_source"),
            },
        }

        logger.info(
            "Composite model planning: %d candidates (%d mixed, %d multi-source)",
            len(candidates),
            result["summary"]["mixed_mode"],
            result["summary"]["multi_source"],
        )
        return result

    def save(self, output_dir: str, result: dict) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "composite_model_plan.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        return path
