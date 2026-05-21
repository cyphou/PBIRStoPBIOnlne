"""
Paginated Publisher — publishes paginated reports (.rdl) to PBI Online via REST API.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PaginatedPublisher:
    """Publish paginated reports to PBI Online (Premium/PPU workspaces)."""

    def __init__(self, pbi_client: Any):
        self.client = pbi_client

    def publish_all(
        self,
        converted_dir: str,
        workspace_id: str,
        dry_run: bool = False,
    ) -> dict:
        """Publish all paginated reports from converted directory."""
        rdl_dir = Path(converted_dir) / "paginated"
        results: dict[str, list] = {"success": [], "failed": [], "skipped": []}

        if not rdl_dir.exists():
            logger.info("No paginated directory found at %s", rdl_dir)
            return results

        for rdl_file in rdl_dir.glob("*.rdl"):
            meta_file = rdl_file.with_suffix(".meta.json")
            meta = {}
            if meta_file.exists():
                with open(meta_file, encoding="utf-8") as f:
                    meta = json.load(f)

            try:
                result = self._publish_rdl(rdl_file, workspace_id, meta, dry_run)
                results["success"].append(result)
            except Exception as e:
                logger.error("Failed to publish paginated report %s: %s", rdl_file.name, e)
                results["failed"].append({
                    "name": rdl_file.stem,
                    "error": str(e),
                })

        return results

    def _publish_rdl(
        self,
        rdl_path: Path,
        workspace_id: str,
        meta: dict,
        dry_run: bool,
    ) -> dict:
        """Publish a single .rdl file."""
        display_name = rdl_path.stem

        if dry_run:
            logger.info("[DRY RUN] Would publish paginated report %s", display_name)
            return {"name": display_name, "status": "dry_run"}

        logger.info("Publishing paginated report %s to workspace %s", display_name, workspace_id)

        with open(rdl_path, "rb") as f:
            content = f.read()

        import_result = self.client.import_rdl(
            workspace_id=workspace_id,
            display_name=display_name,
            file_content=content,
        )

        report_id = import_result.get("id", "")

        # Apply gateway binding if specified
        gateway = meta.get("gateway_binding")
        if gateway and report_id:
            try:
                self.client.bind_paginated_to_gateway(
                    report_id=report_id,
                    gateway_id=gateway["gateway_id"],
                )
            except Exception as e:
                logger.warning("Gateway binding failed for paginated report %s: %s", display_name, e)

        return {
            "name": display_name,
            "report_id": report_id,
            "status": "published",
            "requires_premium": True,
        }
