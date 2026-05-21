"""
Fabric Client — Microsoft Fabric REST API wrapper for workspace and lakehouse operations.
"""

import json
import logging
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError

logger = logging.getLogger(__name__)

FABRIC_BASE_URL = "https://api.fabric.microsoft.com/v1"


class FabricClient:
    """Thin wrapper around the Microsoft Fabric REST API."""

    def __init__(self, access_token: str):
        self._token = access_token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, body: bytes | None = None) -> Any:
        url = f"{FABRIC_BASE_URL}{path}"
        req = Request(url, data=body, headers=self._headers(), method=method)
        try:
            with urlopen(req) as resp:
                data = resp.read()
                if data:
                    return json.loads(data)
                return {}
        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            logger.error("Fabric API error %s %s: %s %s", method, path, e.code, error_body[:500])
            raise

    def list_workspaces(self) -> list[dict]:
        return self._request("GET", "/workspaces").get("value", [])

    def create_workspace(self, display_name: str, description: str = "") -> dict:
        body = json.dumps({"displayName": display_name, "description": description}).encode()
        return self._request("POST", "/workspaces", body)

    def list_items(self, workspace_id: str, item_type: str | None = None) -> list[dict]:
        path = f"/workspaces/{workspace_id}/items"
        if item_type:
            path += f"?type={item_type}"
        return self._request("GET", path).get("value", [])
