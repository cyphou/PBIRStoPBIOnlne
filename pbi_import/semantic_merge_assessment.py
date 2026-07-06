"""Semantic model merge assessment and HTML reporting.

Evaluates whether semantic models should be merged into shared datasets (thin
report pattern) and whether composite model candidates need capacity before
rollout.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from pbi_import.composite_model_planner import CompositeModelPlanner
from pbi_import.model_splitter import ModelSplitter


class SemanticMergeAssessment:
    """Assess semantic model merge readiness and produce a stakeholder HTML report."""

    def assess(self, catalog: dict[str, Any], capacity_id: str | None = None) -> dict[str, Any]:
        items = self._catalog_items(catalog)
        semantic_items = [
            i for i in items
            if i.get("Type") in ("PowerBIReport", "DataSet")
        ]
        splitter = ModelSplitter().analyse(semantic_items)
        composite = CompositeModelPlanner().plan(semantic_items)

        split_groups = [
            r for r in splitter.get("recommendations", [])
            if r.get("action") == "split"
        ]
        composite_candidates = composite.get("candidates", [])

        blockers: list[str] = []
        recommendations: list[str] = []

        if split_groups:
            recommendations.append(
                f"{len(split_groups)} shared semantic-model group(s) detected; thin reports are recommended"
            )
        if composite_candidates:
            recommendations.append(
                f"{len(composite_candidates)} composite model candidate(s) detected"
            )
            if not capacity_id:
                blockers.append(
                    "Composite model merge candidates detected but no capacity configured"
                )
                recommendations.append(
                    "Configure Fabric/Premium capacity before enabling composite model rollout"
                )
            else:
                recommendations.append(
                    f"Capacity configured ({capacity_id}) for composite model rollout"
                )

        if not semantic_items:
            recommendations.append(
                "No Power BI semantic-model artifacts found in catalog (PowerBIReport/DataSet)"
            )
        elif not split_groups and not composite_candidates:
            recommendations.append(
                "No semantic-model merge opportunity detected from current catalog"
            )

        merge_recommended = bool(split_groups or composite_candidates)
        can_merge_now = bool(split_groups) or bool(composite_candidates and capacity_id)

        if merge_recommended and can_merge_now and not blockers:
            status = "READY"
        elif merge_recommended:
            status = "CONDITIONAL"
        else:
            status = "NOT_RECOMMENDED"

        score = self._score(split_groups, composite_candidates, blockers)

        summary = {
            "status": status,
            "score": score,
            "catalog_items": len(items),
            "semantic_items_analysed": len(semantic_items),
            "reports_analysed": sum(
                1 for i in semantic_items if i.get("Type") == "PowerBIReport"
            ),
            "semantic_merge_groups": len(split_groups),
            "composite_candidates": len(composite_candidates),
            "capacity_required": bool(composite_candidates),
            "capacity_configured": bool(capacity_id),
            "capacity_id": capacity_id,
            "merge_recommended": merge_recommended,
            "can_merge_now": can_merge_now and not blockers,
        }

        return {
            "summary": summary,
            "splitter": splitter,
            "composite": composite,
            "blockers": blockers,
            "recommendations": recommendations,
        }

    def generate_html_report(self, report: dict[str, Any], output_path: str | Path) -> None:
        summary = report.get("summary", {})
        blockers = report.get("blockers", [])
        recommendations = report.get("recommendations", [])
        split_groups = [
            r for r in report.get("splitter", {}).get("recommendations", [])
            if r.get("action") == "split"
        ]
        composite_candidates = report.get("composite", {}).get("candidates", [])

        status = str(summary.get("status", "NOT_RECOMMENDED"))
        status_class = {
            "READY": "badge-ready",
            "CONDITIONAL": "badge-conditional",
            "NOT_RECOMMENDED": "badge-not",
        }.get(status, "badge-not")

        html_doc = f"""<!doctype html>
