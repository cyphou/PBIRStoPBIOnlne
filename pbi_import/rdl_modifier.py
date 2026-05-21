"""
RDL Modifier — automatically remove or neutralise unsupported RDL features
for PBI Online paginated reports.

Modifies a copy of the RDL file; the original is never altered.
"""

import logging
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class RdlModifier:
    """Remove unsupported features from an RDL file for PBI Online compatibility."""

    # Tags that will be stripped entirely
    STRIP_TAGS = {"Code", "CodeModules", "Classes"}

    # Tags whose text will be blanked but element kept
    BLANK_TAGS: set[str] = set()

    def __init__(self, rdl_path: str | Path):
        self.path = Path(rdl_path)
        self._tree: ET.ElementTree | None = None
        self._root: ET.Element | None = None
        self._ns: str = ""
        self._changes: list[str] = []

    def modify(self, output_path: str | Path | None = None) -> dict:
        """Modify the RDL and write to *output_path*.

        If *output_path* is None, writes next to the original with a
        ``.modified.rdl`` suffix.

        Returns a summary of changes applied.
        """
        self._parse()
        self._changes.clear()

        self._strip_custom_code()
        self._strip_custom_assemblies()
        self._strip_classes()
        self._neutralise_file_share_delivery()

        out = Path(output_path) if output_path else self.path.with_suffix(".modified.rdl")
        out.parent.mkdir(parents=True, exist_ok=True)

        # Re-register the namespace so output is clean
        if self._ns:
            ET.register_namespace("", self._ns)
        self._tree.write(str(out), xml_declaration=True, encoding="utf-8")

        logger.info("Modified RDL written to %s (%d changes)", out, len(self._changes))
        return {
            "source": str(self.path),
            "output": str(out),
            "changes": list(self._changes),
            "change_count": len(self._changes),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse(self) -> None:
        self._tree = ET.parse(self.path)
        self._root = self._tree.getroot()
        match = re.match(r"\{(.+?)\}", self._root.tag)
        self._ns = match.group(1) if match else ""

    def _qualified(self, tag: str) -> str:
        return f"{{{self._ns}}}{tag}" if self._ns else tag

    def _strip_custom_code(self) -> None:
        """Remove <Code> blocks."""
        for el in list(self._root.iter(self._qualified("Code"))):
            parent = self._find_parent(el)
            if parent is not None:
                parent.remove(el)
                self._changes.append("Removed <Code> block (custom VB.NET code)")

    def _strip_custom_assemblies(self) -> None:
        """Remove <CodeModules> (assembly references)."""
        for el in list(self._root.iter(self._qualified("CodeModules"))):
            parent = self._find_parent(el)
            if parent is not None:
                parent.remove(el)
                self._changes.append("Removed <CodeModules> (custom assembly references)")

    def _strip_classes(self) -> None:
        """Remove <Classes> (custom class instances)."""
        for el in list(self._root.iter(self._qualified("Classes"))):
            parent = self._find_parent(el)
            if parent is not None:
                parent.remove(el)
                self._changes.append("Removed <Classes> (custom class instances)")

    def _neutralise_file_share_delivery(self) -> None:
        """Remove file-share delivery extension references if embedded."""
        for el in list(self._root.iter(self._qualified("DeliveryExtension"))):
            if el.text and "FileShare" in el.text:
                parent = self._find_parent(el)
                if parent is not None:
                    parent.remove(el)
                    self._changes.append("Removed FileShare delivery extension reference")

    def _find_parent(self, target: ET.Element) -> ET.Element | None:
        """Find the parent of *target* (ElementTree has no parent pointer)."""
        for parent in self._root.iter():
            for child in parent:
                if child is target:
                    return parent
        return None


# ------------------------------------------------------------------
# Batch modifier
# ------------------------------------------------------------------

def modify_rdl_directory(
    input_dir: str | Path,
    output_dir: str | Path,
) -> list[dict]:
    """Modify all .rdl files in *input_dir*, writing results to *output_dir*."""
    results: list[dict] = []
    in_path = Path(input_dir)
    out_path = Path(output_dir)
    for rdl in in_path.rglob("*.rdl"):
        relative = rdl.relative_to(in_path)
        dest = out_path / relative
        try:
            modifier = RdlModifier(rdl)
            result = modifier.modify(dest)
            results.append(result)
        except ET.ParseError as e:
            logger.error("Failed to parse %s: %s", rdl, e)
            # Copy unmodified on parse failure
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(rdl, dest)
            results.append({"source": str(rdl), "output": str(dest), "error": str(e)})
    return results
