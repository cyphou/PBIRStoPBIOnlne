"""
Permission Extractor — extracts SSRS role assignments and security policies from PBIRS.
"""

import logging
from typing import Any

from pbirs_export.api_client import PBIRSClient

logger = logging.getLogger(__name__)


class PermissionExtractor:
    """Extract permission/policy data from PBIRS items."""

    def __init__(self, client: PBIRSClient):
        self.client = client

    def extract_all(self, catalog: dict) -> dict:
        """Extract permissions for all catalog items."""
        items = catalog.get("items", [])
        permissions: dict[str, Any] = {
            "system_policies": [],
            "item_policies": [],
        }

        # System-level policies
        try:
            permissions["system_policies"] = self.client.get_system_policies()
        except Exception as e:
            logger.warning("Could not extract system policies: %s", e)

        # Per-item policies
        for item in items:
            item_id = item.get("Id", "")
            item_name = item.get("Name", "")
            try:
                policies = self.client.get_item_policies(item_id)
                if policies:
                    permissions["item_policies"].append({
                        "item_id": item_id,
                        "item_name": item_name,
                        "item_path": item.get("Path", ""),
                        "item_type": item.get("Type", ""),
                        "policies": policies,
                    })
            except Exception as e:
                logger.debug("Could not get policies for %s: %s", item_name, e)

        logger.info("Extracted permissions for %d items", len(permissions["item_policies"]))
        return permissions
