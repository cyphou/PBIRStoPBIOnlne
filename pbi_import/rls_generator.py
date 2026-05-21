"""
RLS Generator — auto-generate Row-Level Security rules from PBIRS item permissions.

Converts PBIRS item-level security (per-folder/per-report access controls)
into PBI Online RLS role definitions and DAX filter expressions.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class RLSGenerator:
    """Generate RLS role definitions from PBIRS item-level permissions."""

    def __init__(self, security_data: dict):
        self.security = security_data

    def generate(self) -> dict:
        """Analyse item-level permissions and generate RLS definitions.

        Returns RLS roles with DAX filter expressions and member assignments.
        """
        item_perms = self.security.get("item_permissions", [])
        effective = self.security.get("effective_permissions", [])

        # Group items by access pattern (set of principals with access)
        access_patterns: dict[str, list[dict]] = {}
        for perm in item_perms:
            principals = tuple(sorted(p.get("principal", "") for p in perm.get("policies", [])))
            key = "|".join(principals)
            access_patterns.setdefault(key, []).append(perm)

        roles: list[dict] = []
        for idx, (key, items) in enumerate(access_patterns.items()):
            principals = key.split("|") if key else []
            if not principals:
                continue

            role_name = f"AccessGroup_{idx + 1}"
            item_paths = [i.get("item_path", "") for i in items]

            # Generate DAX filter (assumes a ReportPath or FolderPath column exists)
            dax_filter = self._generate_dax_filter(item_paths)

            roles.append({
                "role_name": role_name,
                "members": principals,
                "items": item_paths,
                "dax_filter": dax_filter,
                "item_count": len(items),
            })

        result = {
            "roles": roles,
            "summary": {
                "total_roles": len(roles),
                "total_items_covered": sum(r["item_count"] for r in roles),
                "unique_principals": len({
                    p for r in roles for p in r["members"]
                }),
            },
        }

        logger.info(
            "Generated %d RLS roles covering %d items",
            len(roles), result["summary"]["total_items_covered"],
        )
        return result

    def save(self, output_dir: str, rls_plan: dict | None = None) -> Path:
        """Save RLS definitions to disk."""
        if rls_plan is None:
            rls_plan = self.generate()
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "rls_definitions.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rls_plan, f, indent=2)
        logger.info("RLS definitions saved to %s", path)
        return path

    @staticmethod
    def _generate_dax_filter(item_paths: list[str]) -> str:
        """Generate a DAX filter expression for a set of item paths."""
        if not item_paths:
            return "TRUE()"
        if len(item_paths) == 1:
            safe = item_paths[0].replace('"', '""')
            return f'[ReportPath] = "{safe}"'

        conditions = []
        for path in item_paths:
            safe = path.replace('"', '""')
            conditions.append(f'"{safe}"')
        return "[ReportPath] IN {" + ", ".join(conditions) + "}"
