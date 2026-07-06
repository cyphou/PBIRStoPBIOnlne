"""Extract BPA results with attached accounts.

Builds an item-level best-practice assessment payload and enriches each item with
accounts/principals that have effective access.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from pbirs_export.assessment import MigrationAssessment


class BPAExtractor:
    """Generate BPA artifacts (JSON/CSV) with account attachments."""

    def extract(self, catalog: dict[str, Any], security: dict[str, Any]) -> dict[str, Any]:
        assessed = MigrationAssessment().assess(catalog)
        items = assessed.get("items", []) if isinstance(assessed, dict) else []
        account_index = self._build_account_index(security)

        enriched: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", ""))
            principals = sorted(account_index.get(path, set()))
            scores = item.get("scores", {}) if isinstance(item.get("scores", {}), dict) else {}
            red_categories = sorted(k for k, v in scores.items() if isinstance(v, dict) and v.get("score") == "RED")
            yellow_categories = sorted(k for k, v in scores.items() if isinstance(v, dict) and v.get("score") == "YELLOW")

            enriched.append(
                {
                    "item_id": str(item.get("id", "")),
                    "item_name": str(item.get("name", "")),
                    "item_path": path,
                    "item_type": str(item.get("type", "")),
                    "bpa_overall": str(item.get("overall", "")),
                    "red_categories": red_categories,
                    "yellow_categories": yellow_categories,
                    "principal_count": len(principals),
                    "principals": principals,
                    "notes": item.get("notes", []),
                }
            )

        return {
            "summary": {
                "total_items": len(enriched),
                "green": sum(1 for i in enriched if i.get("bpa_overall") == "GREEN"),
                "yellow": sum(1 for i in enriched if i.get("bpa_overall") == "YELLOW"),
                "red": sum(1 for i in enriched if i.get("bpa_overall") == "RED"),
                "items_with_attached_accounts": sum(1 for i in enriched if i.get("principal_count", 0) > 0),
            },
            "items": enriched,
        }

    def save_json(self, output_dir: str, payload: dict[str, Any]) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "bpa_accounts.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return path

    def save_csv(self, output_dir: str, payload: dict[str, Any]) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "bpa_accounts.csv"
        rows = payload.get("items", []) if isinstance(payload, dict) else []

        with path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "item_name",
                    "item_path",
                    "item_type",
                    "bpa_overall",
                    "red_categories",
                    "yellow_categories",
                    "principal_count",
                    "principals",
                    "notes",
                ]
            )
            for item in rows:
                if not isinstance(item, dict):
                    continue
                writer.writerow(
                    [
                        item.get("item_name", ""),
                        item.get("item_path", ""),
                        item.get("item_type", ""),
                        item.get("bpa_overall", ""),
                        "; ".join(item.get("red_categories", [])),
                        "; ".join(item.get("yellow_categories", [])),
                        item.get("principal_count", 0),
                        "; ".join(item.get("principals", [])),
                        "; ".join(str(n) for n in item.get("notes", [])),
                    ]
                )
        return path

    @staticmethod
    def _build_account_index(security: dict[str, Any]) -> dict[str, set[str]]:
        index: dict[str, set[str]] = {}
        effective = security.get("effective_permissions", []) if isinstance(security, dict) else []
        for entry in effective:
            if not isinstance(entry, dict):
                continue
            path = str(entry.get("item_path", ""))
            principal = str(entry.get("principal", ""))
            if not path or not principal:
                continue
            index.setdefault(path, set()).add(principal)
        return index
