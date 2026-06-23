"""Mobile Report best-effort extractor.

PBIRS Mobile Reports (.rsmobile) are deprecated and not migratable as-is.
This extractor parses the visual layout to produce a *scaffold* manifest that
gives the customer a head start on rebuilding the report as a PBI mobile-
optimised report.

Output for each mobile report:
    {
      "source": "...",
      "title": "...",
      "tiles": [{"type":..., "title":..., "data_field":...}, ...],
      "warnings": [...],
      "scaffold_path": ".../report.scaffold.json",
    }
"""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_KNOWN_VISUALS = {
    "Gauge": "gauge",
    "Chart": "chart",
    "Indicator": "kpi",
    "Map": "map",
    "Navigator": "slicer",
    "DataGrid": "table",
    "Image": "image",
    "Text": "textbox",
}


class MobileReportExtractor:
    """Best-effort scaffold builder for PBIRS Mobile Reports."""

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)

    def extract(self, source: str | Path) -> dict[str, Any]:
        """Extract one .rsmobile / .json layout into a scaffold."""
        src = Path(source)
        if not src.exists():
            return {
                "source": str(src),
                "warnings": [f"file not found: {src}"],
                "tiles": [],
            }

        text = src.read_text(encoding="utf-8", errors="replace")
        title = src.stem
        tiles: list[dict[str, Any]] = []
        warnings: list[str] = []

        # Mobile Reports use a layout JSON inside the package — but
        # historically a few are exported as raw XML.  Try both shapes.
        try:
            data = json.loads(text)
            tiles, t_warns = self._tiles_from_json(data)
            warnings.extend(t_warns)
            title = data.get("ReportName") or data.get("Title") or title
        except json.JSONDecodeError:
            try:
                root = ET.fromstring(text)
                tiles, t_warns = self._tiles_from_xml(root)
                warnings.extend(t_warns)
                title_attr = root.attrib.get("Title")
                if title_attr:
                    title = title_attr
            except ET.ParseError as e:
                warnings.append(f"unparseable layout: {e}")

        scaffold = {
            "title": title,
            "source": str(src),
            "tiles": tiles,
            "rebuild_target": "PowerBI mobile-optimised report",
            "warnings": warnings,
            "notes": (
                "Mobile Reports are deprecated. Use this scaffold as a "
                "starting point — open Power BI Desktop, recreate each tile "
                "with the matching visual, then bind to your migrated dataset."
            ),
        }
        scaffold_path = self.output_dir / f"{src.stem}.scaffold.json"
        scaffold_path.parent.mkdir(parents=True, exist_ok=True)
        with scaffold_path.open("w", encoding="utf-8") as f:
            json.dump(scaffold, f, indent=2)
        scaffold["scaffold_path"] = str(scaffold_path)
        logger.info("Mobile scaffold: %s tiles=%d", src.name, len(tiles))
        return scaffold

    def extract_all(self, catalog: dict, source_dir: str | Path) -> list[dict[str, Any]]:
        """Process every MobileReport item in ``catalog``."""
        mobile = (
            catalog.get("mobile_reports")
            or [i for i in catalog.get("items", []) if i.get("Type") == "MobileReport"]
        )
        results: list[dict[str, Any]] = []
        src_root = Path(source_dir)
        for item in mobile:
            name = item.get("Name") or item.get("name") or "report"
            candidate = self._locate(src_root, name)
            if candidate is None:
                results.append({
                    "source": str(src_root / name),
                    "warnings": ["mobile report file not found in export"],
                    "tiles": [],
                    "title": name,
                })
                continue
            results.append(self.extract(candidate))
        return results

    def _locate(self, root: Path, name: str) -> Path | None:
        for ext in (".rsmobile", ".json", ".xml"):
            candidate = root / f"{name}{ext}"
            if candidate.exists():
                return candidate
        # Fall back to a glob
        for ext in ("*.rsmobile", "*.json"):
            for f in root.rglob(ext):
                if f.stem == name:
                    return f
        return None

    def _tiles_from_json(self, data: Any) -> tuple[list[dict], list[str]]:
        tiles: list[dict] = []
        warnings: list[str] = []
        nodes = []
        if isinstance(data, dict):
            for key in ("Tiles", "tiles", "Visuals", "VisualContainers"):
                nodes = data.get(key) or nodes
                if nodes:
                    break
        for node in nodes or []:
            if not isinstance(node, dict):
                continue
            vis_type = node.get("Type") or node.get("VisualType") or "Unknown"
            tiles.append({
                "type": _KNOWN_VISUALS.get(vis_type, "unknown"),
                "title": node.get("Title") or node.get("Name") or vis_type,
                "data_field": node.get("DataField") or node.get("Field"),
                "raw_type": vis_type,
            })
            if vis_type not in _KNOWN_VISUALS:
                warnings.append(f"unknown visual type: {vis_type}")
        return tiles, warnings

    def _tiles_from_xml(self, root: ET.Element) -> tuple[list[dict], list[str]]:
        tiles: list[dict] = []
        warnings: list[str] = []
        ns_strip = re.compile(r"^\{[^}]+\}")
        for el in root.iter():
            tag = ns_strip.sub("", el.tag)
            if tag in _KNOWN_VISUALS or tag.endswith("Tile"):
                tiles.append({
                    "type": _KNOWN_VISUALS.get(tag, "unknown"),
                    "title": el.attrib.get("Title") or el.attrib.get("Name") or tag,
                    "raw_type": tag,
                })
        return tiles, warnings
