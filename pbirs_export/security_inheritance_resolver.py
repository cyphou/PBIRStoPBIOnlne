"""Optional DB-assisted resolver for PBIRS security inheritance edge cases."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


ConflictStrategy = str


class SecurityInheritanceResolver:
    """Merge API-visible and DB-resolved effective permissions."""

    def __init__(
        self,
        connection_string: str,
        conflict_strategy: ConflictStrategy = "prefer-api",
        db_fetcher: Callable[[], dict[str, set[tuple[str, str]]]] | None = None,
        logger_: logging.Logger | None = None,
    ) -> None:
        self.connection_string = connection_string
        self.conflict_strategy = conflict_strategy
        self.db_fetcher = db_fetcher
        self.logger = logger_ or logger

    def resolve(
        self,
        api_item_policies: list[dict[str, Any]],
        catalog_items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Resolve effective permissions and emit a detailed gap report."""
        api_map = self._to_api_map(api_item_policies)
        db_map = self._fetch_db_effective_permissions()

        path_to_item = {str(i.get("Path", "")): i for i in catalog_items if i.get("Path")}
        all_paths = sorted(set(api_map.keys()) | set(db_map.keys()))

        merged_item_policies: list[dict[str, Any]] = []
        gap_items: list[dict[str, Any]] = []
        diff_count = 0

        for path in all_paths:
            api_perms = api_map.get(path, set())
            db_perms = db_map.get(path, set())
            only_api = sorted(api_perms - db_perms)
            only_db = sorted(db_perms - api_perms)
            has_diff = bool(only_api or only_db)
            if has_diff:
                diff_count += 1

            resolved, source = self._resolve_path_permissions(api_perms, db_perms)
            item = path_to_item.get(path, {})
            merged_item_policies.append(
                {
                    "item_id": item.get("Id", ""),
                    "item_name": item.get("Name", ""),
                    "item_path": path,
                    "item_type": item.get("Type", ""),
                    "policies": self._to_policy_list(resolved),
                }
            )

            gap_items.append(
                {
                    "item_path": path,
                    "item_name": item.get("Name", ""),
                    "item_type": item.get("Type", ""),
                    "only_api": [
                        {"principal": p, "ssrs_role": r} for p, r in only_api
                    ],
                    "only_db": [
                        {"principal": p, "ssrs_role": r} for p, r in only_db
                    ],
                    "resolved_source": source,
                    "conflict": has_diff,
                }
            )

        gap_report = {
            "enabled": True,
            "conflict_strategy": self.conflict_strategy,
            "total_items": len(all_paths),
            "diff_items_count": diff_count,
            "items": gap_items,
        }

        return {
            "merged_item_policies": merged_item_policies,
            "gap_report": gap_report,
        }

    def _fetch_db_effective_permissions(self) -> dict[str, set[tuple[str, str]]]:
        if self.db_fetcher is not None:
            return self.db_fetcher()

        try:
            import pyodbc  # type: ignore
        except ImportError as e:  # pragma: no cover - environment dependent
            raise RuntimeError("pyodbc is required for security DB assist") from e

        sql = """
WITH CatalogHierarchy AS (
    SELECT c.ItemID, c.ParentID, c.Path, c.PolicyID, c.ItemID AS RootItemID, 0 AS Depth
    FROM dbo.Catalog c
    UNION ALL
    SELECT p.ItemID, p.ParentID, p.Path, p.PolicyID, ch.RootItemID, ch.Depth + 1
    FROM CatalogHierarchy ch
    JOIN dbo.Catalog p ON ch.ParentID = p.ItemID
    WHERE ch.PolicyID IS NULL AND ch.ParentID IS NOT NULL AND ch.Depth < 32
),
EffectivePolicy AS (
    SELECT RootItemID AS ItemID,
           MAX(CASE WHEN PolicyID IS NOT NULL THEN PolicyID END) AS EffectivePolicyID
    FROM CatalogHierarchy
    GROUP BY RootItemID
)
SELECT c.Path AS ItemPath, u.UserName AS Principal, r.RoleName AS RoleName
FROM EffectivePolicy ep
JOIN dbo.Catalog c ON c.ItemID = ep.ItemID
JOIN dbo.PolicyUserRole pur ON pur.PolicyID = ep.EffectivePolicyID
JOIN dbo.Users u ON u.UserID = pur.UserID
JOIN dbo.Roles r ON r.RoleID = pur.RoleID
WHERE c.Path IS NOT NULL
"""

        out: dict[str, set[tuple[str, str]]] = defaultdict(set)
        conn = pyodbc.connect(self.connection_string)
        try:
            cur = conn.cursor()
            rows = cur.execute(sql).fetchall()
            for row in rows:
                path = str(getattr(row, "ItemPath", "") or row[0] or "")
                principal = str(getattr(row, "Principal", "") or row[1] or "")
                role = str(getattr(row, "RoleName", "") or row[2] or "")
                if path and principal and role:
                    out[path].add((principal, role))
        finally:
            conn.close()

        return dict(out)

    @staticmethod
    def _to_api_map(api_item_policies: list[dict[str, Any]]) -> dict[str, set[tuple[str, str]]]:
        out: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for entry in api_item_policies:
            path = str(entry.get("item_path", ""))
            for pol in entry.get("policies", []):
                principal = str(pol.get("GroupUserName", ""))
                for role in pol.get("Roles", []):
                    role_name = str(role.get("Name", ""))
                    if path and principal and role_name:
                        out[path].add((principal, role_name))
        return dict(out)

    def _resolve_path_permissions(
        self,
        api_perms: set[tuple[str, str]],
        db_perms: set[tuple[str, str]],
    ) -> tuple[set[tuple[str, str]], str]:
        if self.conflict_strategy == "prefer-db":
            if db_perms:
                return db_perms, "db"
            return api_perms, "api"

        if self.conflict_strategy == "strict-fail-on-diff":
            # Preserve API output for deterministic artifacts; caller handles failure.
            if api_perms:
                return api_perms, "api"
            return db_perms, "db"

        # default: prefer-api
        if api_perms:
            return api_perms, "api"
        return db_perms, "db"

    @staticmethod
    def _to_policy_list(perms: set[tuple[str, str]]) -> list[dict[str, Any]]:
        grouped: dict[str, set[str]] = defaultdict(set)
        for principal, role in perms:
            grouped[principal].add(role)

        out: list[dict[str, Any]] = []
        for principal in sorted(grouped.keys()):
            out.append(
                {
                    "GroupUserName": principal,
                    "Roles": [{"Name": r} for r in sorted(grouped[principal])],
                }
            )
        return out
