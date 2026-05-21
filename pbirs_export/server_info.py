"""
Server Info — extracts PBIRS server metadata (version, features, configuration).
"""

import logging
from typing import Any

from pbirs_export.api_client import PBIRSClient

logger = logging.getLogger(__name__)


class ServerInfo:
    """Collect PBIRS server metadata for migration planning."""

    def __init__(self, client: PBIRSClient):
        self.client = client

    def collect(self) -> dict:
        """Collect comprehensive server information."""
        info: dict[str, Any] = {}

        try:
            info["system"] = self.client.get_system_info()
        except Exception as e:
            logger.warning("Could not get system info: %s", e)
            info["system"] = {}

        try:
            info["properties"] = self.client.get_system_properties()
        except Exception as e:
            logger.warning("Could not get system properties: %s", e)
            info["properties"] = {}

        try:
            folders = self.client.list_folders()
            info["folder_count"] = len(folders)
        except Exception:
            info["folder_count"] = 0

        return info
