"""
RDL Analyser — parse RDL XML to detect features, custom code, assemblies,
and subreport dependencies.

Feeds into the assessment (v1.2) and the automatic RDL modifier.
"""

import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# RDL namespaces (SSRS 2016+)
_NS = {
    "rd": "http://schemas.microsoft.com/SQLServer/reporting/reportdesigner",
    "r08": "http://schemas.microsoft.com/sqlserver/reporting/2008/01/reportdefinition",
    "r10": "http://schemas.microsoft.com/sqlserver/reporting/2010/01/reportdefinition",
    "r16": "http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition",
}

# Features unsupported (or partially supported) in PBI Online paginated reports
UNSUPPORTED_FEATURES: dict[str, str] = {
    "Code": "Custom VB.NET code blocks",
    "CodeModules": "Custom assembly references",
    "CustomProperties": "Custom report properties (may be ignored)",
    "Classes": "Custom class instances",
}

# Features that need Premium/PPU but are otherwise supported
PREMIUM_FEATURES: dict[str, str] = {
    "Subreport": "Subreport reference (requires Premium)",
    "Drillthrough": "Drillthrough report link",
}


class RdlAnalyser:
    """Parse a single RDL file and extract feature metadata."""

    def __init__(self, rdl_path: str | Path):
        self.path = Path(rdl_path)
        self._tree: ET.ElementTree | None = None
        self._root: ET.Element | None = None
        self._ns: str = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(self) -> dict[str, Any]:
        """Full analysis of the RDL file."""
        self._parse()
        return {
            "path": str(self.path),
            "custom_code": self._detect_custom_code(),
            "custom_assemblies": self._detect_custom_assemblies(),
            "subreports": self._detect_subreports(),
            "datasources": self._detect_datasources(),
            "data_regions": self._count_data_regions(),
            "unsupported_features": self._detect_unsupported_features(),
            "parameters": self._detect_parameters(),
            "page_count_hint": self._page_count_hint(),
        }

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse(self) -> None:
        """Parse the RDL XML, auto-detecting the namespace."""
        self._tree = ET.parse(self.path)
        self._root = self._tree.getroot()
        # Auto-detect namespace from root tag  {http://...}Report
        match = re.match(r"\{(.+?)\}", self._root.tag)
        self._ns = match.group(1) if match else ""

    def _find(self, tag: str) -> list[ET.Element]:
        """Find all elements with *tag* under the detected namespace."""
        if self._root is None:
            return []
        if self._ns:
            return self._root.iter(f"{{{self._ns}}}{tag}")
        return self._root.iter(tag)

    def _findall(self, xpath: str) -> list[ET.Element]:
        if self._root is None:
            return []
        ns_xpath = xpath
        if self._ns:
            # Replace bare tag names with namespaced versions
            ns_xpath = re.sub(r"(?<![{/])(\w+)", rf"{{{self._ns}}}\1", xpath)
        return self._root.findall(ns_xpath)

    # ------------------------------------------------------------------
    # Feature detectors
    # ------------------------------------------------------------------

    def _detect_custom_code(self) -> dict:
        """Detect <Code> blocks containing custom VB.NET code."""
        code_elements = list(self._find("Code"))
        blocks: list[str] = []
        for el in code_elements:
            text = (el.text or "").strip()
            if text:
                blocks.append(text[:200])  # truncate for summary
        return {
            "present": len(blocks) > 0,
            "block_count": len(blocks),
            "snippets": blocks,
        }

    def _detect_custom_assemblies(self) -> dict:
        """Detect <CodeModules>/<CodeModule> custom assembly references."""
        modules = list(self._find("CodeModule"))
        names = [m.text.strip() for m in modules if m.text]
        # Also check <Classes>/<Class>
        classes = list(self._find("Class"))
        class_info = []
        for cls in classes:
            cn = cls.find(f"{{{self._ns}}}ClassName" if self._ns else "ClassName")
            inst = cls.find(f"{{{self._ns}}}InstanceName" if self._ns else "InstanceName")
            if cn is not None:
                class_info.append({
                    "class": cn.text or "",
                    "instance": inst.text if inst is not None else "",
                })
        return {
            "present": len(names) > 0 or len(class_info) > 0,
            "assemblies": names,
            "classes": class_info,
        }

    def _detect_subreports(self) -> list[dict]:
        """Detect <Subreport> elements and extract referenced report names."""
        subs: list[dict] = []
        for el in self._find("Subreport"):
            name_el = el.find(f"{{{self._ns}}}ReportName" if self._ns else "ReportName")
            report_name = name_el.text if name_el is not None else ""
            # Collect parameters passed to subreport
            params: list[str] = []
            for p in el.iter(f"{{{self._ns}}}SubreportParameter" if self._ns else "SubreportParameter"):
                pname_attr = p.get("Name", "")
                if pname_attr:
                    params.append(pname_attr)
            subs.append({"report_name": report_name, "parameters": params})
        return subs

    def _detect_datasources(self) -> list[dict]:
        """Detect <DataSource> definitions."""
        sources: list[dict] = []
        for el in self._find("DataSource"):
            name = el.get("Name", "")
            conn_el = el.find(f"{{{self._ns}}}ConnectionProperties" if self._ns else "ConnectionProperties")
            conn_str = ""
            provider = ""
            if conn_el is not None:
                cs_el = conn_el.find(f"{{{self._ns}}}ConnectString" if self._ns else "ConnectString")
                dp_el = conn_el.find(f"{{{self._ns}}}DataProvider" if self._ns else "DataProvider")
                conn_str = cs_el.text if cs_el is not None else ""
                provider = dp_el.text if dp_el is not None else ""
            sources.append({"name": name, "provider": provider, "connection_string": conn_str or ""})
        return sources

    def _count_data_regions(self) -> dict[str, int]:
        """Count Tablix, Chart, Map, Gauge, and other data regions."""
        counts: dict[str, int] = {}
        for tag in ("Tablix", "Chart", "Map", "GaugePanel", "DataBar", "Sparkline", "Indicator"):
            n = len(list(self._find(tag)))
            if n:
                counts[tag] = n
        return counts

    def _detect_unsupported_features(self) -> list[dict]:
        """Scan for features that are unsupported or problematic in PBI Online."""
        found: list[dict] = []
        for tag, description in UNSUPPORTED_FEATURES.items():
            elements = list(self._find(tag))
            if elements:
                found.append({"feature": tag, "description": description, "count": len(elements)})
        return found

    def _detect_parameters(self) -> list[dict]:
        """Detect report parameters."""
        params: list[dict] = []
        for el in self._find("ReportParameter"):
            name = el.get("Name", "")
            dt_el = el.find(f"{{{self._ns}}}DataType" if self._ns else "DataType")
            data_type = dt_el.text if dt_el is not None else "String"
            params.append({"name": name, "data_type": data_type})
        return params

    def _page_count_hint(self) -> str:
        """Rough estimate based on body/page breaks."""
        breaks = list(self._find("PageBreak"))
        if len(breaks) > 10:
            return "complex (10+ page breaks)"
        if len(breaks) > 3:
            return "moderate (4-10 page breaks)"
        return "simple (0-3 page breaks)"


# ------------------------------------------------------------------
# Batch analyser
# ------------------------------------------------------------------

def analyse_rdl_directory(directory: str | Path) -> list[dict]:
    """Analyse all .rdl files in a directory tree."""
    results: list[dict] = []
    for rdl_path in Path(directory).rglob("*.rdl"):
        try:
            analyser = RdlAnalyser(rdl_path)
            results.append(analyser.analyse())
        except ET.ParseError as e:
            logger.error("Failed to parse %s: %s", rdl_path, e)
            results.append({"path": str(rdl_path), "error": str(e)})
    return results
