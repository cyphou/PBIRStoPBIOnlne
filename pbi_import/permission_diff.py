"""
Permission Diff — before/after permission comparison report.

Compares PBIRS effective permissions with PBI Online workspace permissions
to generate a diff report showing access changes per user/group.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PermissionDiff:
    """Compare pre-migration and post-migration permissions."""

    def __init__(self, pbi_client: Any | None = None):
        self.client = pbi_client

    def compare(
        self,
        pbirs_security: dict,
        workspace_id: str,
        workspace_permissions: list[dict] | None = None,
    ) -> dict:
        """Generate a diff between PBIRS and PBI Online permissions.

        Args:
            pbirs_security: output from SecurityExtractor.
            workspace_id: target PBI workspace.
            workspace_permissions: pre-fetched workspace permissions (optional).
        """
        # Source permissions
        source_perms = self._extract_source_perms(pbirs_security)

        # Target permissions
        if workspace_permissions is None and self.client:
            workspace_permissions = self.client.get_workspace_users(workspace_id)
        target_perms = self._extract_target_perms(workspace_permissions or [])

        # Compute diff
        all_principals = set(source_perms.keys()) | set(target_perms.keys())
        diff: list[dict] = []

        for principal in sorted(all_principals):
            src = source_perms.get(principal)
            tgt = target_perms.get(principal)

            if src and tgt:
                if src["role"] != tgt["role"]:
                    status = "changed"
                else:
                    status = "unchanged"
            elif src and not tgt:
                status = "removed"
            else:
                status = "added"

            diff.append({
                "principal": principal,
                "source_role": src["role"] if src else None,
                "source_items": src.get("items", []) if src else [],
                "target_role": tgt["role"] if tgt else None,
                "status": status,
            })

        result = {
            "workspace_id": workspace_id,
            "diff": diff,
            "summary": {
                "total_principals": len(all_principals),
                "unchanged": sum(1 for d in diff if d["status"] == "unchanged"),
                "changed": sum(1 for d in diff if d["status"] == "changed"),
                "removed": sum(1 for d in diff if d["status"] == "removed"),
                "added": sum(1 for d in diff if d["status"] == "added"),
            },
        }

        logger.info(
            "Permission diff: %d unchanged, %d changed, %d removed, %d added",
            result["summary"]["unchanged"],
            result["summary"]["changed"],
            result["summary"]["removed"],
            result["summary"]["added"],
        )
        return result

    def save(self, output_dir: str, diff_report: dict) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "permission_diff.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(diff_report, f, indent=2)
        logger.info("Permission diff saved to %s", path)
        return path

    @staticmethod
    def _extract_source_perms(security: dict) -> dict[str, dict]:
        """Extract per-principal permissions from PBIRS security data."""
        perms: dict[str, dict] = {}
        for entry in security.get("effective_permissions", []):
            principal = entry.get("principal", "")
            role = entry.get("pbi_role", entry.get("ssrs_role", ""))
            items = entry.get("items", [])
            existing = perms.get(principal)
            if existing:
                # Keep highest role
                if _ROLE_RANK.get(role, 0) > _ROLE_RANK.get(existing["role"], 0):
                    existing["role"] = role
                existing["items"].extend(items)
            else:
                perms[principal] = {"role": role, "items": list(items)}
        return perms

    @staticmethod
    def _extract_target_perms(workspace_users: list[dict]) -> dict[str, dict]:
        """Extract per-principal permissions from PBI workspace users."""
        perms: dict[str, dict] = {}
        for user in workspace_users:
            principal = user.get("emailAddress", user.get("displayName", ""))
            role = user.get("groupUserAccessRight", user.get("role", ""))
            perms[principal] = {"role": role}
        return perms


_ROLE_RANK: dict[str, int] = {
    "Viewer": 1,
    "Contributor": 2,
    "Member": 3,
    "Admin": 4,
}
