"""
Permission Mapper — maps SSRS role assignments to PBI Online workspace roles + RLS.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# SSRS role → PBI Online workspace role mapping
ROLE_MAP = {
    "Browser": "Viewer",
    "Content Manager": "Admin",
    "My Reports": "Contributor",
    "Publisher": "Contributor",
    "Report Builder": "Contributor",
    "System Administrator": "Admin",
    "System User": "Viewer",
}


class PermissionMapper:
    """Map SSRS permissions to PBI Online workspace roles."""

    def __init__(self, pbi_client: Any):
        self.client = pbi_client

    def map_permissions(
        self,
        permissions: dict,
        workspace_id: str,
        dry_run: bool = False,
    ) -> dict:
        """Map extracted PBIRS permissions to PBI Online workspace roles."""
        results: dict[str, list] = {"assigned": [], "skipped": [], "unmapped": []}

        # Collect unique users/groups across all item policies
        principals: dict[str, set] = {}
        for item_policy in permissions.get("item_policies", []):
            for policy in item_policy.get("policies", []):
                group_user = policy.get("GroupUserName", "")
                if not group_user:
                    continue

                for role in policy.get("Roles", []):
                    role_name = role.get("Name", "")
                    pbi_role = ROLE_MAP.get(role_name)
                    if pbi_role:
                        if group_user not in principals:
                            principals[group_user] = set()
                        principals[group_user].add(pbi_role)
                    else:
                        results["unmapped"].append({
                            "principal": group_user,
                            "ssrs_role": role_name,
                        })

        # Assign highest privilege role per principal
        for principal, roles in principals.items():
            target_role = self._highest_role(roles)

            if dry_run:
                logger.info("[DRY RUN] Would assign %s as %s", principal, target_role)
                results["assigned"].append({
                    "principal": principal,
                    "role": target_role,
                    "dry_run": True,
                })
                continue

            try:
                self.client.add_workspace_user(
                    workspace_id=workspace_id,
                    email_or_upn=principal,
                    role=target_role,
                )
                results["assigned"].append({
                    "principal": principal,
                    "role": target_role,
                })
            except Exception as e:
                logger.warning("Could not assign %s as %s: %s", principal, target_role, e)
                results["skipped"].append({
                    "principal": principal,
                    "role": target_role,
                    "error": str(e),
                })

        return results

    @staticmethod
    def _highest_role(roles: set[str]) -> str:
        """Return the highest privilege role from a set of roles."""
        priority = ["Admin", "Member", "Contributor", "Viewer"]
        for role in priority:
            if role in roles:
                return role
        return "Viewer"

    def generate_mapping_report(self, permissions: dict) -> dict:
        """Generate a permission mapping report without applying changes."""
        mappings = []
        for item_policy in permissions.get("item_policies", []):
            for policy in item_policy.get("policies", []):
                group_user = policy.get("GroupUserName", "")
                for role in policy.get("Roles", []):
                    role_name = role.get("Name", "")
                    pbi_role = ROLE_MAP.get(role_name, "UNMAPPED")
                    mappings.append({
                        "item_path": item_policy.get("item_path"),
                        "principal": group_user,
                        "ssrs_role": role_name,
                        "pbi_role": pbi_role,
                    })
        return {"mappings": mappings, "total": len(mappings)}
