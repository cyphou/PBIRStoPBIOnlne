"""
Report Publisher — publishes Power BI reports (.pbix) to PBI Online.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ReportPublisher:
    """Publish Power BI reports to PBI Online workspaces."""

    def __init__(self, pbi_client: Any):
        self.client = pbi_client

    def publish_all(
        self,
        converted_dir: str,
        workspace_id: str,
        name_conflict: str = "CreateOrOverwrite",
        dry_run: bool = False,
    ) -> dict:
        """Publish all Power BI reports from converted directory."""
        pbix_dir = Path(converted_dir) / "powerbi"
        results: dict[str, list] = {"success": [], "failed": [], "skipped": []}

        if not pbix_dir.exists():
            logger.warning("No powerbi directory found at %s", pbix_dir)
            return results

        for pbix_file in pbix_dir.glob("*.pbix"):
            meta_file = pbix_file.with_suffix(".meta.json")
            meta = {}
            if meta_file.exists():
                with open(meta_file, encoding="utf-8") as f:
                    meta = json.load(f)

            try:
                result = self._publish_report(
                    pbix_file, workspace_id, name_conflict, meta, dry_run
                )
                results["success"].append(result)
            except Exception as e:
                logger.error("Failed to publish %s: %s", pbix_file.name, e)
                results["failed"].append({
                    "name": pbix_file.stem,
                    "error": str(e),
                })

        return results

    def _publish_report(
        self,
        pbix_path: Path,
        workspace_id: str,
        name_conflict: str,
        meta: dict,
        dry_run: bool,
    ) -> dict:
        """Publish a single .pbix file."""
        display_name = pbix_path.stem

        if dry_run:
            logger.info("[DRY RUN] Would publish %s to workspace %s", display_name, workspace_id)
            return {"name": display_name, "status": "dry_run"}

        logger.info("Publishing %s to workspace %s", display_name, workspace_id)

        with open(pbix_path, "rb") as f:
            content = f.read()

        import_result = self.client.import_pbix(
            workspace_id=workspace_id,
            display_name=display_name,
            file_content=content,
            name_conflict=name_conflict,
        )

        report_id = import_result.get("id", "")
        dataset_id = import_result.get("datasets", [{}])[0].get("id", "") if import_result.get("datasets") else ""

        # Apply gateway binding if specified
        gateway = meta.get("gateway_binding")
        if gateway and dataset_id:
            try:
                self.client.bind_to_gateway(
                    dataset_id=dataset_id,
                    gateway_id=gateway["gateway_id"],
                    datasource_ids=gateway.get("datasource_ids", []),
                )
                logger.info("Bound dataset %s to gateway %s", dataset_id, gateway["gateway_id"])
            except Exception as e:
                logger.warning("Gateway binding failed for %s: %s", display_name, e)

        return {
            "name": display_name,
            "report_id": report_id,
            "dataset_id": dataset_id,
            "status": "published",
        }
