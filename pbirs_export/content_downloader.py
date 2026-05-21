"""
Content Downloader — downloads PBIRS report/dataset files to local disk.

Supports parallel downloads via ThreadPoolExecutor and displays a progress bar.
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from pbirs_export.api_client import PBIRSClient
from pbirs_export.checkpoint import CheckpointManager
from pbirs_export.progress import ProgressReporter

logger = logging.getLogger(__name__)


class ContentDownloader:
    """Download PBIRS content files (pbix, rdl, rds) to local directory."""

    # Map item types to file extensions
    EXTENSION_MAP = {
        "PowerBIReport": ".pbix",
        "Report": ".rdl",
        "LinkedReport": ".rdl",
        "DataSet": ".rsd",
        "DataSource": ".rds",
    }

    DEFAULT_WORKERS = 4

    def __init__(self, client: PBIRSClient, output_dir: str, workers: int | None = None):
        self.client = client
        self.output_dir = Path(output_dir)
        self.workers = workers or self.DEFAULT_WORKERS
        self.checkpoint = CheckpointManager(output_dir)

    def download_all(
        self,
        catalog: dict,
        dry_run: bool = False,
        show_progress: bool = True,
    ) -> dict:
        """Download all downloadable items from catalog.

        Args:
            catalog: Extracted catalog dict with ``items`` list.
            dry_run: If True, log what would be downloaded without fetching.
            show_progress: If True, display a console progress bar.
        """
        items = catalog.get("items", [])
        results: dict[str, list] = {"success": [], "failed": [], "skipped": []}

        # Separate downloadable from non-downloadable, skip already-done
        downloadable: list[dict] = []
        for item in items:
            item_type = item.get("Type", "")
            item_id = item.get("Id", "")
            if item_type not in self.EXTENSION_MAP:
                results["skipped"].append({
                    "name": item.get("Name"),
                    "type": item_type,
                    "reason": "Not a downloadable type",
                })
            elif self.checkpoint.is_done(item_id) and not dry_run:
                results["skipped"].append({
                    "name": item.get("Name"),
                    "type": item_type,
                    "reason": "Already downloaded (resume)",
                })
            else:
                downloadable.append(item)

        if not downloadable:
            return results

        if dry_run or self.workers <= 1:
            # Sequential download (dry-run always sequential for stable output)
            self._download_sequential(downloadable, results, dry_run, show_progress)
        else:
            self._download_parallel(downloadable, results, show_progress)

        return results

    # ------------------------------------------------------------------
    # Sequential path
    # ------------------------------------------------------------------

    def _download_sequential(
        self,
        items: list[dict],
        results: dict[str, list],
        dry_run: bool,
        show_progress: bool,
    ) -> None:
        progress = ProgressReporter(total=len(items), label="Downloading") if show_progress else None
        if progress:
            progress.start()

        for item in items:
            try:
                result = self._download_item(item, dry_run=dry_run)
                results["success"].append(result)
                if not dry_run:
                    self.checkpoint.mark_done(item.get("Id", ""), {"name": item.get("Name")})
            except Exception as e:
                logger.error("Failed to download %s: %s", item.get("Name"), e)
                results["failed"].append({
                    "name": item.get("Name"),
                    "type": item.get("Type", ""),
                    "error": str(e),
                })
                self.checkpoint.mark_failed(item.get("Id", ""), str(e))
            finally:
                if progress:
                    progress.advance()

        if progress:
            progress.finish()

    # ------------------------------------------------------------------
    # Parallel path
    # ------------------------------------------------------------------

    def _download_parallel(
        self,
        items: list[dict],
        results: dict[str, list],
        show_progress: bool,
    ) -> None:
        logger.info("Downloading %d items with %d workers", len(items), self.workers)
        progress = ProgressReporter(total=len(items), label="Downloading") if show_progress else None
        if progress:
            progress.start()

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {
                executor.submit(self._download_item, item): item
                for item in items
            }
            for future in as_completed(futures):
                item = futures[future]
                try:
                    result = future.result()
                    results["success"].append(result)
                    self.checkpoint.mark_done(item.get("Id", ""), {"name": item.get("Name")})
                except Exception as e:
                    logger.error("Failed to download %s: %s", item.get("Name"), e)
                    results["failed"].append({
                        "name": item.get("Name"),
                        "type": item.get("Type", ""),
                        "error": str(e),
                    })
                    self.checkpoint.mark_failed(item.get("Id", ""), str(e))
                finally:
                    if progress:
                        progress.advance()

        if progress:
            progress.finish()

    def _download_item(self, item: dict, dry_run: bool = False) -> dict:
        """Download a single item."""
        item_id = item.get("Id", "")
        item_name = item.get("Name", "unknown")
        item_type = item.get("Type", "")
        item_path = item.get("Path", "/")
        ext = self.EXTENSION_MAP.get(item_type, "")

        # Build local path preserving folder structure
        relative_path = item_path.lstrip("/")
        local_dir = self.output_dir / os.path.dirname(relative_path)
        safe_name = self._sanitize_filename(item_name)
        local_path = local_dir / f"{safe_name}{ext}"

        if dry_run:
            logger.info("[DRY RUN] Would download %s → %s", item_name, local_path)
            return {"name": item_name, "path": str(local_path), "dry_run": True}

        local_dir.mkdir(parents=True, exist_ok=True)

        # Download based on type
        if item_type == "PowerBIReport":
            content = self.client.download_powerbi_report(item_id)
        elif item_type in ("Report", "LinkedReport"):
            content = self.client.download_report(item_id)
        elif item_type == "DataSet":
            content = self.client.download_dataset(item_id)
        else:
            content = self.client.get_catalog_item_content(item_id)

        with open(local_path, "wb") as f:
            f.write(content)

        size = len(content)
        logger.info("Downloaded %s (%s, %d bytes) → %s", item_name, item_type, size, local_path)

        return {
            "name": item_name,
            "type": item_type,
            "path": str(local_path),
            "size": size,
            "source_path": item_path,
        }

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """Sanitize a filename by removing/replacing invalid characters."""
        # Replace invalid filename characters
        invalid_chars = '<>:"/\\|?*'
        for ch in invalid_chars:
            name = name.replace(ch, "_")
        # Remove null bytes
        name = name.replace("\x00", "")
        return name.strip(". ")
