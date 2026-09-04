"""
Catalog Extractor — builds a complete inventory of PBIRS content.

Extracts folders, reports (Power BI + paginated), datasets, KPIs,
and enriches each item with datasource, subscription, and permission metadata.
"""

import logging
import re
import xml.etree.ElementTree as ET
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
        self._shared_datasources: list[dict] | None = None

    def extract_catalog(
        self,
        folder: str | None = None,
        content_types: list[str] | None = None,
        include_pattern: str | None = None,
        exclude_pattern: str | None = None,
        batch_size: int = 15,
    ) -> dict:
        """Extract full catalog inventory from PBIRS."""
        logger.info("Extracting PBIRS catalog...")
        if batch_size < 1:
            raise ValueError("batch_size must be greater than zero")

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

        # Fetch shared subscriptions once instead of once per catalog item.
        try:
            subscriptions = self.client.list_subscriptions()
        except Exception as e:
            logger.debug("Could not list subscriptions: %s", e)
            subscriptions = []

        # Enrich items sequentially in bounded batches to avoid request bursts.
        enriched = []
        for batch_start in range(0, len(items), batch_size):
            batch = items[batch_start:batch_start + batch_size]
            logger.info(
                "Enriching catalog batch %d (%d items, max batch size %d)",
                batch_start // batch_size + 1,
                len(batch),
                batch_size,
            )
            enriched.extend(
                self._enrich_item(item, subscriptions=subscriptions)
                for item in batch
            )

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

    def _enrich_item(self, item: dict, subscriptions: list[dict] | None = None) -> dict:
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
                    if not item["datasources"] or any(
                        not str(ds.get("ConnectionString") or "").strip()
                        for ds in item["datasources"]
                        if isinstance(ds, dict)
                    ):
                        item["datasources"] = self._merge_datasources(
                            item["datasources"],
                            self._extract_rdl_datasources(item_id),
                        )
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
            details_getter = getattr(self.client, "get_item_policy_details", None)
            details = details_getter(item_id) if callable(details_getter) else None
            if isinstance(details, dict):
                item["policies"] = details.get("policies", [])
                item["inherit_parent_policy"] = details.get("inherit_parent_policy")
            else:
                item["policies"] = self.client.get_item_policies(item_id)
        except Exception as e:
            logger.debug("Could not get policies for %s: %s", item.get("Name"), e)
            item["policies"] = []

        # Get subscriptions
        try:
            all_subs = subscriptions
            if all_subs is None:
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

    def _extract_rdl_datasources(self, report_id: str) -> list[dict]:
        """Read RDL connection details when the REST metadata is incomplete."""
        try:
            raw = self.client.download_report(report_id)
            root = ET.fromstring(raw)
        except Exception as e:
            logger.debug("Could not inspect RDL datasource content for %s: %s", report_id, e)
            return []

        shared = self._get_shared_datasources()
        shared_by_key: dict[str, dict] = {}
        for datasource in shared:
            for key in (datasource.get("Path"), datasource.get("Name"), datasource.get("Id")):
                if key:
                    shared_by_key[str(key).rstrip("/").casefold()] = datasource

        extracted: list[dict] = []
        for element in root.iter():
            if self._local_name(element.tag) != "DataSource":
                continue
            name = element.attrib.get("Name", "")
            connection = ""
            provider = ""
            reference = ""
            for child in element.iter():
                child_name = self._local_name(child.tag)
                if child_name == "ConnectString":
                    connection = child.text or ""
                elif child_name == "DataProvider":
                    provider = child.text or ""
                elif child_name == "DataSourceReference":
                    reference = child.text or ""

            shared_match = shared_by_key.get(reference.rstrip("/").casefold()) if reference else None
            if shared_match:
                connection = shared_match.get("ConnectionString") or connection
                provider = shared_match.get("DataSourceType") or shared_match.get("Type") or provider

            extracted.append({
                "Name": name,
                "DataSourceType": provider,
                "ConnectionString": connection,
                "DataSourceReference": reference,
            })
        return extracted

    @staticmethod
    def _merge_datasources(api_datasources: list[dict], rdl_datasources: list[dict]) -> list[dict]:
        """Fill incomplete API datasource rows with RDL-derived connection details."""
        by_name = {
            str(ds.get("Name") or "").casefold(): ds
            for ds in rdl_datasources
            if isinstance(ds, dict) and ds.get("Name")
        }
        merged: list[dict] = []
        for api_ds in api_datasources:
            if not isinstance(api_ds, dict):
                continue
            rdl_ds = by_name.get(str(api_ds.get("Name") or "").casefold(), {})
            combined = dict(api_ds)
            for key in ("DataSourceType", "ConnectionString", "DataSourceReference"):
                if not str(combined.get(key) or "").strip() and rdl_ds.get(key):
                    combined[key] = rdl_ds[key]
            merged.append(combined)
            by_name.pop(str(api_ds.get("Name") or "").casefold(), None)
        merged.extend(by_name.values())
        return merged

    def _get_shared_datasources(self) -> list[dict]:
        if self._shared_datasources is None:
            try:
                self._shared_datasources = self.client.list_datasources()
            except Exception as e:
                logger.debug("Could not list shared datasources for RDL resolution: %s", e)
                self._shared_datasources = []
        return self._shared_datasources

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

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
