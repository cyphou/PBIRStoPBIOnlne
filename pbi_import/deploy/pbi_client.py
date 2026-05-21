"""
PBI Client — Power BI REST API wrapper for workspace, report, and dataset operations.
"""

import base64
import json
import logging
import time
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError

logger = logging.getLogger(__name__)

PBI_BASE_URL = "https://api.powerbi.com/v1.0/myorg"


class PBIClient:
    """Thin wrapper around the Power BI REST API."""

    def __init__(self, access_token: str):
        self._token = access_token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, body: bytes | None = None, content_type: str | None = None) -> Any:
        url = f"{PBI_BASE_URL}{path}"
        headers = self._headers()
        if content_type:
            headers["Content-Type"] = content_type

        req = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(req) as resp:
                data = resp.read()
                if data:
                    return json.loads(data)
                return {}
        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            logger.error("PBI API error %s %s: %s %s", method, path, e.code, error_body[:500])
            raise

    # ------------------------------------------------------------------
    # Workspaces (Groups)
    # ------------------------------------------------------------------

    def list_workspaces(self) -> list[dict]:
        return self._request("GET", "/groups").get("value", [])

    def get_workspace_by_name(self, name: str) -> dict | None:
        for ws in self.list_workspaces():
            if ws.get("name") == name:
                return ws
        return None

    def create_workspace(self, name: str, description: str = "") -> dict:
        body = json.dumps({"name": name, "description": description}).encode()
        return self._request("POST", "/groups?workspaceV2=True", body)

    def assign_workspace_to_capacity(self, workspace_id: str, capacity_id: str) -> None:
        body = json.dumps({"capacityId": capacity_id}).encode()
        self._request("POST", f"/groups/{workspace_id}/AssignToCapacity", body)

    def add_workspace_user(self, workspace_id: str, email_or_upn: str, role: str) -> None:
        body = json.dumps({
            "emailAddress": email_or_upn,
            "groupUserAccessRight": role,
        }).encode()
        self._request("POST", f"/groups/{workspace_id}/users", body)

    def list_workspace_users(self, workspace_id: str) -> list[dict]:
        return self._request("GET", f"/groups/{workspace_id}/users").get("value", [])

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    def list_reports(self, workspace_id: str) -> list[dict]:
        return self._request("GET", f"/groups/{workspace_id}/reports").get("value", [])

    def delete_report(self, workspace_id: str, report_id: str) -> None:
        self._request("DELETE", f"/groups/{workspace_id}/reports/{report_id}")

    def import_pbix(
        self,
        workspace_id: str,
        display_name: str,
        file_content: bytes,
        name_conflict: str = "CreateOrOverwrite",
    ) -> dict:
        """Import a .pbix file into a workspace."""
        path = f"/groups/{workspace_id}/imports?datasetDisplayName={display_name}&nameConflict={name_conflict}"
        result = self._request("POST", path, file_content, content_type="application/octet-stream")

        # Poll for import completion
        import_id = result.get("id", "")
        if import_id:
            result = self._poll_import(workspace_id, import_id)

        return result

    def import_rdl(
        self,
        workspace_id: str,
        display_name: str,
        file_content: bytes,
    ) -> dict:
        """Import a paginated report (.rdl) into a workspace."""
        path = f"/groups/{workspace_id}/imports?datasetDisplayName={display_name}&nameConflict=CreateOrOverwrite"
        return self._request("POST", path, file_content, content_type="application/octet-stream")

    def _poll_import(self, workspace_id: str, import_id: str, timeout: int = 300) -> dict:
        """Poll import status until complete."""
        end_time = time.monotonic() + timeout
        while time.monotonic() < end_time:
            result = self._request("GET", f"/groups/{workspace_id}/imports/{import_id}")
            status = result.get("importState", "")
            if status == "Succeeded":
                return result
            if status == "Failed":
                raise RuntimeError(f"Import failed: {result}")
            time.sleep(2)
        raise TimeoutError(f"Import {import_id} did not complete within {timeout}s")

    # ------------------------------------------------------------------
    # Datasets
    # ------------------------------------------------------------------

    def list_datasets(self, workspace_id: str) -> list[dict]:
        return self._request("GET", f"/groups/{workspace_id}/datasets").get("value", [])

    def delete_dataset(self, workspace_id: str, dataset_id: str) -> None:
        self._request("DELETE", f"/groups/{workspace_id}/datasets/{dataset_id}")

    def get_dataset_datasources(self, dataset_id: str) -> list[dict]:
        return self._request("GET", f"/datasets/{dataset_id}/datasources").get("value", [])

    def bind_to_gateway(self, dataset_id: str, gateway_id: str, datasource_ids: list[str] | None = None) -> None:
        body: dict = {"gatewayObjectId": gateway_id}
        if datasource_ids:
            body["datasourceObjectIds"] = datasource_ids
        self._request("POST", f"/datasets/{dataset_id}/Default.BindToGateway", json.dumps(body).encode())

    def bind_paginated_to_gateway(self, report_id: str, gateway_id: str) -> None:
        body = json.dumps({"gatewayObjectId": gateway_id}).encode()
        self._request("POST", f"/reports/{report_id}/Default.BindToGateway", body)

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def update_refresh_schedule(
        self,
        dataset_id: str,
        enabled: bool,
        frequency: str = "Daily",
        time_zone: str = "UTC",
        times: list[str] | None = None,
    ) -> None:
        body = json.dumps({
            "value": {
                "enabled": enabled,
                "notifyOption": "MailOnFailure",
                "localTimeZoneId": time_zone,
                "times": times or ["08:00"],
            }
        }).encode()
        self._request("PATCH", f"/datasets/{dataset_id}/refreshSchedule", body)

    def get_refresh_schedule(self, dataset_id: str) -> dict:
        return self._request("GET", f"/datasets/{dataset_id}/refreshSchedule")

    # ------------------------------------------------------------------
    # Gateways
    # ------------------------------------------------------------------

    def list_gateways(self) -> list[dict]:
        return self._request("GET", "/gateways").get("value", [])

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def create_subscription(
        self,
        report_id: str,
        title: str,
        frequency: str,
        start_time: str,
        emails: list[str],
    ) -> dict:
        body = json.dumps({
            "title": title,
            "frequency": frequency,
            "startDateTime": start_time,
            "users": [{"emailAddress": e} for e in emails],
        }).encode()
        return self._request("POST", f"/reports/{report_id}/subscriptions", body)
