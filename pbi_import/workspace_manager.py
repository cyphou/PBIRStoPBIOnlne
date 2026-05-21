"""
Workspace Manager — creates/verifies PBI Online workspaces before publishing.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class WorkspaceManager:
    """Manage Power BI workspaces for migration."""

    def __init__(self, pbi_client: Any):
        self.client = pbi_client

    def ensure_workspace(
        self,
        name: str,
        description: str | None = None,
        capacity_id: str | None = None,
    ) -> dict:
        """Ensure a workspace exists, creating it if needed."""
        existing = self.client.get_workspace_by_name(name)
        if existing:
            logger.info("Workspace '%s' already exists (id=%s)", name, existing.get("id"))
            return existing

        logger.info("Creating workspace '%s'", name)
        workspace = self.client.create_workspace(
            name=name,
            description=description or f"Migrated from PBIRS",
        )

        # Assign to capacity if specified (required for paginated reports)
        if capacity_id:
            self.client.assign_workspace_to_capacity(
                workspace_id=workspace["id"],
                capacity_id=capacity_id,
            )
            logger.info("Assigned workspace to capacity %s", capacity_id)

        return workspace

    def ensure_folder_structure(
        self,
        workspace_id: str,
        folders: list[dict],
    ) -> dict:
        """PBI Online doesn't have folders — returns mapping of PBIRS paths to flat workspace."""
        path_map = {}
        for folder in folders:
            pbirs_path = folder.get("path", "/")
            # All items go into the same workspace, flattened
            path_map[pbirs_path] = workspace_id
        return path_map
