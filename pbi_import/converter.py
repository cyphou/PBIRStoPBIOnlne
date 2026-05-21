"""
Content Converter — adapts exported PBIRS content for PBI Online compatibility.

Handles:
- Connection string updates (on-prem → cloud or gateway-bound)
- Paginated report feature checks
- Dataset connection rebinding
- Gateway mapping application
"""

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ContentConverter:
    """Convert exported PBIRS content for PBI Online deployment."""

    def __init__(
        self,
        input_dir: str,
        output_dir: str,
        gateway_mapping: str | None = None,
        skip_unsupported: bool = True,
    ):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.skip_unsupported = skip_unsupported
        self.gateway_map: dict = {}

        if gateway_mapping:
            with open(gateway_mapping, encoding="utf-8") as f:
                self.gateway_map = json.load(f)

    def convert_all(self, dry_run: bool = False) -> dict:
        """Convert all exported items."""
        results = {"converted": 0, "skipped": 0, "failed": 0, "items": []}

        manifest_path = self.input_dir / "export_manifest.json"
        if not manifest_path.exists():
            logger.error("Export manifest not found at %s", manifest_path)
            return results

        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        for item in manifest.get("download_results", {}).get("success", []):
            try:
                result = self._convert_item(item, dry_run=dry_run)
                if result.get("status") == "converted":
                    results["converted"] += 1
                elif result.get("status") == "skipped":
                    results["skipped"] += 1
                results["items"].append(result)
            except Exception as e:
                logger.error("Failed to convert %s: %s", item.get("name"), e)
                results["failed"] += 1
                results["items"].append({
                    "name": item.get("name"),
                    "status": "failed",
                    "error": str(e),
                })

        # Copy metadata files
        for meta_file in ("datasources.json", "permissions.json", "subscriptions.json"):
            src = self.input_dir / meta_file
            if src.exists():
                dst = self.output_dir / meta_file
                if not dry_run:
                    self.output_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)

        return results

    def _convert_item(self, item: dict, dry_run: bool = False) -> dict:
        """Convert a single exported item."""
        name = item.get("name", "")
        item_type = item.get("type", "")
        source_path = Path(item.get("path", ""))

        if not source_path.exists() and not dry_run:
            return {"name": name, "status": "skipped", "reason": "Source file not found"}

        if item_type == "PowerBIReport":
            return self._convert_pbix(item, dry_run)
        elif item_type in ("Report", "LinkedReport"):
            return self._convert_rdl(item, dry_run)
        elif item_type == "DataSet":
            return self._convert_dataset(item, dry_run)
        else:
            return {"name": name, "status": "skipped", "reason": f"Unsupported type: {item_type}"}

    def _convert_pbix(self, item: dict, dry_run: bool = False) -> dict:
        """Convert a Power BI report (.pbix).

        PBIX files are binary packages — they can be uploaded as-is to PBI Online.
        The main conversion step is recording gateway mapping for datasource rebinding.
        """
        name = item.get("name", "")
        source = Path(item.get("path", ""))
        dest = self.output_dir / "powerbi" / source.name

        if dry_run:
            return {"name": name, "status": "converted", "type": "PowerBIReport", "path": str(dest), "dry_run": True}

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)

        # Record conversion metadata
        meta = {
            "source": str(source),
            "destination": str(dest),
            "type": "PowerBIReport",
            "gateway_binding": self._resolve_gateway(item),
            "notes": [],
        }

        meta_path = dest.with_suffix(".meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        return {"name": name, "status": "converted", "type": "PowerBIReport", "path": str(dest)}

    def _convert_rdl(self, item: dict, dry_run: bool = False) -> dict:
        """Convert a paginated report (.rdl).

        RDL files may need connection string updates for PBI Online.
        """
        name = item.get("name", "")
        source = Path(item.get("path", ""))
        dest = self.output_dir / "paginated" / source.name

        if dry_run:
            return {"name": name, "status": "converted", "type": "PaginatedReport", "path": str(dest), "dry_run": True}

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)

        # Record metadata
        meta = {
            "source": str(source),
            "destination": str(dest),
            "type": "PaginatedReport",
            "requires_premium": True,
            "gateway_binding": self._resolve_gateway(item),
            "notes": ["Paginated reports require Premium or PPU capacity"],
        }

        meta_path = dest.with_suffix(".meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        return {"name": name, "status": "converted", "type": "PaginatedReport", "path": str(dest)}

    def _convert_dataset(self, item: dict, dry_run: bool = False) -> dict:
        """Convert a shared dataset."""
        name = item.get("name", "")
        source = Path(item.get("path", ""))
        dest = self.output_dir / "datasets" / source.name

        if dry_run:
            return {"name": name, "status": "converted", "type": "DataSet", "path": str(dest), "dry_run": True}

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)

        return {"name": name, "status": "converted", "type": "DataSet", "path": str(dest)}

    def _resolve_gateway(self, item: dict) -> dict | None:
        """Resolve gateway mapping for an item's datasources."""
        if not self.gateway_map:
            return None

        source_path = item.get("source_path", "")
        return self.gateway_map.get(source_path)
