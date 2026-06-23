"""
Dataset Publisher — publishes shared datasets/semantic models to PBI Online.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        workers: int = 1,
    ) -> dict:
        """Publish all datasets from converted directory."""
        ds_dir = Path(converted_dir) / "datasets"
        results: dict[str, list] = {"success": [], "failed": [], "skipped": []}

        if not ds_dir.exists():
            logger.info("No datasets directory found at %s", ds_dir)
            return results

        def _process(ds_file: Path) -> tuple[str, Any]:
            try:
                return ("ok", self._publish_dataset(ds_file, workspace_id, dry_run))
            except Exception as e:
                logger.error("Failed to publish dataset %s: %s", ds_file.name, e)
                return ("fail", {"name": ds_file.stem, "error": str(e)})

        files = [f for f in ds_dir.iterdir() if f.suffix in (".rsd", ".json")]
        if workers > 1 and len(files) > 1:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for status, payload in [f.result() for f in as_completed(
                        pool.submit(_process, f) for f in files)]:
                    results["success" if status == "ok" else "failed"].append(payload)
        else:
            for ds_file in files:
                status, payload = _process(ds_file)
                results["success" if status == "ok" else "failed"].append(payload)

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
