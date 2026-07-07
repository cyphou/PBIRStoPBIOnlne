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

    def extract(
        self,
        catalog: dict[str, Any],
        security: dict[str, Any],
        model_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assessed = MigrationAssessment().assess(catalog)
        items = assessed.get("items", []) if isinstance(assessed, dict) else []
        account_index = self._build_account_index(security)
        model_accounts, model_roles_without_members = self._model_role_accounts(model_snapshot)

        enriched: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", ""))
            principals = sorted(account_index.get(path, set()) | model_accounts)
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
                    "model_role_principal_count": len(model_accounts),
                    "model_role_principals": sorted(model_accounts),
                    "model_roles_without_members": sorted(model_roles_without_members),
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
                "model_role_principal_count": len(model_accounts),
                "model_roles_without_members": sorted(model_roles_without_members),
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
                    "model_role_principal_count",
                    "model_role_principals",
                    "model_roles_without_members",
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
                        item.get("model_role_principal_count", 0),
                        "; ".join(item.get("model_role_principals", [])),
                        "; ".join(item.get("model_roles_without_members", [])),
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

    @staticmethod
    def _model_role_accounts(model_snapshot: dict[str, Any] | None) -> tuple[set[str], set[str]]:
        if not isinstance(model_snapshot, dict) or not model_snapshot.get("available"):
            return set(), set()

        roles = model_snapshot.get("roles", [])
        if not isinstance(roles, list):
            return set(), set()

        principals: set[str] = set()
        roles_without_members: set[str] = set()

        for role in roles:
            if not isinstance(role, dict):
                continue
            role_name = str(role.get("name") or role.get("Name") or "").strip()
            members = BPAExtractor._extract_role_members(role)
            if members:
                principals.update(members)
            elif role_name:
                roles_without_members.add(role_name)

        return principals, roles_without_members

    @staticmethod
    def _extract_role_members(role: dict[str, Any]) -> set[str]:
        candidates = (
            role.get("members"),
            role.get("principals"),
            role.get("modelPermissionMembers"),
            role.get("Members"),
            role.get("Principals"),
        )
        out: set[str] = set()
        for candidate in candidates:
            if not isinstance(candidate, list):
                continue
            for item in candidate:
                if isinstance(item, str) and item.strip():
                    out.add(item.strip())
                    continue
                if isinstance(item, dict):
                    for key in ("name", "principal", "memberName", "id", "objectId", "user"):
                        val = item.get(key)
                        if isinstance(val, str) and val.strip():
                            out.add(val.strip())
                            break
        return out
