"""
AD Group Provisioner — creates Azure AD groups from on-prem AD groups via Graph API.

Reads the security extraction output and provisions matching Azure AD security
groups, optionally adding members based on a user mapping file.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ADGroupProvisioner:
    """Provision Azure AD groups mirroring on-prem AD groups."""

    GRAPH_BASE = "https://graph.microsoft.com/v1.0"

    def __init__(self, graph_client: Any | None = None):
        """Initialise with an optional Microsoft Graph client.

        The graph_client must support ``.post(url, json=...)`` and ``.get(url)``
        patterns (e.g., a thin wrapper around ``urllib.request``).
        """
        self.client = graph_client

    def plan(
        self,
        security_data: dict,
        tenant_mapping: dict[str, str] | None = None,
    ) -> list[dict]:
        """Generate a provisioning plan for AD groups.

        Args:
            security_data: output from SecurityExtractor.
            tenant_mapping: ``{on_prem_name: azure_ad_upn}`` user mapping.
        """
        principals = security_data.get("principals", [])
        mapping = tenant_mapping or {}

        plan: list[dict] = []
        for p in principals:
            if p.get("type") != "Group":
                continue

            name = p.get("name", "")
            domain = p.get("domain", "")
            members_on_prem = p.get("members", [])

            # Map members
            mapped_members = []
            unmapped_members = []
            for m in members_on_prem:
                azure_upn = mapping.get(m)
                if azure_upn:
                    mapped_members.append(azure_upn)
                else:
                    unmapped_members.append(m)

            plan.append({
                "on_prem_name": name,
                "domain": domain,
                "azure_ad_name": f"Migrated-{name}",
                "mapped_members": mapped_members,
                "unmapped_members": unmapped_members,
                "ssrs_roles": p.get("ssrs_roles", []),
            })

        logger.info("AD group provisioning plan: %d groups", len(plan))
        return plan

    def provision(
        self,
        plan: list[dict],
        dry_run: bool = False,
    ) -> dict:
        """Create Azure AD groups from the plan.

        Requires a configured Graph API client.
        """
        results: dict[str, list[dict]] = {"created": [], "failed": [], "skipped": []}

        if not self.client:
            logger.warning("No Graph client configured — generating plan only")
            return {"created": [], "failed": [], "skipped": plan}

        for group in plan:
            azure_name = group["azure_ad_name"]
            if dry_run:
                logger.info("[DRY RUN] Would create group '%s'", azure_name)
                results["skipped"].append({**group, "reason": "dry_run"})
                continue

            try:
                group_id = self._create_group(azure_name)
                for member_upn in group.get("mapped_members", []):
                    self._add_member(group_id, member_upn)

                results["created"].append({
                    **group,
                    "azure_ad_group_id": group_id,
                    "members_added": len(group.get("mapped_members", [])),
                })
            except Exception as e:
                logger.error("Failed to create group '%s': %s", azure_name, e)
                results["failed"].append({**group, "error": str(e)})

        return results

    def save_plan(self, output_dir: str, plan: list[dict]) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "ad_group_plan.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)
        logger.info("AD group plan saved to %s", path)
        return path

    def _create_group(self, name: str) -> str:
        """Create an Azure AD security group via Graph API."""
        payload = {
            "displayName": name,
            "mailEnabled": False,
            "mailNickname": name.replace(" ", "_").lower(),
            "securityEnabled": True,
            "groupTypes": [],
        }
        result = self.client.post(f"{self.GRAPH_BASE}/groups", json=payload)
        return result.get("id", "")

    def _add_member(self, group_id: str, user_upn: str) -> None:
        """Add a user to an Azure AD group."""
        # Resolve user ID from UPN
        user = self.client.get(f"{self.GRAPH_BASE}/users/{user_upn}")
        user_id = user.get("id", "")
        if not user_id:
            logger.warning("Could not resolve user '%s'", user_upn)
            return

        self.client.post(
            f"{self.GRAPH_BASE}/groups/{group_id}/members/$ref",
            json={"@odata.id": f"{self.GRAPH_BASE}/directoryObjects/{user_id}"},
        )
