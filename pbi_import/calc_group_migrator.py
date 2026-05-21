"""
Calculation Group Migrator — detects and migrates calculation groups.

PBIRS datasets with calculation groups need special handling during migration
since they rely on specific model features (like FORMAT_STRING expressions).
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class CalcGroupMigrator:
    """Detect and plan migration of calculation groups."""

    def detect(self, model_metadata: list[dict]) -> list[dict]:
        """Detect calculation groups in dataset model metadata.

        Expects items with a ``tables`` list, where calc group tables have
        ``calculationGroup`` entries.
        """
        results: list[dict] = []

        for item in model_metadata:
            name = item.get("name", item.get("Name", ""))
            tables = item.get("tables", [])

            calc_groups: list[dict] = []
            for table in tables:
                cg = table.get("calculationGroup")
                if not cg:
                    continue

                items = cg.get("calculationItems", [])
                calc_groups.append({
                    "table_name": table.get("name", ""),
                    "precedence": cg.get("precedence", 0),
                    "items": [
                        {
                            "name": ci.get("name", ""),
                            "expression": ci.get("expression", ""),
                            "format_string": ci.get("formatStringDefinition", {}).get(
                                "expression", ""
                            ),
                        }
                        for ci in items
                    ],
                })

            if calc_groups:
                results.append({
                    "dataset_name": name,
                    "calculation_groups": calc_groups,
                    "total_items": sum(len(g["items"]) for g in calc_groups),
                    "requires_premium": True,  # calc groups need Premium/PPU
                    "migration_notes": [
                        "Calculation groups require XMLA endpoint for programmatic migration",
                        "Verify FORMAT_STRING expressions are compatible with PBI Service",
                        "Test all calculation items post-migration",
                    ],
                })

        logger.info(
            "Detected %d datasets with calculation groups (%d total calc items)",
            len(results),
            sum(r["total_items"] for r in results),
        )
        return results

    def generate_tmsl(self, calc_group_info: dict) -> str:
        """Generate a TMSL snippet for creating a calculation group.

        Returns a JSON string suitable for XMLA endpoint execution.
        """
        groups = calc_group_info.get("calculation_groups", [])
        if not groups:
            return "{}"

        # Take the first group for TMSL generation
        group = groups[0]
        tmsl = {
            "createOrReplace": {
                "object": {
                    "database": calc_group_info.get("dataset_name", ""),
                    "table": group["table_name"],
                },
                "table": {
                    "name": group["table_name"],
                    "calculationGroup": {
                        "precedence": group.get("precedence", 0),
                        "calculationItems": [
                            {
                                "name": ci["name"],
                                "expression": ci["expression"],
                                **({"formatStringDefinition": {
                                    "expression": ci["format_string"]
                                }} if ci.get("format_string") else {}),
                            }
                            for ci in group["items"]
                        ],
                    },
                },
            },
        }
        return json.dumps(tmsl, indent=2)

    def save(self, output_dir: str, results: list[dict]) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "calc_group_migration.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        return path
