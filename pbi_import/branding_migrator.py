"""
Branding Migrator — moves PBIRS folder portal branding into PBI workspace branding.

PBIRS supports per-folder portal branding (logo, colours, theme). PBI Online
exposes workspace-level branding via the ``Admin/Workspaces`` API. This module
takes a brand descriptor extracted from PBIRS and emits a PBI-shaped payload
plus an optional companion theme JSON for report-level theming.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class BrandingMigrator:
    """Translate PBIRS branding into PBI workspace + report theming payloads."""

    def __init__(self, default_palette: list[str] | None = None):
        self.default_palette = default_palette or [
            "#0078D4", "#106EBE", "#005A9E",
            "#F2F2F2", "#605E5C", "#323130",
        ]

    def to_workspace_payload(self, brand: dict) -> dict:
        """Build the PBI ``workspace`` update payload from PBIRS *brand* descriptor."""
        payload: dict = {}
        if name := brand.get("name"):
            payload["name"] = name
        if description := brand.get("description"):
            payload["description"] = description

        logo = brand.get("logo")
        if logo:
            payload["logoImageBase64"] = _ensure_base64(logo)
        return payload

    def to_report_theme(self, brand: dict) -> dict:
        """Build a PBI ``ReportTheme`` JSON document from *brand*."""
        palette = self._resolve_palette(brand)
        return {
            "name": brand.get("name", "PBIRS Theme"),
            "dataColors": palette,
            "background": brand.get("background") or "#FFFFFF",
            "foreground": brand.get("foreground") or "#252423",
            "tableAccent": palette[0],
        }

    def write_theme(self, brand: dict, output_dir: str | Path) -> Path:
        """Write the theme JSON to *output_dir* and return its path."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        theme = self.to_report_theme(brand)
        target = out / f"{_safe(brand.get('name', 'theme'))}.theme.json"
        target.write_text(json.dumps(theme, indent=2), encoding="utf-8")
        logger.info("Wrote theme to %s", target)
        return target

    def migrate(self, brand: dict, workspace_id: str, output_dir: str | Path,
                dry_run: bool = False, pbi_client=None) -> dict:
        """Full migration: emit theme file + (optionally) push workspace payload."""
        theme_path = self.write_theme(brand, output_dir)
        payload = self.to_workspace_payload(brand)
        result = {
            "workspace_id": workspace_id,
            "theme_file": str(theme_path),
            "payload_keys": sorted(payload.keys()),
            "status": "prepared",
        }
        if dry_run or not pbi_client or not payload:
            return result
        try:
            pbi_client.update_workspace(workspace_id, payload)
            result["status"] = "applied"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Workspace branding update failed: %s", exc)
            result["status"] = "failed"
            result["error"] = str(exc)
        return result

    # ------------------------------------------------------------------

    def _resolve_palette(self, brand: dict) -> list[str]:
        raw = brand.get("palette") or brand.get("colors") or []
        valid = [c for c in raw if isinstance(c, str) and HEX_RE.match(c)]
        if not valid:
            return list(self.default_palette)
        # Pad to at least 6 colours so PBI doesn't reject the theme.
        while len(valid) < 6:
            valid.append(self.default_palette[len(valid) % len(self.default_palette)])
        return valid


def _ensure_base64(logo: str) -> str:
    """Accept either a base64 string or a filesystem path; return base64."""
    p = Path(logo)
    if p.is_file():
        return base64.b64encode(p.read_bytes()).decode("ascii")
    return logo


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)
