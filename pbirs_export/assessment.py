"""
Migration Readiness Assessment.

Scores PBIRS content across 9 categories to determine migration readiness
and generate migration wave plans.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Score thresholds
GREEN = "GREEN"
YELLOW = "YELLOW"
RED = "RED"


class MigrationAssessment:
    """Assess PBIRS content for PBI Online migration readiness."""

    # Content types that require Premium/PPU capacity
    PREMIUM_REQUIRED_TYPES = {"Report", "LinkedReport"}  # Paginated reports

    # SSRS features not fully supported in PBI Online paginated reports
    UNSUPPORTED_RDL_FEATURES = {
        "CustomCode",
        "CustomAssembly",
        "EmbeddedCode",
        "DataDrivenSubscription",
        "FileShareDelivery",
    }

    # Mobile reports are deprecated
    DEPRECATED_TYPES = {"MobileReport"}

    def assess(self, catalog: dict) -> dict:
        """Run full assessment on a PBIRS catalog inventory."""
        items = catalog.get("items", [])
        if not items:
            return self._empty_report()

        assessed_items = []
        for item in items:
            assessed = self._assess_item(item)
            assessed_items.append(assessed)

        summary = self._compute_summary(assessed_items)
        waves = self._plan_migration_waves(assessed_items)

        return {
            "summary": summary,
            "items": assessed_items,
            "waves": waves,
            "recommendations": self._generate_recommendations(summary, assessed_items),
        }

    def _assess_item(self, item: dict) -> dict:
        """Assess a single catalog item across 9 categories."""
        scores: dict[str, dict] = {}
        item_type = item.get("Type", "Unknown")

        scores["datasource_compatibility"] = self._score_datasource(item)
        scores["report_complexity"] = self._score_complexity(item)
        scores["security_model"] = self._score_security(item)
        scores["gateway_requirements"] = self._score_gateway(item)
        scores["paginated_features"] = self._score_paginated(item)
        scores["subscription_migration"] = self._score_subscriptions(item)
        scores["capacity_requirements"] = self._score_capacity(item)
        scores["data_model"] = self._score_data_model(item)
        scores["custom_visuals"] = self._score_custom_visuals(item)

        overall = self._compute_overall_score(scores)

        return {
            "id": item.get("Id", ""),
            "name": item.get("Name", ""),
            "path": item.get("Path", ""),
            "type": item_type,
            "scores": scores,
            "overall": overall,
            "notes": self._generate_item_notes(item, scores),
        }

    # ------------------------------------------------------------------
    # Category scoring
    # ------------------------------------------------------------------

    def _score_datasource(self, item: dict) -> dict:
        """Score datasource compatibility."""
        datasources = item.get("datasources", [])
        if not datasources:
            return {"score": GREEN, "details": "No datasources to evaluate"}

        issues = []
        for ds in datasources:
            conn_type = ds.get("ConnectionString", "") or ds.get("DataSourceType", "")
            # Check for on-prem only connection types
            if any(k in conn_type.lower() for k in ("file://", "\\\\", "localhost", "127.0.0.1")):
                issues.append(f"Local/file-based connection: {conn_type[:80]}")

        if issues:
            return {"score": RED, "details": "; ".join(issues)}
        return {"score": GREEN, "details": "All datasources compatible"}

    def _score_complexity(self, item: dict) -> dict:
        """Score report complexity."""
        item_type = item.get("Type", "")
        if item_type not in ("PowerBIReport", "Report"):
            return {"score": GREEN, "details": "N/A — not a report"}

        # Use metadata hints if available
        page_count = item.get("page_count", 0)
        visual_count = item.get("visual_count", 0)

        if page_count > 50 or visual_count > 200:
            return {"score": RED, "details": f"{page_count} pages, {visual_count} visuals — high complexity"}
        if page_count > 20 or visual_count > 80:
            return {"score": YELLOW, "details": f"{page_count} pages, {visual_count} visuals — moderate complexity"}
        return {"score": GREEN, "details": f"{page_count} pages, {visual_count} visuals"}

    def _score_security(self, item: dict) -> dict:
        """Score security model migration complexity."""
        policies = item.get("policies", [])
        if not policies:
            return {"score": GREEN, "details": "No custom permissions"}

        has_custom_roles = any(
            p.get("Roles", []) for p in policies
            if any(r.get("Name", "") not in ("Browser", "Content Manager") for r in p.get("Roles", []))
        )

        if has_custom_roles:
            return {"score": YELLOW, "details": "Custom SSRS roles — require manual mapping to workspace roles"}
        return {"score": GREEN, "details": "Standard roles"}

    def _score_gateway(self, item: dict) -> dict:
        """Score gateway requirements."""
        datasources = item.get("datasources", [])
        needs_gateway = False
        for ds in datasources:
            conn = ds.get("ConnectionString", "") or ""
            # On-prem SQL Server, Oracle, etc. need gateway
            if any(k in conn.lower() for k in ("data source=", "server=", "host=")):
                if not any(cloud in conn.lower() for cloud in (
                    ".database.windows.net", ".sql.azuresynapse.net",
                    ".blob.core.windows.net", ".dfs.core.windows.net",
                    ".sharepoint.com", ".onmicrosoft.com",
                )):
                    needs_gateway = True

        if needs_gateway:
            return {"score": YELLOW, "details": "On-premises data gateway required"}
        return {"score": GREEN, "details": "Cloud-native or no gateway needed"}

    def _score_paginated(self, item: dict) -> dict:
        """Score paginated report feature compatibility."""
        if item.get("Type") != "Report":
            return {"score": GREEN, "details": "N/A — not a paginated report"}

        rdl_features = item.get("rdl_features", set())
        if not isinstance(rdl_features, set):
            rdl_features = set(rdl_features)
        unsupported = rdl_features & self.UNSUPPORTED_RDL_FEATURES

        if unsupported:
            return {"score": RED, "details": f"Unsupported RDL features: {', '.join(unsupported)}"}
        return {"score": GREEN, "details": "RDL features compatible"}

    def _score_subscriptions(self, item: dict) -> dict:
        """Score subscription migration complexity."""
        subs = item.get("subscriptions", [])
        if not subs:
            return {"score": GREEN, "details": "No subscriptions"}

        file_share_subs = [s for s in subs if s.get("DeliveryExtension") == "Report Server FileShare"]
        if file_share_subs:
            return {"score": RED, "details": f"{len(file_share_subs)} file-share subscriptions (not supported in PBI Online)"}

        data_driven = [s for s in subs if s.get("IsDataDriven", False)]
        if data_driven:
            return {"score": YELLOW, "details": f"{len(data_driven)} data-driven subscriptions (require manual recreation)"}

        return {"score": GREEN, "details": f"{len(subs)} email subscriptions — migratable"}

    def _score_capacity(self, item: dict) -> dict:
        """Score capacity requirements."""
        if item.get("Type") in self.PREMIUM_REQUIRED_TYPES:
            return {"score": YELLOW, "details": "Paginated report — requires Premium or PPU capacity"}
        if item.get("Type") in self.DEPRECATED_TYPES:
            return {"score": RED, "details": "Mobile reports are deprecated — no PBI Online equivalent"}
        return {"score": GREEN, "details": "Standard capacity"}

    def _score_data_model(self, item: dict) -> dict:
        """Score data model compatibility."""
        if item.get("Type") != "PowerBIReport":
            return {"score": GREEN, "details": "N/A"}
        # All PBI data models are inherently compatible
        return {"score": GREEN, "details": "Power BI data model compatible"}

    def _score_custom_visuals(self, item: dict) -> dict:
        """Score custom visual compatibility."""
        custom_visuals = item.get("custom_visuals", [])
        if not custom_visuals:
            return {"score": GREEN, "details": "No custom visuals"}

        org_visuals = [v for v in custom_visuals if v.get("source") == "organization"]
        if org_visuals:
            return {"score": YELLOW, "details": f"{len(org_visuals)} org visuals — verify availability in target tenant"}
        return {"score": GREEN, "details": f"{len(custom_visuals)} marketplace visuals"}

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _compute_overall_score(self, scores: dict[str, dict]) -> str:
        """Compute overall item score from category scores."""
        all_scores = [s["score"] for s in scores.values()]
        if RED in all_scores:
            return RED
        if YELLOW in all_scores:
            return YELLOW
        return GREEN

    def _compute_summary(self, assessed_items: list[dict]) -> dict:
        """Compute portfolio summary."""
        types = {}
        for item in assessed_items:
            t = item["type"]
            types[t] = types.get(t, 0) + 1

        return {
            "total_items": len(assessed_items),
            "powerbi_reports": types.get("PowerBIReport", 0),
            "paginated_reports": types.get("Report", 0) + types.get("LinkedReport", 0),
            "datasets": types.get("DataSet", 0),
            "kpis": types.get("Kpi", 0),
            "other": sum(v for k, v in types.items() if k not in ("PowerBIReport", "Report", "LinkedReport", "DataSet", "Kpi")),
            "green": sum(1 for i in assessed_items if i["overall"] == GREEN),
            "yellow": sum(1 for i in assessed_items if i["overall"] == YELLOW),
            "red": sum(1 for i in assessed_items if i["overall"] == RED),
            "content_types": types,
        }

    def _plan_migration_waves(self, assessed_items: list[dict]) -> list[dict]:
        """Plan migration waves based on complexity."""
        green_items = [i for i in assessed_items if i["overall"] == GREEN]
        yellow_items = [i for i in assessed_items if i["overall"] == YELLOW]
        red_items = [i for i in assessed_items if i["overall"] == RED]

        waves = []
        if green_items:
            waves.append({
                "wave": 1,
                "name": "Quick Wins",
                "description": "Fully compatible items — direct migration",
                "items": [{"name": i["name"], "path": i["path"], "type": i["type"]} for i in green_items],
                "count": len(green_items),
            })
        if yellow_items:
            waves.append({
                "wave": 2,
                "name": "Minor Adjustments",
                "description": "Items requiring gateway binding, permission mapping, or capacity assignment",
                "items": [{"name": i["name"], "path": i["path"], "type": i["type"]} for i in yellow_items],
                "count": len(yellow_items),
            })
        if red_items:
            waves.append({
                "wave": 3,
                "name": "Rework Required",
                "description": "Items with unsupported features requiring manual intervention",
                "items": [{"name": i["name"], "path": i["path"], "type": i["type"]} for i in red_items],
                "count": len(red_items),
            })
        return waves

    def _generate_item_notes(self, item: dict, scores: dict[str, dict]) -> list[str]:
        """Generate migration notes for an item."""
        notes = []
        for category, score in scores.items():
            if score["score"] in (YELLOW, RED):
                notes.append(f"[{score['score']}] {category}: {score['details']}")
        if item.get("Type") in self.DEPRECATED_TYPES:
            notes.append("Mobile reports are deprecated and have no PBI Online equivalent")
        return notes

    def _generate_recommendations(self, summary: dict, items: list[dict]) -> list[str]:
        """Generate overall migration recommendations."""
        recs = []
        if summary["paginated_reports"] > 0:
            recs.append("Paginated reports require Premium or PPU capacity in PBI Online")
        if summary["red"] > 0:
            recs.append(f"{summary['red']} items require rework before migration — review RED items")
        if summary["yellow"] > 0:
            recs.append(f"{summary['yellow']} items need minor adjustments (gateway, permissions, capacity)")
        if summary.get("content_types", {}).get("MobileReport", 0) > 0:
            recs.append("Mobile reports are deprecated — consider rebuilding as Power BI paginated reports")

        # Gateway recommendation
        gateway_items = [i for i in items if i["scores"].get("gateway_requirements", {}).get("score") == YELLOW]
        if gateway_items:
            recs.append(f"{len(gateway_items)} items need on-premises data gateway — set up gateway before import phase")

        return recs

    def _empty_report(self) -> dict:
        """Return empty assessment report."""
        return {
            "summary": {"total_items": 0, "green": 0, "yellow": 0, "red": 0},
            "items": [],
            "waves": [],
            "recommendations": ["No items found to assess"],
        }

    # ------------------------------------------------------------------
    # HTML report
    # ------------------------------------------------------------------

    def generate_html_report(self, report: dict, output_path: str) -> None:
        """Generate an HTML assessment report."""
        summary = report.get("summary", {})
        items = report.get("items", [])
        waves = report.get("waves", [])
        recommendations = report.get("recommendations", [])

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>PBIRS Migration Assessment Report</title>
    <style>
        :root {{
            --pbi-yellow: #F2C811;
            --pbi-dark: #252423;
            --pbi-blue: #3B82F6;
            --green: #22C55E;
            --yellow: #EAB308;
            --red: #EF4444;
            --bg: #FAFAFA;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--pbi-dark); }}
        .header {{ background: linear-gradient(135deg, var(--pbi-dark), #3B3A39); color: white; padding: 2rem; }}
        .header h1 {{ font-size: 1.8rem; font-weight: 600; }}
        .header p {{ opacity: 0.8; margin-top: 0.5rem; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 1.5rem; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin: 1.5rem 0; }}
        .stat-card {{ background: white; border-radius: 8px; padding: 1.2rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); text-align: center; }}
        .stat-card .value {{ font-size: 2rem; font-weight: 700; }}
        .stat-card .label {{ color: #666; font-size: 0.85rem; margin-top: 0.3rem; }}
        .badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }}
        .badge-green {{ background: #DCFCE7; color: #166534; }}
        .badge-yellow {{ background: #FEF9C3; color: #854D0E; }}
        .badge-red {{ background: #FEE2E2; color: #991B1B; }}
        table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
        th, td {{ padding: 0.6rem 0.8rem; text-align: left; border-bottom: 1px solid #E5E7EB; }}
        th {{ background: #F3F4F6; font-weight: 600; font-size: 0.85rem; }}
        .section {{ background: white; border-radius: 8px; padding: 1.5rem; margin: 1rem 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .section h2 {{ font-size: 1.2rem; margin-bottom: 1rem; color: var(--pbi-dark); }}
        .rec-list {{ list-style: none; }}
        .rec-list li {{ padding: 0.5rem 0; border-bottom: 1px solid #F3F4F6; }}
        .rec-list li::before {{ content: "⚡"; margin-right: 0.5rem; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>PBIRS → PBI Online Migration Assessment</h1>
        <p>Power BI Report Server content readiness report</p>
    </div>
    <div class="container">
        <div class="stats">
            <div class="stat-card"><div class="value">{summary.get('total_items', 0)}</div><div class="label">Total Items</div></div>
            <div class="stat-card"><div class="value" style="color:var(--green)">{summary.get('green', 0)}</div><div class="label">Ready (GREEN)</div></div>
            <div class="stat-card"><div class="value" style="color:var(--yellow)">{summary.get('yellow', 0)}</div><div class="label">Minor Work (YELLOW)</div></div>
            <div class="stat-card"><div class="value" style="color:var(--red)">{summary.get('red', 0)}</div><div class="label">Rework (RED)</div></div>
            <div class="stat-card"><div class="value">{summary.get('powerbi_reports', 0)}</div><div class="label">Power BI Reports</div></div>
            <div class="stat-card"><div class="value">{summary.get('paginated_reports', 0)}</div><div class="label">Paginated Reports</div></div>
        </div>

        <div class="section">
            <h2>Recommendations</h2>
            <ul class="rec-list">
                {''.join(f'<li>{r}</li>' for r in recommendations)}
            </ul>
        </div>

        <div class="section">
            <h2>Migration Waves</h2>
            {''.join(self._wave_html(w) for w in waves)}
        </div>

        <div class="section">
            <h2>Item Details</h2>
            <table>
                <thead><tr><th>Name</th><th>Type</th><th>Path</th><th>Score</th><th>Notes</th></tr></thead>
                <tbody>
                    {''.join(self._item_row_html(i) for i in items)}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

    def _wave_html(self, wave: dict) -> str:
        return f"""<div style="margin-bottom:1rem">
            <h3>Wave {wave['wave']}: {wave['name']} ({wave['count']} items)</h3>
            <p style="color:#666">{wave['description']}</p>
        </div>"""

    def _item_row_html(self, item: dict) -> str:
        badge_class = f"badge-{item['overall'].lower()}"
        notes = "<br>".join(item.get("notes", []))
        return f"""<tr>
            <td>{_esc(item['name'])}</td>
            <td>{_esc(item['type'])}</td>
            <td>{_esc(item['path'])}</td>
            <td><span class="badge {badge_class}">{item['overall']}</span></td>
            <td style="font-size:0.8rem">{notes}</td>
        </tr>"""


def _esc(text: str) -> str:
    """Escape HTML entities."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
