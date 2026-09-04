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
        "CustomAssembly",
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
            conn_type = ds.get("ConnectionString") or ds.get("DataSourceType") or ""
            # Check for on-prem only connection types
            if any(k in conn_type.lower() for k in ("file://", "\\\\", "localhost", "127.0.0.1")):
                issues.append(f"Local/file-based connection: {conn_type[:80]}")

        if issues:
            return {"score": RED, "details": "; ".join(issues)}
        return {"score": GREEN, "details": "All datasources compatible"}

    def _score_complexity(self, item: dict) -> dict:
        """Score report complexity."""
        if item.get("custom_visuals"):
            return {"score": RED, "details": "Custom visuals require target-tenant compatibility review"}
        if item.get("subscriptions"):
            return {"score": RED, "details": "Subscriptions require explicit Power BI Online recreation"}
        if self._has_rls(item):
            return {"score": YELLOW, "details": "Row-Level Security detected — validate model roles"}

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

    @staticmethod
    def _has_rls(item: dict) -> bool:
        if item.get("has_rls"):
            return True
        for expression in item.get("dax_expressions", []):
            text = str(expression).lower()
            if "username()" in text or "userprincipalname()" in text:
                return True
        return any(
            isinstance(ds, dict) and (ds.get("SecurityRoles") or ds.get("roles"))
            for ds in item.get("datasources", [])
        )

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
        """Compute complexity status without conflating operational requirements."""
        if any(detail.get("score") == RED for detail in scores.values()):
            return RED
        if scores.get("report_complexity", {}).get("score") == YELLOW:
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
        wave_number = 1
        if green_items:
            waves.append({
            "wave": wave_number,
                "name": "Quick Wins",
                "description": "Fully compatible items — direct migration",
                "items": [{"name": i["name"], "path": i["path"], "type": i["type"]} for i in green_items],
                "count": len(green_items),
            })
            wave_number += 1
        if yellow_items:
            waves.append({
                "wave": wave_number,
                "name": "Minor Adjustments",
                "description": "Items requiring gateway binding, permission mapping, or capacity assignment",
                "items": [{"name": i["name"], "path": i["path"], "type": i["type"]} for i in yellow_items],
                "count": len(yellow_items),
            })
            wave_number += 1
        if red_items:
            waves.append({
                "wave": wave_number,
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
        total = int(summary.get("total_items", 0) or 0)
        green = int(summary.get("green", 0) or 0)
        yellow = int(summary.get("yellow", 0) or 0)
        red = int(summary.get("red", 0) or 0)
        readiness = round((green / total) * 100) if total else 0
        risk_categories: dict[str, int] = {}
        for item in items:
            for category, detail in item.get("scores", {}).items():
                if detail.get("score") in (YELLOW, RED):
                    risk_categories[category] = risk_categories.get(category, 0) + 1
        top_risks = sorted(risk_categories.items(), key=lambda pair: (-pair[1], pair[0]))[:5]

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>PBIRS Migration Assessment Report</title>
    <style>
        :root {{ --ink:#17212b; --muted:#65727e; --line:#dfe5ea; --paper:#ffffff; --canvas:#f4f6f8; --accent:#f2c811; --green:#16a34a; --yellow:#c27a00; --red:#c73636; }}
        * {{ box-sizing:border-box; margin:0; padding:0; }}
        body {{ font-family:'Segoe UI', system-ui, sans-serif; background:var(--canvas); color:var(--ink); line-height:1.45; }}
        .hero {{ background:linear-gradient(120deg,#17212b 0%,#263746 72%,#f2c811 72%,#f2c811 100%); color:#fff; padding:2.8rem max(1.25rem,calc((100% - 1240px)/2)); }}
        .eyebrow {{ color:#f8d83b; font-size:.72rem; font-weight:700; letter-spacing:.12em; text-transform:uppercase; }}
        h1 {{ font-size:clamp(1.8rem,4vw,3rem); letter-spacing:-.03em; margin-top:.55rem; }}
        .hero p {{ color:#d6e0e8; max-width:680px; margin-top:.7rem; }}
        .container {{ max-width:1240px; margin:0 auto; padding:1.4rem 1.25rem 3rem; }}
        .executive {{ display:grid; grid-template-columns:1.25fr .75fr; gap:1rem; margin-top:-1.4rem; position:relative; }}
        .panel {{ background:var(--paper); border:1px solid var(--line); border-radius:12px; padding:1.25rem; box-shadow:0 8px 24px rgba(23,33,43,.06); }}
        .panel h2 {{ font-size:1rem; margin-bottom:.9rem; }}
        .readiness {{ display:flex; align-items:center; gap:1rem; }}
        .score {{ font-size:3.2rem; font-weight:750; letter-spacing:-.06em; color:var(--green); }}
        .meter {{ height:10px; background:#e8edf1; border-radius:99px; overflow:hidden; margin:.45rem 0 .3rem; }}
        .meter span {{ display:block; height:100%; width:{readiness}%; background:linear-gradient(90deg,#16a34a,#9bcf45); border-radius:inherit; }}
        .muted {{ color:var(--muted); font-size:.82rem; }}
        .stats {{ display:grid; grid-template-columns:repeat(5,1fr); gap:.7rem; margin:1rem 0; }}
        .stat-card {{ background:var(--paper); border:1px solid var(--line); border-radius:10px; padding:1rem; }}
        .stat-card .value {{ font-size:1.75rem; font-weight:750; }}
        .stat-card .label {{ color:var(--muted); font-size:.75rem; margin-top:.25rem; }}
        .green {{ color:var(--green); }} .yellow {{ color:var(--yellow); }} .red {{ color:var(--red); }}
        .badge {{ display:inline-block; padding:.22rem .58rem; border-radius:99px; font-size:.72rem; font-weight:750; }}
        .badge-green {{ background:#e3f6e8; color:#166534; }} .badge-yellow {{ background:#fff2d2; color:#8a5700; }} .badge-red {{ background:#fde5e5; color:#982b2b; }}
        .risk-list {{ display:grid; gap:.55rem; list-style:none; }}
        .risk-list li {{ display:flex; justify-content:space-between; gap:1rem; padding:.5rem 0; border-bottom:1px solid #eef1f3; font-size:.84rem; }}
        .section {{ margin-top:1rem; }}
        .section-header {{ display:flex; align-items:end; justify-content:space-between; gap:1rem; margin-bottom:.8rem; }}
        .section-header h2 {{ font-size:1.15rem; }}
        .rec-list {{ list-style:none; display:grid; gap:.55rem; }}
        .rec-list li {{ background:var(--paper); border-left:4px solid var(--accent); border-radius:8px; padding:.75rem 1rem; border-top:1px solid var(--line); border-right:1px solid var(--line); border-bottom:1px solid var(--line); }}
        .toolbar {{ display:flex; gap:.6rem; flex-wrap:wrap; }}
        input, select {{ border:1px solid #cbd5dc; border-radius:7px; padding:.55rem .7rem; background:#fff; color:var(--ink); }}
        .table-wrap {{ overflow:auto; border:1px solid var(--line); border-radius:10px; background:#fff; }}
        table {{ width:100%; border-collapse:collapse; min-width:850px; }}
        th, td {{ padding:.72rem .8rem; text-align:left; border-bottom:1px solid #edf0f2; vertical-align:top; }}
        th {{ background:#eef2f5; color:#3a4853; font-weight:700; font-size:.74rem; text-transform:uppercase; letter-spacing:.04em; position:sticky; top:0; }}
        td {{ font-size:.82rem; }} tr:last-child td {{ border-bottom:0; }} tr:hover td {{ background:#fbfcfd; }}
        .wave {{ background:var(--paper); border:1px solid var(--line); border-radius:9px; padding:.8rem 1rem; margin:.55rem 0; }}
        .wave h3 {{ font-size:.9rem; }}
        @media (max-width:800px) {{ .executive {{ grid-template-columns:1fr; }} .stats {{ grid-template-columns:repeat(2,1fr); }} .hero {{ background:#17212b; }} }}
    </style>
</head>
<body>
    <div class="hero">
        <div class="eyebrow">Migration intelligence</div>
        <h1>PBIRS → Power BI Online</h1>
        <p>Executive readiness view for the source portfolio, migration risk and next delivery wave.</p>
    </div>
    <div class="container">
        <div class="executive">
            <div class="panel">
                <h2>Portfolio readiness</h2>
                <div class="readiness">
                    <div class="score">{readiness}%</div>
                    <div style="flex:1"><strong>{green} of {total} items ready</strong><div class="meter"><span></span></div><div class="muted">Based on items currently classified GREEN</div></div>
                </div>
            </div>
            <div class="panel">
                <h2>Top attention areas</h2>
                <ul class="risk-list">{''.join(f'<li><span>{_esc(category.replace("_", " ").title())}</span><strong>{count}</strong></li>' for category, count in top_risks) or '<li><span class="muted">No immediate risk areas</span><strong>—</strong></li>'}</ul>
            </div>
        </div>
        <div class="stats">
            <div class="stat-card"><div class="value">{total}</div><div class="label">Total items</div></div>
            <div class="stat-card"><div class="value green">{green}</div><div class="label">Ready</div></div>
            <div class="stat-card"><div class="value yellow">{yellow}</div><div class="label">Attention</div></div>
            <div class="stat-card"><div class="value red">{red}</div><div class="label">Rework</div></div>
            <div class="stat-card"><div class="value">{summary.get('paginated_reports', 0) + summary.get('powerbi_reports', 0)}</div><div class="label">Reports</div></div>
        </div>

        <div class="section panel">
            <div class="section-header"><h2>Recommended next actions</h2><span class="muted">Prioritize before import</span></div>
            <ul class="rec-list">
                {''.join(f'<li>{_esc(r)}</li>' for r in recommendations) or '<li>No additional actions generated.</li>'}
            </ul>
        </div>

        <div class="section panel">
            <div class="section-header"><h2>Migration waves</h2><span class="muted">Delivery sequence</span></div>
            {''.join(self._wave_html(w) for w in waves)}
        </div>

        <div class="section">
            <div class="section-header"><h2>Portfolio detail</h2><div class="toolbar"><input id="search" type="search" placeholder="Search name or path" oninput="filterRows()"><select id="status" onchange="filterRows()"><option value="">All statuses</option><option>GREEN</option><option>YELLOW</option><option>RED</option></select></div></div>
            <div class="table-wrap"><table>
                <thead><tr><th>Name</th><th>Type</th><th>Path</th><th>Score</th><th>Notes</th></tr></thead>
                <tbody>
                    {''.join(self._item_row_html(i) for i in items)}
                </tbody>
            </table></div>
        </div>
    </div>
    <script type="text/javascript">
    function filterRows() {{
        const query = document.getElementById('search').value.toLowerCase();
        const status = document.getElementById('status').value;
        document.querySelectorAll('tbody tr').forEach(row => {{
            const matchesText = row.innerText.toLowerCase().includes(query);
            const matchesStatus = !status || row.dataset.status === status;
            row.style.display = matchesText && matchesStatus ? '' : 'none';
        }});
    }}
    </script>
</body>
</html>"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

    def _wave_html(self, wave: dict) -> str:
        return f"""<div class="wave">
            <h3>Wave {wave['wave']}: {wave['name']} ({wave['count']} items)</h3>
            <p class="muted">{_esc(wave['description'])}</p>
        </div>"""

    def _item_row_html(self, item: dict) -> str:
        badge_class = f"badge-{item['overall'].lower()}"
        notes = "<br>".join(_esc(note) for note in item.get("notes", []))
        return f"""<tr data-status="{_esc(item['overall'])}">
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