<html lang=\"en\"> 
<head>
  <meta charset=\"utf-8\"> 
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"> 
  <title>Semantic Model Merge Assessment</title>
  <style>
    :root {{
      --ink:#1f2937;
      --muted:#6b7280;
      --bg:#f8fafc;
      --card:#ffffff;
      --line:#e5e7eb;
      --ok:#166534;
      --okbg:#dcfce7;
      --warn:#854d0e;
      --warnbg:#fef9c3;
      --bad:#991b1b;
      --badbg:#fee2e2;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:'Segoe UI',system-ui,sans-serif; color:var(--ink); background:linear-gradient(180deg,#eef2ff 0%, var(--bg) 22%); }}
    .wrap {{ max-width:1200px; margin:0 auto; padding:24px; }}
    .hero {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:18px 20px; box-shadow:0 4px 16px rgba(15,23,42,0.05); }}
    .hero h1 {{ margin:0; font-size:1.5rem; }}
    .hero p {{ margin:8px 0 0; color:var(--muted); }}
    .badge {{ display:inline-block; margin-top:12px; padding:6px 10px; border-radius:999px; font-weight:700; font-size:.82rem; }}
    .badge-ready {{ background:var(--okbg); color:var(--ok); }}
    .badge-conditional {{ background:var(--warnbg); color:var(--warn); }}
    .badge-not {{ background:var(--badbg); color:var(--bad); }}
    .cards {{ margin-top:16px; display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; }}
    .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px; }}
    .card .v {{ font-size:1.4rem; font-weight:700; }}
    .card .k {{ font-size:.8rem; color:var(--muted); margin-top:4px; }}
    .section {{ margin-top:14px; background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px; }}
    .section h2 {{ margin:0 0 10px; font-size:1.04rem; }}
    table {{ width:100%; border-collapse:collapse; }}
    th,td {{ padding:8px 10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; font-size:.92rem; }}
    th {{ color:#374151; font-size:.82rem; letter-spacing:.02em; text-transform:uppercase; }}
    ul {{ margin:0; padding-left:18px; }}
    li {{ margin:6px 0; }}
    .muted {{ color:var(--muted); }}
    .empty {{ color:var(--muted); font-style:italic; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <section class=\"hero\">
      <h1>Semantic Model Merge Assessment</h1>
      <p>Assessment of shared semantic-model merge feasibility and composite-model prerequisites.</p>
      <span class=\"badge {status_class}\">{_esc(status)}</span>
    </section>

    <section class=\"cards\">
      <div class=\"card\"><div class=\"v\">{summary.get('score', 0)}</div><div class=\"k\">Readiness Score</div></div>
      <div class=\"card\"><div class=\"v\">{summary.get('semantic_merge_groups', 0)}</div><div class=\"k\">Shared Model Groups</div></div>
      <div class=\"card\"><div class=\"v\">{summary.get('composite_candidates', 0)}</div><div class=\"k\">Composite Candidates</div></div>
      <div class=\"card\"><div class=\"v\">{summary.get('reports_analysed', 0)}</div><div class=\"k\">Reports Analysed</div></div>
      <div class=\"card\"><div class=\"v\">{'Yes' if summary.get('can_merge_now') else 'No'}</div><div class=\"k\">Can Merge Now</div></div>
      <div class=\"card\"><div class=\"v\">{'Yes' if summary.get('capacity_configured') else 'No'}</div><div class=\"k\">Capacity Configured</div></div>
    </section>

    <section class=\"section\">
      <h2>Recommendations</h2>
      {_list_html(recommendations, empty='No recommendations generated')}
    </section>

    <section class=\"section\">
      <h2>Blockers</h2>
      {_list_html(blockers, empty='No blockers detected')}
    </section>

    <section class=\"section\">
      <h2>Shared Semantic Model Groups</h2>
      {self._split_table(split_groups)}
    </section>

    <section class=\"section\">
      <h2>Composite Model Candidates</h2>
      {self._composite_table(composite_candidates)}
    </section>

    <section class=\"section\">
      <h2>Raw Summary</h2>
      <pre>{_esc(json.dumps(summary, indent=2))}</pre>
    </section>
  </div>
</body>
</html>"""

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html_doc, encoding="utf-8")

    @staticmethod
    def _catalog_items(catalog: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(catalog, dict):
            return []
        raw = catalog.get("items", [])
        if isinstance(raw, list):
            return [i for i in raw if isinstance(i, dict)]
        return []

    @staticmethod
    def _score(split_groups: list[dict[str, Any]], composite_candidates: list[dict[str, Any]], blockers: list[str]) -> int:
        if not split_groups and not composite_candidates:
            return 35
        score = 85
        score += min(10, len(split_groups) * 2)
        score += min(5, len(composite_candidates))
        score -= min(40, len(blockers) * 20)
        return max(0, min(100, score))

    @staticmethod
    def _split_table(groups: list[dict[str, Any]]) -> str:
        if not groups:
            return '<p class="empty">No shared semantic-model groups detected.</p>'
        rows = []
        for g in groups:
            names = ", ".join(_esc(r.get("name", "")) for r in g.get("reports", []))
            rows.append(
                "<tr>"
                f"<td>{_esc(g.get('dataset_reference', ''))}</td>"
                f"<td>{int(g.get('report_count', 0))}</td>"
                f"<td>{names}</td>"
                "</tr>"
            )
        return (
            "<table><thead><tr><th>Dataset Reference</th><th>Reports</th><th>Report Names</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )

    @staticmethod
    def _composite_table(candidates: list[dict[str, Any]]) -> str:
        if not candidates:
            return '<p class="empty">No composite model candidates detected.</p>'
        rows = []
        for c in candidates:
            partitions = ", ".join(
                f"{_esc(p.get('datasource', ''))}: {_esc(p.get('recommended_mode', ''))}"
                for p in c.get("partitions", [])
            )
            rows.append(
                "<tr>"
                f"<td>{_esc(c.get('name', ''))}</td>"
                f"<td>{_esc(c.get('model_type', ''))}</td>"
                f"<td>{int(c.get('datasource_count', 0))}</td>"
                f"<td>{partitions}</td>"
                "</tr>"
            )
        return (
            "<table><thead><tr><th>Name</th><th>Type</th><th>Datasources</th><th>Partitions</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _list_html(values: list[str], empty: str) -> str:
    if not values:
        return f'<p class="empty">{_esc(empty)}</p>'
    return "<ul>" + "".join(f"<li>{_esc(v)}</li>" for v in values) + "</ul>"
