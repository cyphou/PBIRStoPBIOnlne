"""
Report Publisher — publishes Power BI reports (.pbix) to PBI Online.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from pbi_import.large_file_handler import LargeFileHandler

logger = logging.getLogger(__name__)


class ReportPublisher:
    """Publish Power BI reports to PBI Online workspaces."""

    def __init__(
        self,
        pbi_client: Any,
        large_file_threshold_mb: int = 1024,
        enable_large_file_upload: bool = True,
    ):
        self.client = pbi_client
        self.large_file_threshold_mb = large_file_threshold_mb
        self.enable_large_file_upload = enable_large_file_upload

    def publish_all(
        self,
        converted_dir: str,
        workspace_id: str,
        name_conflict: str = "CreateOrOverwrite",
        dry_run: bool = False,
        workers: int = 1,
    ) -> dict:
        """Publish all Power BI reports from converted directory.

        ``workers`` enables ThreadPoolExecutor-based parallelism for file-level imports.
        """
        pbix_dir = Path(converted_dir) / "powerbi"
        results: dict[str, list] = {"success": [], "failed": [], "skipped": []}

        if not pbix_dir.exists():
            logger.warning("No powerbi directory found at %s", pbix_dir)
            return results

        def _process(pbix_file: Path) -> tuple[str, Any]:
            meta_file = pbix_file.with_suffix(".meta.json")
            meta = {}
            if meta_file.exists():
                with open(meta_file, encoding="utf-8") as f:
                    meta = json.load(f)
            try:
                return ("ok", self._publish_report(
                    pbix_file, workspace_id, name_conflict, meta, dry_run
                ))
            except Exception as e:
                logger.error("Failed to publish %s: %s", pbix_file.name, e)
                return ("fail", {"name": pbix_file.stem, "error": str(e)})

        files = list(pbix_dir.glob("*.pbix"))
        if workers > 1 and len(files) > 1:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for status, payload in [f.result() for f in as_completed(
                        pool.submit(_process, f) for f in files)]:
                    results["success" if status == "ok" else "failed"].append(payload)
        else:
            for pbix_file in files:
                status, payload = _process(pbix_file)
                results["success" if status == "ok" else "failed"].append(payload)

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
        file_size_mb = round(pbix_path.stat().st_size / (1024 * 1024), 1)

        if dry_run:
            strategy = self._select_import_strategy(pbix_path)
            logger.info(
                "[DRY RUN] Would publish %s to workspace %s (strategy=%s, size_mb=%.1f)",
                display_name,
                workspace_id,
                strategy,
                file_size_mb,
            )
            return {
                "name": display_name,
                "status": "dry_run",
                "strategy": strategy,
                "size_mb": file_size_mb,
            }

        strategy = self._select_import_strategy(pbix_path)
        logger.info(
            "Publishing %s to workspace %s (strategy=%s, size_mb=%.1f)",
            display_name,
            workspace_id,
            strategy,
            file_size_mb,
        )

        if strategy == "large":
            self._ensure_large_upload_support()
            try:
                import_result = LargeFileHandler(self.client).upload(
                    workspace_id=workspace_id,
                    file_path=str(pbix_path),
                    display_name=display_name,
                    dry_run=False,
                )
            except Exception as e:
                raise RuntimeError(
                    "Large PBIX upload failed. "
                    "Confirm workspace/tenant import settings and verify enhanced import API access. "
                    f"Original error: {e}"
                ) from e
        else:
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
            "strategy": strategy,
            "size_mb": file_size_mb,
        }

    def _select_import_strategy(self, pbix_path: Path) -> str:
        """Choose import strategy based on file size and feature flags."""
        if not self.enable_large_file_upload:
            return "standard"
        if LargeFileHandler.needs_chunked_upload(
            str(pbix_path), threshold_mb=self.large_file_threshold_mb
        ):
            return "large"
        return "standard"

    def _ensure_large_upload_support(self) -> None:
        """Ensure client has enhanced import methods required by LargeFileHandler."""
        required = ("create_temporary_upload_location", "upload_chunk", "complete_upload")
        missing = [name for name in required if not hasattr(self.client, name)]
        if missing:
            raise RuntimeError(
                "PBI client does not support enhanced large-file import methods: "
                + ", ".join(missing)
            )
