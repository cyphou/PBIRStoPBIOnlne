"""Environment and feature capability reporting for migration readiness."""

from __future__ import annotations

import importlib.util
import platform
import sys
import time
from pathlib import Path
from typing import Any


def _has_module(name: str) -> bool:
    """Return True when a module is importable in the current environment."""
    return importlib.util.find_spec(name) is not None


def _entry(cap_id: str, state: str, detail: str) -> dict[str, str]:
    """Build one capability row."""
    return {"id": cap_id, "state": state, "detail": detail}


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

    capabilities = [
        _entry("core.python_3_12_plus", "ready" if sys.version_info >= (3, 12) else "blocked",
               f"Running Python {platform.python_version()}"),
        _entry("core.import_deploy_optional_deps", auth_state, auth_detail),
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
        _entry("limitation.large_pbix_over_1gb", "planned",
               "Enhanced >1GB PBIX import path is not yet fully implemented"),
        _entry("limitation.data_driven_query_bridge", "planned",
               "PBIRS REST does not expose query text; DB-assisted bridge is still pending"),
        _entry("limitation.security_inheritance_db_bridge", "planned",
               "Some PBIRS security inheritance edge cases still require DB-assisted resolution"),
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
