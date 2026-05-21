"""
Field Parameter Creator — auto-creates field parameters for dynamic axis/slicer scenarios.

Scans report visuals for common patterns where field parameters improve
the PBI Online experience (dynamic axis switching, metric selectors).
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class FieldParameterCreator:
    """Detect field-parameter-worthy patterns and generate DAX definitions."""

    def detect(self, report_visuals: list[dict]) -> list[dict]:
        """Detect visuals that would benefit from field parameters.

        Args:
            report_visuals: list of visual definitions with ``fields`` and ``type``.
        """
        candidates: list[dict] = []

        # Group by page and visual type to find switchable axes
        page_fields: dict[str, list[dict]] = {}
        for visual in report_visuals:
            page = visual.get("page", "default")
            page_fields.setdefault(page, []).append(visual)

        for page, visuals in page_fields.items():
            # Look for multiple similar visuals that differ only by axis
            charts = [v for v in visuals if v.get("type") in (
                "clusteredBarChart", "lineChart", "areaChart",
                "clusteredColumnChart", "combo", "scatterChart",
            )]

            if len(charts) < 2:
                continue

            # Collect all axis fields across similar charts
            axis_fields: set[str] = set()
            for chart in charts:
                for field in chart.get("fields", []):
                    if field.get("role") in ("axis", "category", "x"):
                        axis_fields.add(field.get("column", ""))

            if len(axis_fields) >= 2:
                candidates.append({
                    "page": page,
                    "parameter_name": f"Axis Selector - {page}",
                    "fields": sorted(axis_fields),
                    "affected_visuals": len(charts),
                    "type": "axis_parameter",
                })

            # Look for metric selectors (multiple measures on same visual type)
            measure_fields: set[str] = set()
            for chart in charts:
                for field in chart.get("fields", []):
                    if field.get("role") in ("values", "y", "measure"):
                        measure_fields.add(field.get("measure", ""))

            if len(measure_fields) >= 3:
                candidates.append({
                    "page": page,
                    "parameter_name": f"Metric Selector - {page}",
                    "fields": sorted(measure_fields),
                    "affected_visuals": len(charts),
                    "type": "measure_parameter",
                })

        logger.info(
            "Field parameter detection: %d candidates found", len(candidates),
        )
        return candidates

    def generate_dax(self, candidate: dict) -> str:
        """Generate DAX for a field parameter table.

        Returns the DAX expression to create the parameter table.
        """
        param_name = candidate.get("parameter_name", "Parameter")
        fields = candidate.get("fields", [])
        param_type = candidate.get("type", "axis_parameter")

        if param_type == "measure_parameter":
            # Measure parameter — uses NAMEOF
            rows = []
            for i, field in enumerate(fields):
                if field:
                    rows.append(f'    ("{field}", NAMEOF([{field}]), {i})')
            dax = (
                f'{param_name} = {{\n'
                + ",\n".join(rows)
                + "\n}"
            )
        else:
            # Column parameter
            rows = []
            for i, field in enumerate(fields):
                if field:
                    safe = field.replace("'", "''")
                    rows.append(f'    ("{safe}", NAMEOF(\'{safe}\'[{safe}]), {i})')
            dax = (
                f'{param_name} = {{\n'
                + ",\n".join(rows)
                + "\n}"
            )

        return dax

    def save(self, output_dir: str, candidates: list[dict]) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        output = []
        for c in candidates:
            output.append({
                **c,
                "dax": self.generate_dax(c),
            })

        path = out / "field_parameters.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
        return path
