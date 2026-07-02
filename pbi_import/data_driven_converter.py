"""
Data-Driven Subscription Converter — converts PBIRS data-driven subscriptions
to PBI Online alternatives.

PBIRS data-driven subscriptions use a SQL query to generate per-row
subscription parameters (recipient, format, parameters).  PBI Online does not
support data-driven subscriptions natively, so this module generates:

  1. A Power Automate flow definition (via PowerAutomateGenerator)
  2. A parameterised CSV template for manual review
  3. Migration notes documenting what needs manual attention
"""

import csv
import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DataDrivenConverter:
    """Convert PBIRS data-driven subscriptions to PBI Online alternatives."""

    def __init__(self):
        pass

    def convert_all(self, subscriptions: dict) -> dict:
        """Analyse all data-driven subscriptions and produce conversion plans.

        Args:
            subscriptions: Extracted subscription data from PBIRS.

        Returns:
            Dict with ``plans`` (one per data-driven sub), ``summary``.
        """
        subs = subscriptions.get("subscriptions", [])
        data_driven = [s for s in subs if s.get("IsDataDriven")]
        plans: list[dict] = []

        for sub in data_driven:
            plan = self._convert_one(sub)
            plans.append(plan)

        return {
            "plans": plans,
            "summary": {
                "total_data_driven": len(data_driven),
                "converted": len([p for p in plans if p["strategy"] != "manual"]),
                "manual_required": len([p for p in plans if p["strategy"] == "manual"]),
            },
        }

    def save_plans(self, results: dict, output_dir: str) -> list[Path]:
        """Save conversion plans and CSV templates."""
        out = Path(output_dir) / "data_driven_conversions"
        out.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []

        for plan in results.get("plans", []):
            plan_id = plan.get("subscription_id", "unknown")
            safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in plan_id)

            # Save plan JSON
            plan_path = out / f"{safe_id}_plan.json"
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(plan, f, indent=2)
            paths.append(plan_path)

            # Save parameter template CSV
            csv_path = out / f"{safe_id}_parameters.csv"
            self._write_param_template(plan, csv_path)
            paths.append(csv_path)

        # Save summary
        summary_path = out / "_summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(results.get("summary", {}), f, indent=2)
        paths.append(summary_path)

        logger.info("Saved %d data-driven conversion plans to %s", len(results.get("plans", [])), out)
        return paths

    # ------------------------------------------------------------------
    # Conversion logic
    # ------------------------------------------------------------------

    def _convert_one(self, sub: dict) -> dict:
        """Convert a single data-driven subscription."""
        report_path = sub.get("Report", "")
        report_name = report_path.rsplit("/", 1)[-1] if report_path else ""
        delivery = sub.get("DeliveryExtension", "")
        db_meta = sub.get("DbQueryMetadata") or {}
        db_query = db_meta.get("query_text", "") if isinstance(db_meta, dict) else ""
        query = db_query or sub.get("DataDrivenQuery", sub.get("QueryDefinition", ""))
        query_source = "reportserver_db" if db_query else "pbirs_api"

        strategy = self._determine_strategy(sub)

        plan: dict[str, Any] = {
            "subscription_id": sub.get("SubscriptionID", ""),
            "description": sub.get("Description", ""),
            "report_name": report_name,
            "report_path": report_path,
            "delivery_extension": delivery,
            "strategy": strategy,
            "original_query": query,
            "query_source": query_source,
            "query_preview_redacted": self._redact_query(query)[:200],
            "parameter_fields": self._extract_field_mapping(sub),
            "migration_notes": self._generate_notes(sub, strategy),
        }

        if strategy == "power_automate":
            plan["power_automate_hint"] = {
                "trigger": "Recurrence",
                "step_1": "Execute SQL query to get recipient list",
                "step_2": "Apply to each → Export report with row parameters",
                "step_3": f"Send via {delivery}",
            }

        return plan

    @staticmethod
    def _determine_strategy(sub: dict) -> str:
        """Determine the best conversion strategy."""
        delivery = sub.get("DeliveryExtension", "")
        if delivery == "Report Server Email":
            return "power_automate"
        if delivery == "Report Server FileShare":
            return "power_automate"
        return "manual"

    @staticmethod
    def _extract_field_mapping(sub: dict) -> list[dict]:
        """Extract the field-to-parameter mapping from the subscription."""
        fields: list[dict] = []
        for p in sub.get("ParameterValues", []):
            name = p.get("Name", "")
            value = p.get("Value", "")
            field_ref = p.get("FieldReference", "")
            fields.append({
                "parameter_name": name,
                "static_value": value if not field_ref else "",
                "field_reference": field_ref,
                "note": "Maps to query column" if field_ref else "Static value",
            })
        return fields

    @staticmethod
    def _generate_notes(sub: dict, strategy: str) -> list[str]:
        """Generate migration guidance notes."""
        notes: list[str] = []
        if strategy == "power_automate":
            notes.append("Create a Power Automate flow with Recurrence trigger")
            notes.append("Use SQL connector to replicate the data-driven query")
            notes.append("Use 'Apply to each' to loop over query results")
            notes.append("Use 'Export to File for Paginated Reports' action per row")
        elif strategy == "manual":
            notes.append("This subscription requires manual migration")
            notes.append("Review the original query and delivery method")

        query = sub.get("DataDrivenQuery", sub.get("QueryDefinition", ""))
        if query:
            notes.append(f"Original query: {query[:200]}")

        return notes

    @staticmethod
    def _write_param_template(plan: dict, csv_path: Path) -> None:
        """Write a CSV template showing the parameter mapping."""
        fields = plan.get("parameter_fields", [])
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "parameter_name",
                "static_value",
                "field_reference",
                "pbi_mapping",
                "query_source",
                "query_preview_redacted",
                "notes",
            ])
            for field in fields:
                writer.writerow([
                    field.get("parameter_name", ""),
                    field.get("static_value", ""),
                    field.get("field_reference", ""),
                    "",  # pbi_mapping — user fills this
                    plan.get("query_source", ""),
                    plan.get("query_preview_redacted", ""),
                    field.get("note", ""),
                ])

    @staticmethod
    def _redact_query(query: str) -> str:
        """Redact obvious secret patterns before writing query previews."""
        if not query:
            return ""
        out = re.sub(r"(?i)(password|pwd|token|apikey|api_key)\s*[:=]\s*['\"]?[^'\"\s;]+", r"\1=***", query)
        out = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "***@***", out)
        return out
