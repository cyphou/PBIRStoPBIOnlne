"""
Security Converter — converts PBIRS security model to PBI Online security model.

Handles:
- AD principal → Azure AD mapping (using a tenant mapping file)
- Workspace role assignment plans
- RLS preservation plan (document existing RLS for manual recreation)
- Item-level permission → workspace-level permission conversion with
  workspace-splitting recommendations
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# SSRS role → PBI Online workspace role mapping
ROLE_MAP: dict[str, str] = {
    "Browser": "Viewer",
    "Content Manager": "Admin",
    "My Reports": "Contributor",
    "Publisher": "Contributor",
    "Report Builder": "Contributor",
    "System Administrator": "Admin",
    "System User": "Viewer",
}

# Priority order for role deduplication (highest first)
_ROLE_PRIORITY = ["Admin", "Member", "Contributor", "Viewer"]


class SecurityConverter:
    """Convert the extracted PBIRS security model for PBI Online deployment."""

    def __init__(
        self,
        security_data: dict,
        tenant_mapping_path: str | None = None,
    ):
        self.security = security_data
        self.tenant_map: dict[str, str] = {}
        if tenant_mapping_path:
            self.tenant_map = self._load_tenant_mapping(tenant_mapping_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def convert(self, dry_run: bool = False) -> dict:
        """Run the full security conversion pipeline.

        Returns a conversion plan that can be applied by the deployer.
        """
        role_assignments = self._convert_role_assignments()
        ad_mapping = self._convert_principals()
        rls_plan = self._build_rls_plan()
        workspace_plan = self._build_workspace_plan()

        plan = {
            "role_assignments": role_assignments,
            "principal_mapping": ad_mapping,
            "rls_plan": rls_plan,
            "workspace_plan": workspace_plan,
            "unmapped_principals": self._find_unmapped_principals(ad_mapping),
            "unmapped_roles": self._find_unmapped_roles(),
            "dry_run": dry_run,
            "summary": {
                "total_assignments": len(role_assignments),
                "mapped_principals": sum(
                    1 for m in ad_mapping if m.get("azure_ad_identity")
                ),
                "unmapped_principals": sum(
                    1 for m in ad_mapping if not m.get("azure_ad_identity")
                ),
                "rls_reports": len(rls_plan),
                "recommended_workspaces": len(workspace_plan),
            },
        }

        logger.info(
            "Security conversion: %d role assignments, %d principals mapped, "
            "%d unmapped, %d RLS reports",
            len(role_assignments),
            plan["summary"]["mapped_principals"],
            plan["summary"]["unmapped_principals"],
            len(rls_plan),
        )

        return plan

    def save_plan(self, output_dir: str, plan: dict) -> Path:
        """Save the security conversion plan to disk."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        plan_path = out / "security_plan.json"
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2, default=str)
        logger.info("Security plan saved to %s", plan_path)
        return plan_path

    # ------------------------------------------------------------------
    # Role assignment conversion
    # ------------------------------------------------------------------

    def _convert_role_assignments(self) -> list[dict]:
        """Convert SSRS effective permissions to PBI workspace role assignments."""
        effective = self.security.get("effective_permissions", [])
        # Aggregate: (principal) → set of PBI roles
        principal_roles: dict[str, set[str]] = {}
        for entry in effective:
            principal = entry.get("principal", "")
            ssrs_role = entry.get("ssrs_role", "")
            pbi_role = ROLE_MAP.get(ssrs_role)
            if not pbi_role:
                continue
            principal_roles.setdefault(principal, set()).add(pbi_role)

        assignments: list[dict] = []
        for principal, roles in sorted(principal_roles.items()):
            target_role = self._highest_role(roles)
            azure_identity = self.tenant_map.get(principal, "")
            assignments.append({
                "pbirs_principal": principal,
                "azure_ad_identity": azure_identity or None,
                "pbi_role": target_role,
                "source_roles": sorted(roles),
            })

        return assignments

    # ------------------------------------------------------------------
    # Principal mapping (AD → Azure AD)
    # ------------------------------------------------------------------

    def _convert_principals(self) -> list[dict]:
        """Map each PBIRS principal to an Azure AD identity."""
        principals = self.security.get("principals", [])
        results: list[dict] = []

        for p in principals:
            name = p.get("name", "")
            mapped = self.tenant_map.get(name, "")
            results.append({
                "pbirs_principal": name,
                "type": p.get("type", "unknown"),
                "domain": p.get("domain", ""),
                "ssrs_roles": p.get("ssrs_roles", []),
                "azure_ad_identity": mapped or None,
                "mapping_status": "mapped" if mapped else "unmapped",
            })

        return results

    # ------------------------------------------------------------------
    # RLS plan
    # ------------------------------------------------------------------

    def _build_rls_plan(self) -> list[dict]:
        """Document RLS configurations that need manual recreation in PBI Online.

        RLS roles defined in .pbix data models are preserved inside the file,
        but the role-member assignments must be reconfigured in PBI Online.
        """
        rls_items = self.security.get("rls_detection", [])
        plan: list[dict] = []

        for rls in rls_items:
            plan.append({
                "report_name": rls.get("item_name", ""),
                "report_path": rls.get("item_path", ""),
                "indicators": rls.get("indicators", []),
                "action": "Reconfigure RLS role-member assignments in PBI Online after import",
                "notes": (
                    "RLS role definitions inside the .pbix model are preserved. "
                    "After publishing, go to the dataset settings in PBI Online "
                    "and assign Azure AD users/groups to each RLS role."
                ),
            })

        return plan

    # ------------------------------------------------------------------
    # Workspace splitting plan
    # ------------------------------------------------------------------

    def _build_workspace_plan(self) -> list[dict]:
        """Convert workspace recommendations to an actionable deployment plan."""
        recommendations = self.security.get("workspace_recommendations", [])
        plan: list[dict] = []

        for rec in recommendations:
            # Map principals to Azure AD identities
            mapped_principals = []
            for p in rec.get("principals", []):
                azure_id = self.tenant_map.get(p, "")
                mapped_principals.append({
                    "pbirs_principal": p,
                    "azure_ad_identity": azure_id or None,
                })

            mapped_access = []
            for entry in rec.get("access_pattern", []):
                original = entry.get("principal", "")
                azure_id = self.tenant_map.get(original, "")
                pbi_role = ROLE_MAP.get(entry.get("role", ""), "Viewer")
                mapped_access.append({
                    "pbirs_principal": original,
                    "azure_ad_identity": azure_id or None,
                    "pbi_role": pbi_role,
                })

            plan.append({
                "workspace_name": rec.get("suggested_name", ""),
                "item_count": rec.get("item_count", 0),
                "items": rec.get("items", []),
                "role_assignments": mapped_access,
            })

        return plan

    # ------------------------------------------------------------------
    # Gap analysis
    # ------------------------------------------------------------------

    def _find_unmapped_principals(self, ad_mapping: list[dict]) -> list[dict]:
        """Return principals that could not be mapped to Azure AD."""
        return [
            m for m in ad_mapping
            if not m.get("azure_ad_identity")
        ]

    def _find_unmapped_roles(self) -> list[dict]:
        """Return SSRS roles that have no PBI Online mapping."""
        effective = self.security.get("effective_permissions", [])
        unmapped: list[dict] = []
        seen: set[str] = set()

        for entry in effective:
            role = entry.get("ssrs_role", "")
            if role and role not in ROLE_MAP and role not in seen:
                seen.add(role)
                unmapped.append({
                    "ssrs_role": role,
                    "example_principal": entry.get("principal", ""),
                    "example_item": entry.get("item_path", ""),
                })

        return unmapped

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_tenant_mapping(path: str) -> dict[str, str]:
        """Load AD → Azure AD principal mapping file."""
        p = Path(path)
        if not p.exists():
            logger.warning("Tenant mapping file not found: %s", path)
            return {}
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        # Strip keys starting with _ (comments)
        return {k: v for k, v in data.items() if not k.startswith("_")}

    @staticmethod
    def _highest_role(roles: set[str]) -> str:
        """Return the highest-privilege PBI role from a set."""
        for role in _ROLE_PRIORITY:
            if role in roles:
                return role
        return "Viewer"
