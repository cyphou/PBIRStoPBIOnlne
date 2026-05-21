"""
Multi-Workspace Manager — orchestrates migration across multiple PBI Online workspaces.

Uses FolderMapper rules to partition PBIRS content into separate workspaces,
creating them as needed and tracking per-workspace migration state.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MultiWorkspaceManager:
    """Manage migration across multiple PBI Online workspaces."""

    def __init__(self, pbi_client: Any):
        self.client = pbi_client
        self._cache: dict[str, str] = {}  # workspace_name → workspace_id

    # ------------------------------------------------------------------
    # Workspace lifecycle
    # ------------------------------------------------------------------

    def ensure_workspaces(
        self,
        workspace_plan: dict[str, list[dict]],
        dry_run: bool = False,
    ) -> dict[str, str]:
        """Create or resolve workspaces for each partition.

        Args:
            workspace_plan: ``{workspace_name: [items…]}`` from FolderMapper.
        Returns:
            ``{workspace_name: workspace_id}``
        """
        mapping: dict[str, str] = {}

        for ws_name in workspace_plan:
            if ws_name.startswith("_"):
                continue
            if dry_run:
                logger.info("[DRY RUN] Would create/resolve workspace '%s'", ws_name)
                mapping[ws_name] = f"dry-run-{ws_name}"
                continue

            ws_id = self._resolve_or_create(ws_name)
            mapping[ws_name] = ws_id

        self._cache.update(mapping)
        logger.info("Resolved %d workspaces", len(mapping))
        return mapping

    def get_workspace_id(self, workspace_name: str) -> str | None:
        """Look up a workspace ID by name from cache or API."""
        if workspace_name in self._cache:
            return self._cache[workspace_name]
        return None

    # ------------------------------------------------------------------
    # Dispatch helpers
    # ------------------------------------------------------------------

    def dispatch_items(
        self,
        workspace_plan: dict[str, list[dict]],
        workspace_mapping: dict[str, str],
    ) -> list[dict]:
        """Return a flat list of ``(item, workspace_id)`` pairs for migration."""
        dispatch: list[dict] = []
        for ws_name, items in workspace_plan.items():
            ws_id = workspace_mapping.get(ws_name, "")
            for item in items:
                dispatch.append({
                    "item": item,
                    "workspace_name": ws_name,
                    "workspace_id": ws_id,
                })
        return dispatch

    def save_mapping(self, output_dir: str, mapping: dict[str, str]) -> Path:
        """Persist workspace mapping to disk."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "workspace_mapping.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2)
        logger.info("Saved workspace mapping to %s", path)
        return path

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_or_create(self, name: str) -> str:
        """Find existing workspace or create a new one."""
        try:
            workspaces = self.client.list_workspaces()
            for ws in workspaces:
                if ws.get("name") == name:
                    logger.info("Found existing workspace '%s' (%s)", name, ws["id"])
                    return ws["id"]
        except Exception as e:
            logger.warning("Failed to list workspaces: %s", e)

        try:
            result = self.client.create_workspace(name)
            ws_id = result.get("id", "")
            logger.info("Created workspace '%s' (%s)", name, ws_id)
            return ws_id
        except Exception as e:
            logger.error("Failed to create workspace '%s': %s", name, e)
            raise
