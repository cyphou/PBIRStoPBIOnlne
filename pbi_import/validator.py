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
            "binding_parity": self._validate_binding_parity(workspace_id, converted_dir),
            "refresh_status": self._validate_refresh(workspace_id),
            "permissions": self._validate_permissions(workspace_id),
            "custom_visuals": self._validate_custom_visuals(catalog, workspace_id),
            "overall": "PASS",
            "issues": [],
        }

        # Determine overall status
        for key in (
            "report_count",
            "datasource_binding",
            "binding_parity",
            "refresh_status",
            "permissions",
            "custom_visuals",
        ):
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

    def _validate_binding_parity(self, workspace_id: str, converted_dir: str) -> dict:
        """Validate target datasource bindings against source connection expectations."""
        ds_path = Path(converted_dir) / "datasources.json"
        if not ds_path.exists():
            return {
                "status": "PASS",
                "message": "No datasource baseline file found; parity check skipped",
            }

        try:
            payload = json.loads(ds_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            return {"status": "WARN", "message": f"Could not parse datasource baseline: {e}"}

        expected_summary = payload.get("connection_summary", {}) if isinstance(payload, dict) else {}
        if not isinstance(expected_summary, dict):
            expected_summary = {}
        expected_count = sum(int(v) for v in expected_summary.values() if isinstance(v, int))

        if expected_count <= 0:
            return {
                "status": "PASS",
                "message": "No source datasource expectations found in baseline",
            }

        try:
            datasets = self.client.list_datasets(workspace_id)
        except Exception as e:
            return {"status": "FAIL", "message": f"Could not list datasets for parity check: {e}"}

        bound_count = 0
        for ds in datasets:
            ds_id = ds.get("id", "")
            if not ds_id:
                continue
            try:
                target_sources = self.client.get_dataset_datasources(ds_id)
            except Exception:
                continue
            if not isinstance(target_sources, list):
                continue
            for src in target_sources:
                if src.get("gatewayId") or src.get("datasourceId"):
                    bound_count += 1

        if bound_count < expected_count:
            return {
                "status": "WARN",
                "message": (
                    f"Binding parity mismatch: source expects ~{expected_count} datasource refs, "
                    f"target has {bound_count} bound refs. "
                    "Review gateway mapping and run --map-gateway / --gateway-auto."
                ),
            }

        return {
            "status": "PASS",
            "message": f"Binding parity OK: {bound_count}/{expected_count} refs bound",
        }

    def _validate_custom_visuals(self, catalog: dict, workspace_id: str) -> dict:
        """Validate custom visuals used by source content are available in target tenant/workspace."""
        required = self._collect_required_custom_visuals(catalog)
        if not required:
            return {"status": "PASS", "message": "No custom visuals detected in source metadata"}

        available = self._list_available_custom_visuals(workspace_id)
        if not available:
            return {
                "status": "WARN",
                "message": (
                    f"Detected {len(required)} required custom visual(s), but target catalog could not be read. "
                    "Ensure tenant/org visuals are published and accessible."
                ),
            }

        missing = sorted(required - available)
        if missing:
            preview = ", ".join(missing[:5])
            suffix = "..." if len(missing) > 5 else ""
            return {
                "status": "WARN",
                "message": (
                    f"Missing {len(missing)} custom visual(s): {preview}{suffix}. "
                    "Install/publish visuals in AppSource or Org visuals before go-live."
                ),
            }

        return {
            "status": "PASS",
            "message": f"All required custom visuals available ({len(required)})",
        }

    @staticmethod
    def _collect_required_custom_visuals(catalog: dict) -> set[str]:
        required: set[str] = set()
        for item in catalog.get("items", []):
            visuals = item.get("custom_visuals", [])
            if not isinstance(visuals, list):
                continue
            for v in visuals:
                if isinstance(v, str) and v.strip():
                    required.add(v.strip())
                elif isinstance(v, dict):
                    for key in ("name", "id", "visualName", "visualId"):
                        val = v.get(key)
                        if isinstance(val, str) and val.strip():
                            required.add(val.strip())
                            break
        return required

    def _list_available_custom_visuals(self, workspace_id: str) -> set[str]:
        candidates = (
            ("list_custom_visuals", (workspace_id,)),
            ("list_custom_visuals", tuple()),
            ("list_org_visuals", tuple()),
            ("get_available_custom_visuals", (workspace_id,)),
            ("get_available_custom_visuals", tuple()),
        )

        for method_name, args in candidates:
            method = getattr(self.client, method_name, None)
            if method is None:
                continue
            try:
                payload = method(*args)
            except Exception:
                continue
            names = self._normalise_visual_name_payload(payload)
            if names:
                return names
        return set()

    @staticmethod
    def _normalise_visual_name_payload(payload: Any) -> set[str]:
        visuals = payload.get("value") if isinstance(payload, dict) else payload
        if not isinstance(visuals, list):
            return set()

        names: set[str] = set()
        for v in visuals:
            if isinstance(v, str) and v.strip():
                names.add(v.strip())
            elif isinstance(v, dict):
                for key in ("name", "id", "visualName", "displayName"):
                    val = v.get(key)
                    if isinstance(val, str) and val.strip():
                        names.add(val.strip())
                        break
        return names

    # ------------------------------------------------------------------
    # CLI-friendly helpers
    # ------------------------------------------------------------------

    def validate_all(self, input_dir: str, workspace_id: str) -> dict:
        """Run :meth:`validate` against catalog metadata on disk.

        Reads ``input_dir/export_manifest.json`` (or ``inventory.json``) to
        recover the source catalog, then returns the standard validation
        result enriched with ``passed`` / ``failed`` counters.
        """
        catalog = self._load_catalog(Path(input_dir))
        result = self.validate(catalog, workspace_id, input_dir)

        checks = (
            "report_count",
            "datasource_binding",
            "binding_parity",
            "refresh_status",
            "permissions",
            "custom_visuals",
        )
        passed = sum(1 for k in checks if result.get(k, {}).get("status") == "PASS")
        failed = sum(1 for k in checks if result.get(k, {}).get("status") == "FAIL")
        result["passed"] = passed
        result["failed"] = failed
        return result

    @staticmethod
    def _load_catalog(input_dir: Path) -> dict:
        for candidate in ("export_manifest.json", "inventory.json"):
            path = input_dir / candidate
            if not path.exists():
                continue
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
            if candidate == "export_manifest.json":
                return data.get("catalog", {})
            return data
        logger.warning("No catalog found in %s — validation will run with empty catalog", input_dir)
        return {}

    def generate_html_report(self, result: dict, output_path: str) -> None:
        """Render the validation result as a standalone HTML page."""
        checks = (
            "report_count",
            "datasource_binding",
            "binding_parity",
            "refresh_status",
            "permissions",
            "custom_visuals",
        )
        rows = []
        for key in checks:
            check = result.get(key, {})
            status = check.get("status", "UNKNOWN")
            css = {
                "PASS": "badge-green",
                "WARN": "badge-yellow",
                "FAIL": "badge-red",
            }.get(status, "badge-grey")
            rows.append(
                f"<tr><td>{_esc(key)}</td>"
                f"<td><span class='badge {css}'>{_esc(status)}</span></td>"
                f"<td>{_esc(check.get('message', ''))}</td></tr>"
            )

        overall = result.get("overall", "UNKNOWN")
        overall_css = {
            "PASS": "badge-green",
            "WARN": "badge-yellow",
            "FAIL": "badge-red",
        }.get(overall, "badge-grey")

        issues_html = "".join(f"<li>{_esc(i)}</li>" for i in result.get("issues", []))

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>PBIRS → PBI Online Validation Report</title>
<style>
 body {{ font-family: 'Segoe UI', system-ui, sans-serif; background:#FAFAFA; color:#252423; margin:0; }}
 .header {{ background:linear-gradient(135deg,#252423,#3B3A39); color:white; padding:2rem; }}
 .container {{ max-width:1100px; margin:0 auto; padding:1.5rem; }}
 .section {{ background:white; border-radius:8px; padding:1.5rem; margin:1rem 0; box-shadow:0 1px 3px rgba(0,0,0,.1); }}
 table {{ width:100%; border-collapse:collapse; }}
 th,td {{ padding:.6rem .8rem; text-align:left; border-bottom:1px solid #E5E7EB; }}
 th {{ background:#F3F4F6; font-weight:600; font-size:.85rem; }}
 .badge {{ display:inline-block; padding:2px 10px; border-radius:12px; font-size:.8rem; font-weight:600; }}
 .badge-green {{ background:#DCFCE7; color:#166534; }}
 .badge-yellow {{ background:#FEF9C3; color:#854D0E; }}
 .badge-red {{ background:#FEE2E2; color:#991B1B; }}
 .badge-grey {{ background:#E5E7EB; color:#374151; }}
 ul {{ margin-left:1.2rem; }}
</style>
</head>
<body>
 <div class="header">
   <h1>PBIRS → PBI Online Validation</h1>
   <p>Post-migration fidelity report</p>
 </div>
 <div class="container">
   <div class="section">
     <h2>Overall: <span class="badge {overall_css}">{_esc(overall)}</span></h2>
     <p>{result.get('passed', 0)} checks passed · {result.get('failed', 0)} checks failed</p>
   </div>
   <div class="section">
     <h2>Checks</h2>
     <table>
       <thead><tr><th>Check</th><th>Status</th><th>Message</th></tr></thead>
       <tbody>{''.join(rows)}</tbody>
     </table>
   </div>
   <div class="section">
     <h2>Issues</h2>
     <ul>{issues_html or '<li>None</li>'}</ul>
   </div>
 </div>
</body>
</html>"""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)


def _esc(text: Any) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
