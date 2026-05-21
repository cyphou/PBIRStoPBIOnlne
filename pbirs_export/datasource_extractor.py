"""
Datasource Extractor — extracts connection strings and datasource metadata from PBIRS.
"""

import logging
from typing import Any

from pbirs_export.api_client import PBIRSClient

logger = logging.getLogger(__name__)


class DatasourceExtractor:
    """Extract datasource connection metadata from PBIRS catalog items."""

    def __init__(self, client: PBIRSClient):
        self.client = client

    def extract_all(self, catalog: dict) -> dict:
        """Extract datasource info for all relevant catalog items."""
        items = catalog.get("items", [])
        datasources: dict[str, Any] = {
            "shared_datasources": [],
            "embedded_datasources": [],
            "connection_summary": {},
        }

        # Shared datasources
        try:
            shared = self.client.list_datasources()
            datasources["shared_datasources"] = shared
            logger.info("Found %d shared datasources", len(shared))
        except Exception as e:
            logger.warning("Could not list shared datasources: %s", e)

        # Embedded datasources from reports
        conn_types: dict[str, int] = {}
        for item in items:
            item_type = item.get("Type", "")
            if item_type not in ("PowerBIReport", "Report"):
                continue

            item_ds = item.get("datasources", [])
            for ds in item_ds:
                ds_type = ds.get("DataSourceType", ds.get("ConnectionString", "Unknown"))
                conn_types[ds_type] = conn_types.get(ds_type, 0) + 1
                datasources["embedded_datasources"].append({
                    "item_name": item.get("Name"),
                    "item_path": item.get("Path"),
                    "item_type": item_type,
                    "datasource": ds,
                })

        datasources["connection_summary"] = conn_types
        logger.info("Found %d embedded datasource references", len(datasources["embedded_datasources"]))
        return datasources
