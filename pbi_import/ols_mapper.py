"""
OLS Mapper — maps Object-Level Security from SSRS hidden fields/columns.

Detects fields marked as hidden or restricted in PBIRS reports and generates
OLS role definitions for PBI Online datasets.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class OLSMapper:
    """Map PBIRS hidden/restricted fields to PBI Object-Level Security."""

    def __init__(self, rdl_analyses: list[dict] | None = None):
        self.analyses = rdl_analyses or []

    def detect_hidden_fields(self, catalog: list[dict]) -> list[dict]:
        """Detect hidden or restricted fields across catalog items.

        Inspects RDL analysis results for hidden columns, toggled visibility
        expressions, and restricted dataset fields.
        """
        findings: list[dict] = []

        for item in catalog:
            name = item.get("Name", "")
            rdl_data = self._find_rdl_analysis(name)
            if not rdl_data:
                continue

            hidden = []
            # Fields with visibility toggles
            for field in rdl_data.get("hidden_fields", []):
                hidden.append({
                    "field": field.get("name", ""),
                    "table": field.get("table", ""),
                    "reason": "visibility_toggle",
                })

            # Columns with Hidden="true" attribute
            for col in rdl_data.get("hidden_columns", []):
                hidden.append({
                    "field": col.get("name", ""),
                    "table": col.get("dataset", ""),
                    "reason": "hidden_attribute",
                })

            if hidden:
                findings.append({
                    "report_name": name,
                    "report_path": item.get("Path", ""),
                    "hidden_fields": hidden,
                })

        logger.info("OLS scan: %d reports with hidden fields", len(findings))
        return findings

    def generate_ols_roles(self, findings: list[dict]) -> dict:
        """Generate OLS role definitions from hidden field findings.

        Returns OLS roles that restrict column visibility per table.
        """
        # Aggregate: table.column → set of reports using it
        field_usage: dict[str, set[str]] = {}
        for finding in findings:
            for field in finding.get("hidden_fields", []):
                key = f"{field['table']}.{field['field']}"
                field_usage.setdefault(key, set()).add(finding["report_name"])

        roles: list[dict] = []
        # Group by table
        table_fields: dict[str, list[str]] = {}
        for key in field_usage:
            table, field = key.rsplit(".", 1)
            table_fields.setdefault(table, []).append(field)

        for table, fields in table_fields.items():
            roles.append({
                "role_name": f"OLS_{table}_Restricted",
                "table": table,
                "restricted_columns": fields,
                "ols_permission": "None",  # None = hidden, Read = visible
            })

        result = {
            "roles": roles,
            "summary": {
                "total_roles": len(roles),
                "total_restricted_columns": sum(len(r["restricted_columns"]) for r in roles),
                "tables_affected": len(table_fields),
            },
        }

        logger.info("Generated %d OLS roles", len(roles))
        return result

    def save(self, output_dir: str, ols_plan: dict) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "ols_definitions.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(ols_plan, f, indent=2)
        logger.info("OLS definitions saved to %s", path)
        return path

    def _find_rdl_analysis(self, name: str) -> dict | None:
        for a in self.analyses:
            if a.get("report_name") == name or a.get("Name") == name:
                return a
        return None
