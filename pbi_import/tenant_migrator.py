"""
Tenant Migrator — tenant-to-tenant migration using service principal auth.

Supports migrating content between two separate PBI tenants by exporting
from a source tenant and importing into a target tenant with independent
authentication contexts.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TenantMigrator:
    """Migrate PBI content between two separate Azure AD tenants."""

    def __init__(
        self,
        source_client: Any,
        target_client: Any,
    ):
        self.source = source_client
        self.target = target_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def plan(
        self,
        source_workspace_id: str,
        target_workspace_id: str,
    ) -> dict:
        """Generate a migration plan between tenants.

        Returns items in the source workspace that need to be migrated.
        """
        source_items = self._list_source_content(source_workspace_id)
        target_items = self._list_target_content(target_workspace_id)

        existing_names = {i.get("name", "") for i in target_items}

        plan: dict[str, list[dict]] = {
            "to_migrate": [],
            "already_exists": [],
            "summary": {},
        }

        for item in source_items:
            name = item.get("name", "")
            if name in existing_names:
                plan["already_exists"].append(item)
            else:
                plan["to_migrate"].append(item)

        plan["summary"] = {
            "source_total": len(source_items),
            "target_existing": len(target_items),
            "to_migrate": len(plan["to_migrate"]),
            "already_exists": len(plan["already_exists"]),
        }

        logger.info(
            "Tenant migration plan: %d to migrate, %d already exist",
            len(plan["to_migrate"]),
            len(plan["already_exists"]),
        )
        return plan

    def execute(
        self,
        source_workspace_id: str,
        target_workspace_id: str,
        plan: dict | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Execute tenant-to-tenant migration."""
        if plan is None:
            plan = self.plan(source_workspace_id, target_workspace_id)

        results: dict[str, list[dict]] = {
            "migrated": [], "failed": [], "skipped": [],
        }

        for item in plan.get("to_migrate", []):
            item_type = item.get("type", "report")
            name = item.get("name", "")

            if dry_run:
                logger.info("[DRY RUN] Would migrate %s '%s'", item_type, name)
                results["skipped"].append({"name": name, "reason": "dry_run"})
                continue

            try:
                result = self._migrate_item(
                    item, source_workspace_id, target_workspace_id,
                )
                results["migrated"].append(result)
            except Exception as e:
                logger.error("Failed to migrate '%s': %s", name, e)
                results["failed"].append({"name": name, "error": str(e)})

        logger.info(
            "Tenant migration: %d migrated, %d failed, %d skipped",
            len(results["migrated"]),
            len(results["failed"]),
            len(results["skipped"]),
        )
        return results

    def save_plan(self, output_dir: str, plan: dict) -> Path:
        """Save migration plan to disk."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "tenant_migration_plan.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2, default=str)
        return path

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _list_source_content(self, workspace_id: str) -> list[dict]:
        """List reports and datasets in source tenant workspace."""
        items: list[dict] = []
        try:
            reports = self.source.list_reports(workspace_id)
            for r in reports:
                r["type"] = "report"
                items.append(r)
        except Exception as e:
            logger.warning("Failed to list source reports: %s", e)
        try:
            datasets = self.source.list_datasets(workspace_id)
            for d in datasets:
                d["type"] = "dataset"
                items.append(d)
        except Exception as e:
            logger.warning("Failed to list source datasets: %s", e)
        return items

    def _list_target_content(self, workspace_id: str) -> list[dict]:
        """List existing content in target tenant workspace."""
        items: list[dict] = []
        try:
            items.extend(self.target.list_reports(workspace_id))
        except Exception:
            pass
        try:
            items.extend(self.target.list_datasets(workspace_id))
        except Exception:
            pass
        return items

    def _migrate_item(
        self,
        item: dict,
        source_ws: str,
        target_ws: str,
    ) -> dict:
        """Export from source and import to target."""
        name = item.get("name", "")
        item_id = item.get("id", "")
        item_type = item.get("type", "report")

        # Export from source
        export_data = self.source.export_report(source_ws, item_id)

        # Import to target
        import_result = self.target.import_file(
            workspace_id=target_ws,
            display_name=name,
            file_content=export_data,
        )

        return {
            "name": name,
            "type": item_type,
            "source_id": item_id,
            "target_id": import_result.get("id", ""),
            "status": "migrated",
        }
