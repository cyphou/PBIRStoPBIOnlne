"""
Power Automate Flow Generator — converts PBIRS subscriptions into
Power Automate flow definitions.

Generates JSON flow definitions that can be imported into Power Automate
via the Management API or the portal.  Covers email, file-share, and
data-driven subscription patterns.
"""

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PowerAutomateGenerator:
    """Generate Power Automate flow definitions from PBIRS subscription data."""

    def __init__(self, tenant_id: str = "", environment_id: str = ""):
        self.tenant_id = tenant_id
        self.environment_id = environment_id

    def generate_flows(
        self,
        subscriptions: dict,
        published_items: dict | None = None,
    ) -> dict:
        """Convert PBIRS subscriptions to Power Automate flow definitions.

        Args:
            subscriptions: Extracted subscription data from PBIRS.
            published_items: Optional map of source path → published PBI item.

        Returns:
            Dict with ``flows``, ``skipped``, and summary.
        """
        subs = subscriptions.get("subscriptions", [])
        results: dict[str, Any] = {"flows": [], "skipped": [], "summary": {}}

        for sub in subs:
            delivery = sub.get("DeliveryExtension", "")
            if delivery == "Report Server Email":
                flow = self._email_flow(sub, published_items)
                results["flows"].append(flow)
            elif delivery == "Report Server FileShare":
                flow = self._fileshare_flow(sub, published_items)
                results["flows"].append(flow)
            elif sub.get("IsDataDriven"):
                flow = self._data_driven_flow(sub, published_items)
                results["flows"].append(flow)
            else:
                results["skipped"].append({
                    "description": sub.get("Description", ""),
                    "delivery": delivery,
                    "reason": f"Unsupported delivery: {delivery}",
                })

        results["summary"] = {
            "total_subscriptions": len(subs),
            "flows_generated": len(results["flows"]),
            "skipped": len(results["skipped"]),
        }
        return results

    def save_flows(self, results: dict, output_dir: str) -> list[Path]:
        """Save generated flows as individual JSON files."""
        out = Path(output_dir) / "power_automate_flows"
        out.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []

        for i, flow in enumerate(results.get("flows", []), 1):
            name = flow.get("display_name", f"flow_{i}")
            safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name)
            path = out / f"{safe}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(flow, f, indent=2)
            paths.append(path)

        # Save summary
        summary_path = out / "_summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(results.get("summary", {}), f, indent=2)
        paths.append(summary_path)

        logger.info("Saved %d Power Automate flow definitions to %s", len(results.get("flows", [])), out)
        return paths

    # ------------------------------------------------------------------
    # Flow generators
    # ------------------------------------------------------------------

    def _email_flow(self, sub: dict, published: dict | None) -> dict:
        """Generate a Recurrence → Export → Email flow."""
        schedule = self._map_schedule(sub.get("Schedule", {}))
        recipients = self._extract_recipients(sub)
        report_name = sub.get("Report", "").rsplit("/", 1)[-1]
        description = sub.get("Description", f"Auto-migrated: {report_name}")

        return {
            "flow_id": str(uuid.uuid4()),
            "display_name": f"Email - {report_name}",
            "description": description,
            "source_subscription": sub.get("SubscriptionID", ""),
            "trigger": {
                "type": "Recurrence",
                "frequency": schedule.get("frequency", "Day"),
                "interval": schedule.get("interval", 1),
                "start_time": schedule.get("start_time", "08:00"),
            },
            "actions": [
                {
                    "type": "ExportToFile",
                    "report_name": report_name,
                    "format": self._map_render_format(sub),
                    "published_report_id": self._find_published_id(sub, published),
                },
                {
                    "type": "SendEmail",
                    "to": recipients,
                    "subject": description,
                    "body": f"Automated report delivery: {report_name}",
                    "include_attachment": True,
                },
            ],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def _fileshare_flow(self, sub: dict, published: dict | None) -> dict:
        """Generate a Recurrence → Export → SharePoint/OneDrive flow."""
        schedule = self._map_schedule(sub.get("Schedule", {}))
        report_name = sub.get("Report", "").rsplit("/", 1)[-1]
        file_path = self._extract_param(sub, "PATH", "")
        file_name = self._extract_param(sub, "FILENAME", report_name)

        return {
            "flow_id": str(uuid.uuid4()),
            "display_name": f"FileShare - {report_name}",
            "description": sub.get("Description", f"File delivery: {report_name}"),
            "source_subscription": sub.get("SubscriptionID", ""),
            "trigger": {
                "type": "Recurrence",
                "frequency": schedule.get("frequency", "Day"),
                "interval": schedule.get("interval", 1),
                "start_time": schedule.get("start_time", "08:00"),
            },
            "actions": [
                {
                    "type": "ExportToFile",
                    "report_name": report_name,
                    "format": self._map_render_format(sub),
                    "published_report_id": self._find_published_id(sub, published),
                },
                {
                    "type": "CreateFile_SharePoint",
                    "site_url": "(TO FILL — SharePoint site URL)",
                    "folder_path": file_path or "(TO FILL — target folder)",
                    "file_name": file_name,
                    "note": "Original file share path was on-prem; map to SharePoint/OneDrive",
                },
            ],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def _data_driven_flow(self, sub: dict, published: dict | None) -> dict:
        """Generate a flow stub for data-driven subscriptions."""
        report_name = sub.get("Report", "").rsplit("/", 1)[-1]

        return {
            "flow_id": str(uuid.uuid4()),
            "display_name": f"DataDriven - {report_name}",
            "description": sub.get("Description", f"Data-driven: {report_name}"),
            "source_subscription": sub.get("SubscriptionID", ""),
            "data_driven": True,
            "trigger": {
                "type": "Recurrence",
                "frequency": "Day",
                "interval": 1,
                "note": "Review original data-driven query and adapt",
            },
            "actions": [
                {
                    "type": "SQL_GetRows",
                    "note": "(TO FILL — replicate the data-driven query)",
                    "original_query_hint": sub.get("DataDrivenQuery", ""),
                },
                {
                    "type": "Apply_to_each",
                    "actions": [
                        {
                            "type": "ExportToFile",
                            "report_name": report_name,
                            "format": self._map_render_format(sub),
                            "parameters": "(TO FILL — map query columns to report params)",
                        },
                        {
                            "type": "SendEmail",
                            "to": "(TO FILL — from query column)",
                            "subject": sub.get("Description", report_name),
                        },
                    ],
                },
            ],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _map_schedule(ssrs_schedule: dict) -> dict:
        """Map SSRS recurrence to Power Automate frequency."""
        pattern = ssrs_schedule.get("RecurrencePattern", "")
        start = ssrs_schedule.get("StartDateTime", "08:00")
        if isinstance(start, str) and "T" in start:
            start = start.split("T")[1][:5]

        if "Daily" in pattern:
            return {"frequency": "Day", "interval": 1, "start_time": start}
        if "Weekly" in pattern:
            return {"frequency": "Week", "interval": 1, "start_time": start}
        if "Monthly" in pattern:
            return {"frequency": "Month", "interval": 1, "start_time": start}
        return {"frequency": "Day", "interval": 1, "start_time": start}

    @staticmethod
    def _extract_recipients(sub: dict) -> list[str]:
        params = sub.get("ParameterValues", [])
        for p in params:
            if p.get("Name") == "TO":
                return [e.strip() for e in p.get("Value", "").split(";") if e.strip()]
        return []

    @staticmethod
    def _extract_param(sub: dict, name: str, default: str = "") -> str:
        for p in sub.get("ParameterValues", []):
            if p.get("Name") == name:
                return p.get("Value", default)
        return default

    @staticmethod
    def _map_render_format(sub: dict) -> str:
        fmt = ""
        for p in sub.get("ParameterValues", []):
            if p.get("Name") == "RENDER_FORMAT":
                fmt = p.get("Value", "")
                break
        mapping = {
            "PDF": "PDF",
            "EXCELOPENXML": "XLSX",
            "WORDOPENXML": "DOCX",
            "CSV": "CSV",
            "IMAGE": "PNG",
            "PPTX": "PPTX",
            "MHTML": "MHTML",
        }
        return mapping.get(fmt.upper(), fmt or "PDF")

    @staticmethod
    def _find_published_id(sub: dict, published: dict | None) -> str:
        if not published:
            return "(TO FILL — published report ID)"
        report_path = sub.get("Report", "")
        item = published.get(report_path, {})
        return item.get("report_id", "(TO FILL — published report ID)")
