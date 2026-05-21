"""
Migration Validator — validates post-migration fidelity between PBIRS and PBI Online.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MigrationValidator:
    """Validate migration results by comparing PBIRS catalog with PBI Online workspace."""

    def __init__(self, pbi_client: Any):
        self.client = pbi_client

    def validate(
        self,
        catalog: dict,
        workspace_id: str,
        converted_dir: str,
    ) -> dict:
        """Run post-migration validation."""
        results = {
            "report_count": self._validate_report_count(catalog, workspace_id),
            "datasource_binding": self._validate_datasources(workspace_id),
            "refresh_status": self._validate_refresh(workspace_id),
            "permissions": self._validate_permissions(workspace_id),
            "overall": "PASS",
            "issues": [],
        }

        # Determine overall status
        for key in ("report_count", "datasource_binding", "refresh_status", "permissions"):
            check = results[key]
            if check.get("status") == "FAIL":
                results["overall"] = "FAIL"
                results["issues"].append(f"{key}: {check.get('message', '')}")
            elif check.get("status") == "WARN":
                if results["overall"] != "FAIL":
                    results["overall"] = "WARN"
                results["issues"].append(f"{key}: {check.get('message', '')}")

        return results

    def _validate_report_count(self, catalog: dict, workspace_id: str) -> dict:
        """Validate all migratable reports made it to PBI Online."""
        source_items = catalog.get("items", [])
        source_reports = [
            i for i in source_items
            if i.get("Type") in ("PowerBIReport", "Report", "LinkedReport")
        ]

        try:
            pbi_reports = self.client.list_reports(workspace_id)
        except Exception as e:
            return {"status": "FAIL", "message": f"Could not list PBI Online reports: {e}"}

        source_count = len(source_reports)
        target_count = len(pbi_reports)

        if target_count >= source_count:
            return {"status": "PASS", "message": f"{target_count}/{source_count} reports present"}
        elif target_count > 0:
            return {"status": "WARN", "message": f"{target_count}/{source_count} reports present — some missing"}
        else:
            return {"status": "FAIL", "message": f"0/{source_count} reports found in workspace"}

    def _validate_datasources(self, workspace_id: str) -> dict:
        """Validate datasource bindings are configured."""
        try:
            datasets = self.client.list_datasets(workspace_id)
        except Exception as e:
            return {"status": "FAIL", "message": f"Could not list datasets: {e}"}

        unbound = []
        for ds in datasets:
            ds_id = ds.get("id", "")
            try:
                sources = self.client.get_dataset_datasources(ds_id)
                for src in sources:
                    if not src.get("gatewayId") and not src.get("datasourceId"):
                        unbound.append(ds.get("name", ds_id))
            except Exception:
                pass

        if unbound:
            return {"status": "WARN", "message": f"{len(unbound)} datasets have unbound datasources: {', '.join(unbound[:5])}"}
        return {"status": "PASS", "message": "All datasources bound"}

    def _validate_refresh(self, workspace_id: str) -> dict:
        """Validate refresh schedules are configured."""
        try:
            datasets = self.client.list_datasets(workspace_id)
        except Exception as e:
            return {"status": "FAIL", "message": f"Could not list datasets: {e}"}

        no_schedule = []
        for ds in datasets:
            ds_id = ds.get("id", "")
            try:
                schedule = self.client.get_refresh_schedule(ds_id)
                if not schedule.get("enabled"):
                    no_schedule.append(ds.get("name", ds_id))
            except Exception:
                no_schedule.append(ds.get("name", ds_id))

        if no_schedule:
            return {"status": "WARN", "message": f"{len(no_schedule)} datasets lack refresh schedules"}
        return {"status": "PASS", "message": "All refresh schedules configured"}

    def _validate_permissions(self, workspace_id: str) -> dict:
        """Validate workspace permissions are configured."""
        try:
            users = self.client.list_workspace_users(workspace_id)
        except Exception as e:
            return {"status": "FAIL", "message": f"Could not list workspace users: {e}"}

        if len(users) <= 1:
            return {"status": "WARN", "message": "Only 1 user in workspace — review permission mapping"}
        return {"status": "PASS", "message": f"{len(users)} users configured"}
