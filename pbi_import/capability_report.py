"""Environment and feature capability reporting for migration readiness."""

from __future__ import annotations

import importlib.util
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any


def _has_module(name: str) -> bool:
    """Return True when a module is importable in the current environment."""
    return importlib.util.find_spec(name) is not None


def _has_attr(module_name: str, attr: str) -> bool:
    """Return True when a module exists and exposes a given attribute."""
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return False
    return hasattr(module, attr)


def _entry(cap_id: str, state: str, detail: str) -> dict[str, str]:
    """Build one capability row."""
    return {"id": cap_id, "state": state, "detail": detail}


def _candidate_powerbi_desktop_rs_paths() -> list[Path]:
    """Return likely Power BI Desktop RS executable locations on Windows."""
    candidates: list[Path] = []
    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        root = os.environ.get(env_name)
        if not root:
            continue
        candidates.append(Path(root) / "Microsoft Power BI Desktop RS" / "bin" / "PBIDesktop.exe")
    return candidates


def _desktop_rs_workspace_root() -> Path:
    """Return the local Analysis Services workspace root used by Desktop RS."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Microsoft" / "Power BI Desktop SSRS" / "AnalysisServicesWorkspaces"
    return Path.home() / "AppData" / "Local" / "Microsoft" / "Power BI Desktop SSRS" / "AnalysisServicesWorkspaces"


def _powerbi_desktop_rs_capabilities() -> list[dict[str, str]]:
    """Check local Power BI Desktop RS install and active authoring session state."""
    install_path = next((path for path in _candidate_powerbi_desktop_rs_paths() if path.exists()), None)
    workspace_root = _desktop_rs_workspace_root()
    workspace_exists = workspace_root.exists()
    port_files = list(workspace_root.rglob("msmdsrv.port.txt")) if workspace_exists else []

    capabilities = []
    if install_path:
        capabilities.append(
            _entry(
                "tool.powerbi_desktop_rs.installed",
                "ready",
                f"Found PBIDesktop.exe at {install_path}",
            )
        )
    else:
        capabilities.append(
            _entry(
                "tool.powerbi_desktop_rs.installed",
                "blocked",
                "Power BI Desktop RS not found in Program Files",
            )
        )

    if workspace_exists:
        detail = f"AnalysisServicesWorkspaces root: {workspace_root}"
        if port_files:
            detail += f"; live AS session detected ({port_files[0].parent.name})"
        else:
            detail += "; no live AS session detected"
        capabilities.append(
            _entry(
                "tool.powerbi_desktop_rs.authoring_session",
                "ready" if port_files else "partial",
                detail,
            )
        )
    else:
        capabilities.append(
            _entry(
                "tool.powerbi_desktop_rs.authoring_session",
                "blocked",
                f"AnalysisServicesWorkspaces root not found at {workspace_root}",
            )
        )

    return capabilities


def generate_capability_report(args: Any) -> dict[str, Any]:
    """Create a capability report aligned with roadmap and known limitations."""
    output_root = Path(getattr(args, "output_dir", None) or "artifacts")

    azure_auth_deps = {
        "azure-identity": _has_module("azure.identity"),
        "requests": _has_module("requests"),
        "msal": _has_module("msal"),
    }

    all_auth_deps = all(azure_auth_deps.values())
    any_auth_deps = any(azure_auth_deps.values())
    if all_auth_deps:
        auth_state = "ready"
        auth_detail = "All optional import/deploy auth dependencies are installed"
    elif any_auth_deps:
        auth_state = "partial"
        missing = [k for k, v in azure_auth_deps.items() if not v]
        auth_detail = "Missing optional dependency(s): " + ", ".join(missing)
    else:
        auth_state = "partial"
        auth_detail = "No optional import/deploy auth dependencies detected"

    has_large_file_impl = (
        _has_module("pbi_import.large_file_handler")
        and _has_attr("pbi_import.report_publisher", "ReportPublisher")
        and _has_attr("pbi_import.deploy.pbi_client", "PBIClient")
    )

    db_conn = getattr(args, "reportserver_db_conn", None) or os.getenv("REPORTSERVER_DB_CONN")
    has_query_bridge_impl = _has_module("pbi_import.reportserver_db_bridge")
    has_security_bridge_impl = _has_module("pbirs_export.security_inheritance_resolver")

    if has_query_bridge_impl and db_conn:
        query_bridge_state = "ready"
        query_bridge_detail = "DB-assisted query bridge implemented and connection string is configured"
    elif has_query_bridge_impl:
        query_bridge_state = "partial"
        query_bridge_detail = "DB-assisted query bridge implemented; set --reportserver-db-conn (or REPORTSERVER_DB_CONN) to enable"
    else:
        query_bridge_state = "planned"
        query_bridge_detail = "PBIRS REST does not expose query text; DB-assisted bridge is still pending"

    if has_security_bridge_impl and db_conn:
        security_bridge_state = "ready"
        security_bridge_detail = "DB-assisted security inheritance resolver implemented and connection string is configured"
    elif has_security_bridge_impl:
        security_bridge_state = "partial"
        security_bridge_detail = "DB-assisted security inheritance resolver implemented; set --reportserver-db-conn (or REPORTSERVER_DB_CONN) to enable"
    else:
        security_bridge_state = "planned"
        security_bridge_detail = "Some PBIRS security inheritance edge cases still require DB-assisted resolution"

    capabilities = [
        _entry("core.python_3_12_plus", "ready" if sys.version_info >= (3, 12) else "blocked",
               f"Running Python {platform.python_version()}"),
        _entry("core.import_deploy_optional_deps", auth_state, auth_detail),
         *_powerbi_desktop_rs_capabilities(),
        _entry("feature.mobile_scaffold", "ready" if _has_module("pbi_import.mobile_extractor") else "blocked",
               "Mobile report scaffold extraction (--migrate-mobile)"),
        _entry("feature.ad_bridge", "ready" if _has_module("pbi_import.ad_group_bridge") else "blocked",
               "AD principal discovery and bridge CSV generation (--ad-bridge)"),
        _entry("feature.gateway_auto_create", "ready" if _has_module("pbi_import.gateway_autocreate") else "blocked",
               "Gateway datasource auto-create from shared .rds (--gateway-auto)"),
        _entry("feature.dax_autofix", "ready" if _has_module("pbi_import.dax_auto_fixer") else "blocked",
               "Safe DAX rewrites and diff reports (--dax-autofix)"),
        _entry("feature.capability_report", "ready",
               "Environment capability report command (--capability-report)"),
         _entry(
             "limitation.large_pbix_over_1gb",
             "ready" if has_large_file_impl else "planned",
             "Enhanced >1GB PBIX import path is implemented (chunked upload via temporary upload location)"
             if has_large_file_impl
             else "Enhanced >1GB PBIX import path is not yet fully implemented",
         ),
         _entry("limitation.data_driven_query_bridge", query_bridge_state, query_bridge_detail),
         _entry("limitation.security_inheritance_db_bridge", security_bridge_state, security_bridge_detail),
    ]

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "output_root": str(output_root),
        "optional_dependencies": azure_auth_deps,
        "capabilities": capabilities,
    }


def render_capability_report(report: dict[str, Any]) -> str:
    """Render report in a readable plain-text table for CLI output."""
    lines: list[str] = []
    lines.append("CAPABILITY REPORT")
    lines.append("=" * 70)
    lines.append(f"Generated: {report.get('generated_at', '')}")
    lines.append(f"Platform:  {report.get('platform', '')}")
    lines.append(f"Python:    {report.get('python_version', '')}")
    lines.append(f"Root:      {report.get('output_root', '')}")
    lines.append("-" * 70)
    lines.append(f"{'State':<10} {'Capability':<42} Detail")
    lines.append("-" * 70)

    for item in report.get("capabilities", []):
        state = str(item.get("state", "")).upper()
        cap_id = str(item.get("id", ""))
        detail = str(item.get("detail", ""))
        lines.append(f"{state:<10} {cap_id:<42} {detail}")

    lines.append("=" * 70)
    return "\n".join(lines)
