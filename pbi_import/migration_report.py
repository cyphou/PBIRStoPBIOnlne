"""
Migration Report — generates HTML + JSON migration status reports.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class MigrationReport:
    """Generate migration status/fidelity reports."""

    def generate(
        self,
        assessment: dict,
        export_results: dict,
        conversion_results: dict,
        import_results: dict,
        validation_results: dict,
        output_dir: str,
    ) -> dict:
        """Generate a comprehensive migration report."""
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "phases": {
                "assessment": self._summarize_assessment(assessment),
                "export": self._summarize_export(export_results),
                "conversion": self._summarize_conversion(conversion_results),
                "import": self._summarize_import(import_results),
                "validation": self._summarize_validation(validation_results),
            },
            "overall_status": self._compute_overall(validation_results),
        }

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # Write JSON report
        json_path = out / "migration_report.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        # Write HTML report
        html_path = out / "migration_report.html"
        self._write_html(report, str(html_path))

        logger.info("Migration report written to %s", out)
        return report

    def _summarize_assessment(self, assessment: dict) -> dict:
        summary = assessment.get("summary", {})
        return {
            "total_items": summary.get("total_items", 0),
            "green": summary.get("green", 0),
            "yellow": summary.get("yellow", 0),
            "red": summary.get("red", 0),
        }

    def _summarize_export(self, export_results: dict) -> dict:
        dl = export_results.get("download_results", {})
        return {
            "downloaded": len(dl.get("success", [])),
            "failed": len(dl.get("failed", [])),
            "skipped": len(dl.get("skipped", [])),
        }

    def _summarize_conversion(self, conversion_results: dict) -> dict:
        return {
            "converted": conversion_results.get("converted", 0),
            "skipped": conversion_results.get("skipped", 0),
            "failed": conversion_results.get("failed", 0),
        }

    def _summarize_import(self, import_results: dict) -> dict:
        total_success = 0
        total_failed = 0
        for key, val in import_results.items():
            if isinstance(val, dict):
                total_success += len(val.get("success", []))
                total_failed += len(val.get("failed", []))
        return {"published": total_success, "failed": total_failed}

    def _summarize_validation(self, validation_results: dict) -> dict:
        return {
            "overall": validation_results.get("overall", "N/A"),
            "issues": validation_results.get("issues", []),
        }

    def _compute_overall(self, validation_results: dict) -> str:
        return validation_results.get("overall", "UNKNOWN")

    def _write_html(self, report: dict, path: str) -> None:
        phases = report["phases"]
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>PBIRS Migration Report</title>
    <style>
        :root {{ --dark: #252423; --green: #22C55E; --yellow: #EAB308; --red: #EF4444; }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #FAFAFA; color: var(--dark); }}
        .header {{ background: linear-gradient(135deg, var(--dark), #3B3A39); color: white; padding: 2rem; }}
        .container {{ max-width: 1000px; margin: 0 auto; padding: 1.5rem; }}
        .card {{ background: white; border-radius: 8px; padding: 1.5rem; margin: 1rem 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .card h2 {{ margin-bottom: 0.8rem; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 0.5rem; text-align: left; border-bottom: 1px solid #E5E7EB; }}
        th {{ background: #F3F4F6; }}
        .status {{ font-weight: 700; }}
        .pass {{ color: var(--green); }}
        .warn {{ color: var(--yellow); }}
        .fail {{ color: var(--red); }}
    </style>
</head>
<body>
    <div class="header">
        <h1>PBIRS → PBI Online Migration Report</h1>
        <p>Generated: {report['generated_at']}</p>
        <p class="status {'pass' if report['overall_status'] == 'PASS' else 'fail'}">
            Overall: {report['overall_status']}
        </p>
    </div>
    <div class="container">
        <div class="card">
            <h2>Assessment</h2>
            <table>
                <tr><th>Metric</th><th>Value</th></tr>
                <tr><td>Total Items</td><td>{phases['assessment']['total_items']}</td></tr>
                <tr><td>Ready (GREEN)</td><td>{phases['assessment']['green']}</td></tr>
                <tr><td>Minor Work (YELLOW)</td><td>{phases['assessment']['yellow']}</td></tr>
                <tr><td>Rework (RED)</td><td>{phases['assessment']['red']}</td></tr>
            </table>
        </div>
        <div class="card">
            <h2>Export</h2>
            <table>
                <tr><th>Metric</th><th>Value</th></tr>
                <tr><td>Downloaded</td><td>{phases['export']['downloaded']}</td></tr>
                <tr><td>Failed</td><td>{phases['export']['failed']}</td></tr>
                <tr><td>Skipped</td><td>{phases['export']['skipped']}</td></tr>
            </table>
        </div>
        <div class="card">
            <h2>Conversion</h2>
            <table>
                <tr><th>Metric</th><th>Value</th></tr>
                <tr><td>Converted</td><td>{phases['conversion']['converted']}</td></tr>
                <tr><td>Skipped</td><td>{phases['conversion']['skipped']}</td></tr>
                <tr><td>Failed</td><td>{phases['conversion']['failed']}</td></tr>
            </table>
        </div>
        <div class="card">
            <h2>Import</h2>
            <table>
                <tr><th>Metric</th><th>Value</th></tr>
                <tr><td>Published</td><td>{phases['import']['published']}</td></tr>
                <tr><td>Failed</td><td>{phases['import']['failed']}</td></tr>
            </table>
        </div>
        <div class="card">
            <h2>Validation</h2>
            <p class="status {'pass' if phases['validation']['overall'] == 'PASS' else 'fail'}">
                {phases['validation']['overall']}
            </p>
            {''.join(f'<p>⚠ {issue}</p>' for issue in phases['validation'].get('issues', []))}
        </div>
    </div>
</body>
</html>"""

        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
