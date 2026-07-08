"""PBIX compatibility inspection and HTML reporting.

Checks PBIX package structure before upload so common PBIRS import failures can
be caught early with a readable report.
"""

from __future__ import annotations

import html
import json
import logging
import zipfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PbixCompatibilityInspector:
    """Inspect PBIX packages for common upload blockers and risk signals."""

    REQUIRED_PARTS = (
        "Version",
        "[Content_Types].xml",
        "Report/Layout",
        "Settings",
        "Metadata",
        "Connections",
        "SecurityBindings",
        "DiagramLayout",
    )

    WARNING_PARTS = (
        "DataModel",
        "DataMashup",
        "docProps/custom.xml",
    )

    def inspect(self, pbix_path: Path) -> dict[str, Any]:
        """Inspect a single PBIX file and return a structured result."""
        result: dict[str, Any] = {
            "name": pbix_path.stem,
            "path": str(pbix_path),
            "exists": pbix_path.exists(),
            "size_bytes": pbix_path.stat().st_size if pbix_path.exists() else 0,
            "size_mb": round(pbix_path.stat().st_size / (1024 * 1024), 2) if pbix_path.exists() else 0,
            "status": "FAIL",
            "score": 0,
            "issues": [],
            "warnings": [],
            "recommendations": [],
            "core_parts": [],
            "missing_parts": [],
            "package_type": "unknown",
            "desktop_version_hint": None,
        }

        if not pbix_path.exists():
            result["issues"].append("File does not exist")
            result["recommendations"].append("Re-run conversion or confirm the PBIX path")
            return result

        try:
            with zipfile.ZipFile(pbix_path, "r") as archive:
                names = set(archive.namelist())
                result["package_type"] = "zip"

                missing_required = [part for part in self.REQUIRED_PARTS if part not in names]
                result["missing_parts"] = missing_required
                result["core_parts"] = [part for part in self.REQUIRED_PARTS if part in names]

                if missing_required:
                    result["issues"].append(
                        "Missing required PBIX package part(s): " + ", ".join(missing_required)
                    )

                for warning_part in self.WARNING_PARTS:
                    if warning_part not in names:
                        result["warnings"].append(f"Optional package part missing: {warning_part}")

                layout = self._read_text(archive, "Report/Layout")
                if layout is None:
                    result["issues"].append("Report/Layout could not be read as UTF-8 JSON text")
                else:
                    try:
                        layout_payload = json.loads(layout)
                        if not isinstance(layout_payload, dict):
                            raise ValueError("Report/Layout payload is not an object")
                        if not layout_payload.get("sections"):
                            result["warnings"].append("Report/Layout contains no sections")
                    except Exception as exc:
                        result["issues"].append(f"Report/Layout JSON is invalid: {exc}")

                connections_text = self._read_text(archive, "Connections")
                if connections_text:
                    try:
                        connections_payload = json.loads(connections_text)
                        connection_types = self._extract_connection_types(connections_payload)
                        if "pbiservicelive" in connection_types:
                            result["issues"].append(
                                "Connections contains ConnectionType=pbiServiceLive, which PBIRS commonly rejects with HTTP 422"
                            )
                            result["recommendations"].append(
                                "Skip this PBIX for automated upload and migrate the live-connection dependency manually"
                            )
                    except Exception as exc:
                        result["warnings"].append(f"Connections payload could not be parsed as JSON: {exc}")

                custom_xml = self._read_text(archive, "docProps/custom.xml")
                if custom_xml:
                    version_hint = self._extract_desktop_version_hint(custom_xml)
                    if version_hint:
                        result["desktop_version_hint"] = version_hint

        except zipfile.BadZipFile:
            result["issues"].append("PBIX is not a valid ZIP package")
            result["recommendations"].append(
                "Open the file in Power BI Desktop for Report Server and save it again"
            )
            return self._finalise(result)
        except OSError as exc:
            result["issues"].append(f"Could not read PBIX: {exc}")
            return self._finalise(result)

        if result["issues"]:
            result["recommendations"].append(
                "Use Power BI Desktop for Report Server to re-save a known-good PBIX before upload"
            )
        elif result["warnings"]:
            result["recommendations"].append(
                "Re-save from Power BI Desktop for Report Server if PBIRS still rejects the upload"
            )
        else:
            result["recommendations"].append(
                "PBIX package structure looks sound; PBIRS rejection is more likely version- or feature-related"
            )

        return self._finalise(result)

    def inspect_directory(self, input_dir: Path) -> dict[str, Any]:
        """Inspect all PBIX files under a converted export directory."""
        if input_dir.name.lower() == "powerbi":
            pbix_dir = input_dir
        else:
            pbix_dir = input_dir / "powerbi"

        files = sorted(pbix_dir.glob("*.pbix")) if pbix_dir.exists() else []
        items = [self.inspect(path) for path in files]

        counts = {
            "PASS": sum(1 for item in items if item["status"] == "PASS"),
            "WARN": sum(1 for item in items if item["status"] == "WARN"),
            "FAIL": sum(1 for item in items if item["status"] == "FAIL"),
        }
        common_issues: dict[str, int] = {}
        for item in items:
            for issue in item.get("issues", []):
                common_issues[issue] = common_issues.get(issue, 0) + 1
            for warning in item.get("warnings", []):
                common_issues[warning] = common_issues.get(warning, 0) + 1

        status = "PASS"
        if counts["FAIL"]:
            status = "FAIL"
        elif counts["WARN"]:
            status = "WARN"

        return {
            "summary": {
                "status": status,
                "total_files": len(items),
                "passed": counts["PASS"],
                "warned": counts["WARN"],
                "failed": counts["FAIL"],
                "input_dir": str(input_dir),
                "pbix_dir": str(pbix_dir),
            },
            "items": items,
            "common_issues": sorted(common_issues.items(), key=lambda kv: (-kv[1], kv[0])),
            "recommendations": self._directory_recommendations(items),
        }

    def generate_html_report(self, report: dict[str, Any], output_path: str | Path) -> None:
        """Render a standalone HTML report."""
        summary = report.get("summary", {})
        items = report.get("items", [])
        common_issues = report.get("common_issues", [])
        recommendations = report.get("recommendations", [])

        status = str(summary.get("status", "FAIL"))
        status_class = {
            "PASS": "badge-pass",
            "WARN": "badge-warn",
            "FAIL": "badge-fail",
        }.get(status, "badge-fail")

        rows = []
        for item in items:
            item_status = str(item.get("status", "FAIL"))
            css = {
                "PASS": "badge-pass",
                "WARN": "badge-warn",
                "FAIL": "badge-fail",
            }.get(item_status, "badge-fail")
            rows.append(
                f"<tr><td>{_esc(item.get('name', ''))}</td>"
                f"<td><span class='badge {css}'>{_esc(item_status)}</span></td>"
                f"<td>{_esc(item.get('score', 0))}</td>"
                f"<td>{_esc(', '.join(item.get('issues', [])) or 'None')}</td>"
                f"<td>{_esc(', '.join(item.get('warnings', [])) or 'None')}</td>"
                f"<td>{_esc(', '.join(item.get('recommendations', [])) or 'None')}</td></tr>"
            )

        issue_rows = "".join(
            f"<tr><td>{_esc(text)}</td><td>{count}</td></tr>" for text, count in common_issues
        ) or "<tr><td colspan='2' class='muted'>No recurring issues detected</td></tr>"

        html_doc = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
  <title>PBIX Compatibility Report</title>
  <style>
    :root {{
      --ink:#1f2937;
      --muted:#6b7280;
      --bg:#f8fafc;
      --card:#ffffff;
      --line:#e5e7eb;
      --pass:#166534;
      --passbg:#dcfce7;
      --warn:#854d0e;
      --warnbg:#fef3c7;
      --fail:#991b1b;
      --failbg:#fee2e2;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:'Segoe UI',system-ui,sans-serif; color:var(--ink); background:linear-gradient(180deg,#eff6ff 0%, var(--bg) 24%); }}
    .wrap {{ max-width:1280px; margin:0 auto; padding:24px; }}
    .hero {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:18px 20px; box-shadow:0 4px 16px rgba(15,23,42,0.05); }}
    .hero h1 {{ margin:0; font-size:1.55rem; }}
    .hero p {{ margin:8px 0 0; color:var(--muted); }}
    .badge {{ display:inline-block; margin-top:12px; padding:6px 10px; border-radius:999px; font-weight:700; font-size:.82rem; }}
    .badge-pass {{ background:var(--passbg); color:var(--pass); }}
    .badge-warn {{ background:var(--warnbg); color:var(--warn); }}
    .badge-fail {{ background:var(--failbg); color:var(--fail); }}
    .cards {{ margin-top:16px; display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; }}
    .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px; }}
    .card .v {{ font-size:1.35rem; font-weight:700; }}
    .card .k {{ font-size:.8rem; color:var(--muted); margin-top:4px; }}
    .section {{ margin-top:14px; background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px; }}
    .section h2 {{ margin:0 0 10px; font-size:1.04rem; }}
    table {{ width:100%; border-collapse:collapse; }}
    th,td {{ padding:8px 10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; font-size:.92rem; }}
    th {{ color:#374151; font-size:.82rem; letter-spacing:.02em; text-transform:uppercase; }}
    ul {{ margin:0; padding-left:18px; }}
    li {{ margin:6px 0; }}
    .muted {{ color:var(--muted); }}
    pre {{ margin:0; white-space:pre-wrap; word-break:break-word; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <section class=\"hero\">
      <h1>PBIX Compatibility Report</h1>
      <p>Pre-upload inspection for common PBIRS failure modes: malformed packages, missing core parts, and suspicious PBIX structure.</p>
      <span class=\"badge {status_class}\">{_esc(status)}</span>
    </section>

    <section class=\"cards\">
      <div class=\"card\"><div class=\"v\">{summary.get('total_files', 0)}</div><div class=\"k\">PBIX Files</div></div>
      <div class=\"card\"><div class=\"v\">{summary.get('passed', 0)}</div><div class=\"k\">Pass</div></div>
      <div class=\"card\"><div class=\"v\">{summary.get('warned', 0)}</div><div class=\"k\">Warn</div></div>
      <div class=\"card\"><div class=\"v\">{summary.get('failed', 0)}</div><div class=\"k\">Fail</div></div>
    </section>

    <section class=\"section\">
      <h2>Recommendations</h2>
      {_list_html(recommendations, empty='No recommendations generated')}
    </section>

    <section class=\"section\">
      <h2>Common Issues</h2>
      <table><thead><tr><th>Issue</th><th>Count</th></tr></thead><tbody>{issue_rows}</tbody></table>
    </section>

    <section class=\"section\">
      <h2>Per-file Details</h2>
      <table><thead><tr><th>Name</th><th>Status</th><th>Score</th><th>Issues</th><th>Warnings</th><th>Recommendations</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
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
    def _read_text(archive: zipfile.ZipFile, member: str) -> str | None:
        try:
            return archive.read(member).decode("utf-8", errors="replace")
        except KeyError:
            return None
        except OSError:
            return None

    @staticmethod
    def _extract_desktop_version_hint(custom_xml: str) -> str | None:
        marker = "PBIDesktopVersion"
        if marker not in custom_xml:
            return None
        start = custom_xml.find(marker)
        if start < 0:
            return None
        tail = custom_xml[start: start + 400]
        for token in ("<vt:lpwstr>", "<value>"):
            idx = tail.find(token)
            if idx >= 0:
                idx += len(token)
                end = tail.find("<", idx)
                if end > idx:
                    return tail[idx:end].strip()
        return "PBIDesktopVersion present"

    @staticmethod
    def _extract_connection_types(payload: Any) -> set[str]:
        """Collect all connection type values from a Connections JSON payload."""
        found: set[str] = set()

        def _walk(value: Any) -> None:
            if isinstance(value, dict):
                for key, inner in value.items():
                    if key.lower() == "connectiontype" and isinstance(inner, str):
                        found.add(inner.strip().lower())
                    else:
                        _walk(inner)
            elif isinstance(value, list):
                for inner in value:
                    _walk(inner)

        _walk(payload)
        return found

    @staticmethod
    def _finalise(result: dict[str, Any]) -> dict[str, Any]:
        if result["issues"]:
            result["status"] = "FAIL"
        elif result["warnings"]:
            result["status"] = "WARN"
        else:
            result["status"] = "PASS"

        issue_count = len(result["issues"])
        warning_count = len(result["warnings"])
        score = 100 - (issue_count * 35) - (warning_count * 10)
        result["score"] = max(0, score)
        return result

    @staticmethod
    def _directory_recommendations(items: list[dict[str, Any]]) -> list[str]:
        if not items:
            return ["No PBIX files found under input/powerbi"]

        recommendations: list[str] = []
        if any(item.get("status") == "FAIL" for item in items):
            recommendations.append(
                "Fix FAIL items first; malformed PBIX packages are the most common cause of HTTP 422 upload errors"
            )
        if any(item.get("warnings") for item in items):
            recommendations.append(
                "Warnings are not always fatal, but PBIRS often rejects PBIX files that were not re-saved with Power BI Desktop for Report Server"
            )
        recommendations.append(
            "If the package structure is sound and upload still fails, compare the PBIRS version with the Desktop RS version used to save the file"
        )
        recommendations.append(
            "Re-save a known-good PBIX from Power BI Desktop for Report Server before retrying the upload"
        )
        return recommendations


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _list_html(values: list[str], empty: str) -> str:
    if not values:
        return f'<p class="muted">{_esc(empty)}</p>'
    return "<ul>" + "".join(f"<li>{_esc(value)}</li>" for value in values) + "</ul>"