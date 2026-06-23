"""
Visual Diff Report — HTML report comparing source vs target report screenshots.

Extends ``visual_regression`` into a stakeholder-ready deliverable: pairs each
PBIRS before/after screenshot, renders an HTML page with side-by-side thumbnails,
diff status, and a summary table. Stdlib only — no Pillow, no Jinja2.
"""

from __future__ import annotations

import base64
import html
import json
import logging
from pathlib import Path

from pbi_import.visual_regression import VisualRegression

logger = logging.getLogger(__name__)


class VisualDiffReport:
    """Generate a side-by-side HTML visual diff report."""

    def __init__(self, threshold: float = 0.05, embed_images: bool = True):
        self.regression = VisualRegression(threshold=threshold)
        self.embed_images = embed_images

    def generate(self, pairs: list[dict], output_path: str | Path) -> dict:
        """Render *pairs* into an HTML report at *output_path*.

        Each pair: ``{"name": str, "before": path, "after": path}``.
        Returns a summary dict with totals and per-pair statuses.
        """
        results = []
        for pair in pairs:
            cmp = self.regression.compare_files(pair["before"], pair["after"])
            cmp["name"] = pair.get("name", "report")
            results.append(cmp)

        summary = self._summarise(results)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self._render_html(results, summary), encoding="utf-8")
        logger.info(
            "Visual diff report written to %s (pass=%d fail=%d error=%d)",
            out, summary["pass"], summary["fail"], summary["error"],
        )
        summary["output"] = str(out)
        return summary

    # ------------------------------------------------------------------

    @staticmethod
    def _summarise(results: list[dict]) -> dict:
        total = len(results)
        passed = sum(1 for r in results if r.get("status") == "pass")
        failed = sum(1 for r in results if r.get("status") == "fail")
        error = sum(1 for r in results if r.get("status") == "error")
        return {
            "total": total, "pass": passed, "fail": failed, "error": error,
            "pass_rate": round(passed / total, 4) if total else 0.0,
        }

    def _embed(self, path: str) -> str:
        if not self.embed_images:
            return path
        p = Path(path)
        if not p.is_file():
            return ""
        ext = p.suffix.lower().lstrip(".") or "png"
        data = base64.b64encode(p.read_bytes()).decode("ascii")
        return f"data:image/{ext};base64,{data}"

    def _render_html(self, results: list[dict], summary: dict) -> str:
        rows = []
        for r in results:
            before = self._embed(r.get("before_file", ""))
            after = self._embed(r.get("after_file", ""))
            status = r.get("status", "error")
            badge_class = {
                "pass": "ok", "fail": "bad", "error": "err",
            }.get(status, "err")
            rows.append(f"""
<section class="pair">
  <h2>{html.escape(str(r.get("name", "report")))}
    <span class="badge {badge_class}">{status.upper()}</span></h2>
  <div class="meta">diff={r.get("difference", "n/a")} method={html.escape(str(r.get("method", "")))}</div>
  <div class="grid">
    <figure><figcaption>Source (PBIRS)</figcaption>
      {'<img src="' + html.escape(before) + '"/>' if before else '<div class="missing">missing</div>'}
    </figure>
    <figure><figcaption>Target (PBI Online)</figcaption>
      {'<img src="' + html.escape(after) + '"/>' if after else '<div class="missing">missing</div>'}
    </figure>
  </div>
</section>
""")

        return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Visual Diff Report</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:24px;color:#222}}
 h1{{margin-bottom:4px}}
 .summary{{background:#f3f3f3;padding:12px 16px;border-radius:6px;margin:12px 0 24px}}
 .summary span{{margin-right:18px;font-weight:600}}
 .pair{{border:1px solid #ddd;border-radius:6px;padding:16px;margin:16px 0;background:#fff}}
 .grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:12px}}
 figure{{margin:0;text-align:center}}
 figure img{{max-width:100%;border:1px solid #ccc;border-radius:4px}}
 figcaption{{font-size:13px;color:#666;margin-bottom:6px}}
 .missing{{padding:48px;color:#999;background:#fafafa;border:1px dashed #ccc;border-radius:4px}}
 .badge{{display:inline-block;padding:2px 10px;border-radius:10px;font-size:12px;margin-left:8px;color:#fff}}
 .badge.ok{{background:#107c10}}
 .badge.bad{{background:#a4262c}}
 .badge.err{{background:#605e5c}}
 .meta{{color:#666;font-size:13px}}
</style></head><body>
<h1>Visual Diff Report</h1>
<div class="summary">
 <span>Total: {summary["total"]}</span>
 <span style="color:#107c10">Pass: {summary["pass"]}</span>
 <span style="color:#a4262c">Fail: {summary["fail"]}</span>
 <span style="color:#605e5c">Error: {summary["error"]}</span>
 <span>Pass rate: {summary["pass_rate"] * 100:.1f}%</span>
</div>
<pre style="display:none">{html.escape(json.dumps(summary))}</pre>
{"".join(rows)}
</body></html>"""
