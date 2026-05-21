"""
Security Extractor — deep extraction of the PBIRS security model.

Goes beyond basic policy extraction to capture:
- Permission inheritance chains (which items break inheritance)
- Effective permissions per principal (aggregated across folder hierarchy)
- AD group/user enumeration from policies
- Row-Level Security (RLS) detection in Power BI report datasets
"""

import logging
import re
from typing import Any

from pbirs_export.api_client import PBIRSClient

logger = logging.getLogger(__name__)


class SecurityExtractor:
    """Extract the full PBIRS security model for migration analysis."""

    def __init__(self, client: PBIRSClient):
        self.client = client

    def extract_all(self, catalog: dict) -> dict:
        """Extract complete security model from PBIRS."""
        items = catalog.get("items", [])
        folders = catalog.get("folders", [])

        system_policies = self._extract_system_policies()
        inheritance_map = self._build_inheritance_map(items, folders)
        principals = self._enumerate_principals(items, system_policies)
        effective_permissions = self._compute_effective_permissions(
            items, folders, inheritance_map,
        )
        rls_items = self._detect_rls(items)
        workspace_recommendations = self._recommend_workspaces(effective_permissions)

        result = {
            "system_policies": system_policies,
            "inheritance_map": inheritance_map,
            "principals": principals,
            "effective_permissions": effective_permissions,
            "rls_detection": rls_items,
            "workspace_recommendations": workspace_recommendations,
            "summary": self._summarise(
                system_policies, principals, inheritance_map,
                rls_items, workspace_recommendations,
            ),
        }

        logger.info(
            "Security extraction complete: %d principals, %d items with "
            "broken inheritance, %d items with RLS",
            len(principals),
            sum(1 for v in inheritance_map.values() if v.get("breaks_inheritance")),
            len(rls_items),
        )
        return result

    # ------------------------------------------------------------------
    # System-level policies
    # ------------------------------------------------------------------

    def _extract_system_policies(self) -> list[dict]:
        """Extract PBIRS system-level policies."""
        try:
            return self.client.get_system_policies()
        except Exception as e:
            logger.warning("Could not extract system policies: %s", e)
            return []

    # ------------------------------------------------------------------
    # Inheritance analysis
    # ------------------------------------------------------------------

    def _build_inheritance_map(
        self,
        items: list[dict],
        folders: list[dict],
    ) -> dict[str, dict]:
        """Build a map of which items/folders break permission inheritance.

        An item breaks inheritance when it defines its own policy set
        rather than inheriting from the parent folder.
        """
        inheritance: dict[str, dict] = {}

        for item in items:
            item_id = item.get("Id", "")
            item_path = item.get("Path", "")
            parent_path = "/".join(item_path.rstrip("/").split("/")[:-1]) or "/"
            policies = item.get("policies", [])

            breaks = len(policies) > 0
            inheritance[item_path] = {
                "item_id": item_id,
                "parent_path": parent_path,
                "breaks_inheritance": breaks,
                "policy_count": len(policies),
            }

        return inheritance

    # ------------------------------------------------------------------
    # Principal enumeration
    # ------------------------------------------------------------------

    def _enumerate_principals(
        self,
        items: list[dict],
        system_policies: list[dict],
    ) -> list[dict]:
        """Enumerate all unique principals (users/groups) in the security model."""
        seen: dict[str, dict] = {}

        # From system policies
        for policy in system_policies:
            name = policy.get("GroupUserName", "")
            if name and name not in seen:
                seen[name] = self._classify_principal(name)

        # From item policies
        for item in items:
            for policy in item.get("policies", []):
                name = policy.get("GroupUserName", "")
                if name and name not in seen:
                    seen[name] = self._classify_principal(name)

                roles = policy.get("Roles", [])
                for role in roles:
                    role_name = role.get("Name", "")
                    entry = seen.get(name)
                    if entry:
                        entry.setdefault("ssrs_roles", set()).add(role_name)

        # Convert sets to sorted lists for JSON serialisation
        principals = []
        for name, info in sorted(seen.items()):
            info["name"] = name
            if isinstance(info.get("ssrs_roles"), set):
                info["ssrs_roles"] = sorted(info["ssrs_roles"])
            principals.append(info)

        return principals

    @staticmethod
    def _classify_principal(name: str) -> dict:
        """Classify a principal as AD user, AD group, or email."""
        info: dict[str, Any] = {"type": "unknown"}

        if "\\" in name:
            # DOMAIN\user or DOMAIN\group
            domain, account = name.split("\\", 1)
            info["domain"] = domain
            info["account"] = account
            info["type"] = "ad_account"
        elif "@" in name:
            info["type"] = "email"
        elif name.startswith("BUILTIN\\"):
            info["type"] = "builtin"
        else:
            info["type"] = "local"

        return info

    # ------------------------------------------------------------------
    # Effective permissions
    # ------------------------------------------------------------------

    def _compute_effective_permissions(
        self,
        items: list[dict],
        folders: list[dict],
        inheritance_map: dict[str, dict],
    ) -> list[dict]:
        """Compute effective permissions per principal per item.

        Walks the folder hierarchy to resolve inherited permissions.
        """
        # Build folder policy lookup
        folder_policies: dict[str, list[dict]] = {}
        for item in items:
            path = item.get("Path", "")
            policies = item.get("policies", [])
            if policies:
                folder_policies[path] = policies

        effective: list[dict] = []
        for item in items:
            item_path = item.get("Path", "")
            policies = item.get("policies", [])

            if policies:
                # Item has its own policies
                resolved_policies = policies
                source = "direct"
            else:
                # Inherit from nearest parent with policies
                resolved_policies = self._find_inherited_policies(
                    item_path, folder_policies,
                )
                source = "inherited"

            for policy in resolved_policies:
                principal = policy.get("GroupUserName", "")
                for role in policy.get("Roles", []):
                    effective.append({
                        "item_path": item_path,
                        "item_name": item.get("Name", ""),
                        "item_type": item.get("Type", ""),
                        "principal": principal,
                        "ssrs_role": role.get("Name", ""),
                        "source": source,
                    })

        return effective

    @staticmethod
    def _find_inherited_policies(
        item_path: str,
        folder_policies: dict[str, list[dict]],
    ) -> list[dict]:
        """Walk up the path hierarchy to find the nearest ancestor policies."""
        parts = item_path.rstrip("/").split("/")
        # Walk from parent to root
        for i in range(len(parts) - 1, 0, -1):
            ancestor = "/".join(parts[:i]) or "/"
            if ancestor in folder_policies:
                return folder_policies[ancestor]
        return folder_policies.get("/", [])

    # ------------------------------------------------------------------
    # RLS detection
    # ------------------------------------------------------------------

    def _detect_rls(self, items: list[dict]) -> list[dict]:
        """Detect items that may have Row-Level Security (RLS) configured.

        RLS in PBIRS Power BI reports is embedded in the .pbix data model.
        We flag items based on heuristics (metadata hints, datasource roles).
        """
        rls_items: list[dict] = []
        for item in items:
            if item.get("Type") != "PowerBIReport":
                continue

            rls_indicators: list[str] = []

            # Check for RLS-related metadata hints
            if item.get("has_rls"):
                rls_indicators.append("metadata flag")

            # Check for username() or userprincipalname() DAX patterns
            # (only possible if we have partial model info)
            expressions = item.get("dax_expressions", [])
            for expr in expressions:
                expr_lower = str(expr).lower()
                if "username()" in expr_lower or "userprincipalname()" in expr_lower:
                    rls_indicators.append("DAX security function")
                    break

            # Check for security roles in datasource metadata
            datasources = item.get("datasources", [])
            for ds in datasources:
                if ds.get("SecurityRoles") or ds.get("roles"):
                    rls_indicators.append("datasource security roles")
                    break

            if rls_indicators:
                rls_items.append({
                    "item_id": item.get("Id", ""),
                    "item_name": item.get("Name", ""),
                    "item_path": item.get("Path", ""),
                    "indicators": rls_indicators,
                })

        return rls_items

    # ------------------------------------------------------------------
    # Workspace splitting recommendations
    # ------------------------------------------------------------------

    def _recommend_workspaces(
        self,
        effective_permissions: list[dict],
    ) -> list[dict]:
        """Recommend workspace splitting based on permission boundaries.

        In PBIRS, each folder can have distinct permissions.  PBI Online has
        workspace-level permissions, so items with different access patterns
        should be placed in separate workspaces.
        """
        # Group items by their unique set of (principal, role) tuples
        from collections import defaultdict

        access_patterns: dict[str, set[tuple[str, str]]] = defaultdict(set)
        item_info: dict[str, dict] = {}

        for entry in effective_permissions:
            path = entry["item_path"]
            access_patterns[path].add(
                (entry["principal"], entry["ssrs_role"]),
            )
            if path not in item_info:
                item_info[path] = {
                    "name": entry["item_name"],
                    "type": entry["item_type"],
                }

        # Cluster items with identical access patterns
        pattern_groups: dict[frozenset, list[str]] = defaultdict(list)
        for path, pattern in access_patterns.items():
            pattern_groups[frozenset(pattern)].append(path)

        recommendations: list[dict] = []
        for idx, (pattern, paths) in enumerate(
            sorted(pattern_groups.items(), key=lambda x: -len(x[1])), start=1,
        ):
            principals_in_group = sorted({p for p, _ in pattern})
            recommendations.append({
                "workspace_index": idx,
                "suggested_name": f"Workspace-{idx}",
                "item_count": len(paths),
                "items": [
                    {"path": p, **item_info.get(p, {})} for p in sorted(paths)
                ],
                "principals": principals_in_group,
                "access_pattern": sorted(
                    {"principal": p, "role": r} for p, r in pattern
                ),
            })

        return recommendations

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    @staticmethod
    def _summarise(
        system_policies: list[dict],
        principals: list[dict],
        inheritance_map: dict[str, dict],
        rls_items: list[dict],
        workspace_recommendations: list[dict],
    ) -> dict:
        """Produce a concise security summary."""
        ad_accounts = [p for p in principals if p.get("type") == "ad_account"]
        emails = [p for p in principals if p.get("type") == "email"]
        broken = sum(
            1 for v in inheritance_map.values() if v.get("breaks_inheritance")
        )

        return {
            "system_policy_count": len(system_policies),
            "total_principals": len(principals),
            "ad_accounts": len(ad_accounts),
            "email_accounts": len(emails),
            "items_with_custom_policies": broken,
            "items_inheriting": len(inheritance_map) - broken,
            "rls_report_count": len(rls_items),
            "recommended_workspace_count": len(workspace_recommendations),
        }
