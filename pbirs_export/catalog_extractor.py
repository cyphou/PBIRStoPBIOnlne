"""
Catalog Extractor — builds a complete inventory of PBIRS content.

Extracts folders, reports (Power BI + paginated), datasets, KPIs,
and enriches each item with datasource, subscription, and permission metadata.
"""

import logging
import re
from typing import Any

from pbirs_export.api_client import PBIRSClient

logger = logging.getLogger(__name__)


class CatalogExtractor:
    """Extract and organize the full PBIRS catalog."""

    # Map PBIRS type names to content type filter names
    TYPE_MAP = {
        "PowerBIReport": "powerbi",
        "Report": "paginated",
        "LinkedReport": "paginated",
        "DataSet": "dataset",
        "Kpi": "kpi",
        "MobileReport": "mobile",
        "DataSource": "datasource",
        "Folder": "folder",
    }

    def __init__(self, client: PBIRSClient):
        self.client = client

    def extract_catalog(
        self,
        folder: str | None = None,
        content_types: list[str] | None = None,
        include_pattern: str | None = None,
        exclude_pattern: str | None = None,
    ) -> dict:
        """Extract full catalog inventory from PBIRS."""
        logger.info("Extracting PBIRS catalog...")

        # Fetch all catalog items
        items = self.client.list_catalog_items(folder=folder)
        logger.info("Found %d catalog items", len(items))

        # Filter by content types
        if content_types and "all" not in content_types:
            items = [
                i for i in items
                if self.TYPE_MAP.get(i.get("Type", ""), "other") in content_types
            ]

        # Apply include/exclude patterns
        if include_pattern:
            pattern = re.compile(include_pattern, re.IGNORECASE)
            items = [i for i in items if pattern.search(i.get("Name", ""))]

        if exclude_pattern:
            pattern = re.compile(exclude_pattern, re.IGNORECASE)
            items = [i for i in items if not pattern.search(i.get("Name", ""))]

        # Enrich items with metadata
        enriched = []
        for item in items:
            enriched_item = self._enrich_item(item)
            enriched.append(enriched_item)

        # Build folder tree
        folders = self._build_folder_tree(enriched)

        # Server info
        try:
            server_info = self.client.get_system_info()
        except Exception:
            server_info = {}

        return {
            "server_info": server_info,
            "items": enriched,
            "folders": folders,
            "total_count": len(enriched),
        }

    def _enrich_item(self, item: dict) -> dict:
        """Enrich a catalog item with additional metadata."""
        item_id = item.get("Id", "")
        item_type = item.get("Type", "")

        # Get datasources for reports
        if item_type in ("PowerBIReport", "Report"):
            try:
                if item_type == "PowerBIReport":
                    item["datasources"] = self.client.get_powerbi_report_datasources(item_id)
                else:
                    item["datasources"] = self.client.get_report_datasources(item_id)
            except Exception as e:
                logger.debug("Could not get datasources for %s: %s", item.get("Name"), e)
                item["datasources"] = []

        # Get parameters for paginated reports
        if item_type == "Report":
            try:
                item["parameters"] = self.client.get_report_parameters(item_id)
            except Exception as e:
                logger.debug("Could not get parameters for %s: %s", item.get("Name"), e)
                item["parameters"] = []

        # Get policies
        try:
            item["policies"] = self.client.get_item_policies(item_id)
        except Exception as e:
            logger.debug("Could not get policies for %s: %s", item.get("Name"), e)
            item["policies"] = []

        # Get subscriptions
        try:
            all_subs = self.client.list_subscriptions()
            item["subscriptions"] = [
                s for s in all_subs
                if s.get("Report", "") == item.get("Path", "")
            ]
        except Exception:
            item["subscriptions"] = []

        # Get cache refresh plans
        try:
            item["cache_refresh_plans"] = self.client.list_cache_refresh_plans(item_id)
        except Exception:
            item["cache_refresh_plans"] = []

        return item

    def _build_folder_tree(self, items: list[dict]) -> list[dict]:
        """Build a folder hierarchy from flat item list."""
        folders: dict[str, dict] = {}
        for item in items:
            path = item.get("Path", "/")
            parts = path.rsplit("/", 1)
            parent_path = parts[0] if len(parts) > 1 else "/"
            if parent_path not in folders:
                folders[parent_path] = {"path": parent_path, "items": [], "children": []}
            folders[parent_path]["items"].append({
                "name": item.get("Name", ""),
                "type": item.get("Type", ""),
                "id": item.get("Id", ""),
            })

        return list(folders.values())
