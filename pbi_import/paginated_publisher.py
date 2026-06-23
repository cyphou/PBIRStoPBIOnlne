"""
Paginated Publisher — publishes paginated reports (.rdl) to PBI Online via REST API.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        workers: int = 1,
    ) -> dict:
        """Publish all paginated reports from converted directory."""
        rdl_dir = Path(converted_dir) / "paginated"
        results: dict[str, list] = {"success": [], "failed": [], "skipped": []}

        if not rdl_dir.exists():
            logger.info("No paginated directory found at %s", rdl_dir)
            return results

        def _process(rdl_file: Path) -> tuple[str, Any]:
            meta_file = rdl_file.with_suffix(".meta.json")
            meta = {}
            if meta_file.exists():
                with open(meta_file, encoding="utf-8") as f:
                    meta = json.load(f)
            try:
                return ("ok", self._publish_rdl(rdl_file, workspace_id, meta, dry_run))
            except Exception as e:
                logger.error("Failed to publish paginated report %s: %s", rdl_file.name, e)
                return ("fail", {"name": rdl_file.stem, "error": str(e)})

        files = list(rdl_dir.glob("*.rdl"))
        if workers > 1 and len(files) > 1:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for status, payload in [f.result() for f in as_completed(
                        pool.submit(_process, f) for f in files)]:
                    results["success" if status == "ok" else "failed"].append(payload)
        else:
            for rdl_file in files:
                status, payload = _process(rdl_file)
                results["success" if status == "ok" else "failed"].append(payload)

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
