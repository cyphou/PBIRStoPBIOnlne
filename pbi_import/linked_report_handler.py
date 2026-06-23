"""
Linked Report Handler — converts PBIRS Linked Reports into PBI Online artefacts.

A PBIRS Linked Report is a saved snapshot of a base report with overridden
parameter defaults. Three migration strategies are supported:

* ``bookmarks`` — emit a bookmarks JSON payload alongside the base PBIX so the
  parameter set can be applied as a Power BI bookmark.
* ``paginated`` — emit a parameterised paginated-report variant (an RDL
  shadow file with the overridden default values baked in).
* ``skip`` — record the link and skip migration.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

VALID_STRATEGIES = {"bookmarks", "paginated", "skip"}


class LinkedReportHandler:
    """Detect and convert PBIRS linked reports."""

    def __init__(self, strategy: str = "bookmarks"):
        if strategy not in VALID_STRATEGIES:
            raise ValueError(
                f"Unknown linked-report strategy '{strategy}'. "
                f"Expected one of {sorted(VALID_STRATEGIES)}."
            )
        self.strategy = strategy

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect(self, catalog: list[dict]) -> list[dict]:
        """Return every catalog entry that is a Linked Report."""
        return [
            item for item in catalog
            if (item.get("Type") == "LinkedReport"
                or item.get("type") == "LinkedReport"
                or item.get("LinkSourceId") or item.get("linkSourceId"))
        ]

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def convert(self, item: dict, output_dir: str | Path) -> dict:
        """Convert a single linked-report item using the configured strategy."""
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        name = item.get("Name") or item.get("name") or "linked_report"
        source_id = item.get("LinkSourceId") or item.get("linkSourceId") or ""
        parameters = item.get("Parameters") or item.get("parameters") or []

        if self.strategy == "skip":
            logger.info("Skipping linked report '%s'", name)
            return {"name": name, "strategy": "skip", "status": "skipped"}

        if self.strategy == "bookmarks":
            payload = self._make_bookmark(name, source_id, parameters)
            target = out_dir / f"{_safe(name)}.bookmark.json"
            target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return {
                "name": name, "strategy": "bookmarks",
                "status": "written", "output": str(target),
                "source_id": source_id,
            }

        # paginated strategy
        payload = self._make_paginated_overrides(name, source_id, parameters)
        target = out_dir / f"{_safe(name)}.paginated.json"
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return {
            "name": name, "strategy": "paginated",
            "status": "written", "output": str(target),
            "source_id": source_id,
        }

    def convert_all(self, catalog: list[dict], output_dir: str | Path) -> dict:
        """Convert every linked report found in *catalog*."""
        detected = self.detect(catalog)
        results = [self.convert(item, output_dir) for item in detected]
        summary = {
            "strategy": self.strategy,
            "detected": len(detected),
            "converted": sum(1 for r in results if r["status"] == "written"),
            "skipped": sum(1 for r in results if r["status"] == "skipped"),
            "items": results,
        }
        logger.info(
            "Linked-report conversion: %d detected, %d written, strategy=%s",
            summary["detected"], summary["converted"], self.strategy,
        )
        return summary

    # ------------------------------------------------------------------
    # Payload builders
    # ------------------------------------------------------------------

    @staticmethod
    def _make_bookmark(name: str, source_id: str, parameters: list[dict]) -> dict:
        return {
            "name": name,
            "displayName": name,
            "sourceReportId": source_id,
            "filters": [
                {
                    "name": p.get("Name") or p.get("name"),
                    "value": p.get("DefaultValues") or p.get("defaultValues") or p.get("value"),
                }
                for p in parameters
            ],
        }

    @staticmethod
    def _make_paginated_overrides(name: str, source_id: str, parameters: list[dict]) -> dict:
        return {
            "linkedReportName": name,
            "baseReportId": source_id,
            "parameterOverrides": [
                {
                    "name": p.get("Name") or p.get("name"),
                    "default": p.get("DefaultValues") or p.get("defaultValues") or p.get("value"),
                }
                for p in parameters
            ],
        }


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)
