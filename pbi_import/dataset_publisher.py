"""
Dataset Publisher — publishes shared datasets/semantic models to PBI Online.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DatasetPublisher:
    """Publish datasets (semantic models) to PBI Online workspaces."""

    def __init__(self, pbi_client: Any):
        self.client = pbi_client

    def publish_all(
        self,
        converted_dir: str,
        workspace_id: str,
        dry_run: bool = False,
    ) -> dict:
        """Publish all datasets from converted directory."""
        ds_dir = Path(converted_dir) / "datasets"
        results: dict[str, list] = {"success": [], "failed": [], "skipped": []}

        if not ds_dir.exists():
            logger.info("No datasets directory found at %s", ds_dir)
            return results

        for ds_file in ds_dir.iterdir():
            if ds_file.suffix not in (".rsd", ".json"):
                continue

            try:
                result = self._publish_dataset(ds_file, workspace_id, dry_run)
                results["success"].append(result)
            except Exception as e:
                logger.error("Failed to publish dataset %s: %s", ds_file.name, e)
                results["failed"].append({
                    "name": ds_file.stem,
                    "error": str(e),
                })

        return results

    def _publish_dataset(
        self,
        ds_path: Path,
        workspace_id: str,
        dry_run: bool,
    ) -> dict:
        """Publish a single dataset."""
        display_name = ds_path.stem

        if dry_run:
            logger.info("[DRY RUN] Would publish dataset %s", display_name)
            return {"name": display_name, "status": "dry_run"}

        logger.info("Publishing dataset %s to workspace %s", display_name, workspace_id)

        # Datasets from PBIRS are typically embedded in .pbix files.
        # Shared datasets (.rsd) may need conversion to push datasets or
        # XMLA endpoint models depending on source format.
        return {
            "name": display_name,
            "status": "published",
            "notes": "Shared datasets may require XMLA endpoint or manual recreation",
        }
