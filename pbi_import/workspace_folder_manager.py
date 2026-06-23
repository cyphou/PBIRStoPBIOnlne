"""
Workspace Folder Manager — preserves PBIRS folder hierarchy as PBI Online workspace folders.

PBI Online introduced native workspace folders (Fabric REST API). This module
walks the PBIRS catalog tree and recreates the hierarchy inside the target
workspace, returning a ``path → folder_id`` map so publishers can place each
item in the correct folder.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class WorkspaceFolderManager:
    """Create and resolve PBI workspace folders from PBIRS paths."""

    def __init__(self, pbi_client: Any):
        self.client = pbi_client

    def build_tree(self, catalog: list[dict]) -> list[str]:
        """Return every unique folder path implied by *catalog* (PBIRS-style)."""
        paths: set[str] = set()
        for item in catalog:
            raw = item.get("Path", "") or item.get("path", "")
            if not raw:
                continue
            parts = [p for p in raw.split("/") if p]
            # Drop the leaf (item name); we want folders only.
            for i in range(1, len(parts)):
                paths.add("/" + "/".join(parts[:i]))
        ordered = sorted(paths, key=lambda p: (p.count("/"), p))
        logger.info("Discovered %d folder paths", len(ordered))
        return ordered

    def ensure_folders(
        self,
        workspace_id: str,
        folder_paths: list[str],
        dry_run: bool = False,
    ) -> dict[str, str]:
        """Create the folder tree inside *workspace_id*.

        Returns a ``{folder_path: folder_id}`` mapping (including a sentinel
        ``"/"`` for the workspace root). When *dry_run* is True, IDs are
        synthetic placeholders.
        """
        mapping: dict[str, str] = {"/": workspace_id}
        for path in folder_paths:
            parent = "/" + "/".join(path.strip("/").split("/")[:-1])
            parent = parent if parent != "/" else "/"
            parent_id = mapping.get(parent)
            name = path.rsplit("/", 1)[-1]

            if dry_run:
                mapping[path] = f"dry-run-folder-{path}"
                logger.info("[DRY RUN] Would create folder '%s' under %s", name, parent)
                continue

            try:
                created = self._create_folder(workspace_id, name, parent_id)
                mapping[path] = created.get("id") or created.get("folderId") or ""
                logger.info("Created folder '%s' (id=%s)", path, mapping[path])
            except Exception as exc:  # noqa: BLE001
                logger.warning("Folder '%s' creation failed: %s", path, exc)
                mapping[path] = ""
        return mapping

    def resolve_item_folder(self, item_path: str, mapping: dict[str, str]) -> str | None:
        """Return the folder_id for the directory containing *item_path*."""
        parts = [p for p in item_path.split("/") if p]
        if not parts:
            return mapping.get("/")
        parent = "/" + "/".join(parts[:-1])
        return mapping.get(parent) or mapping.get("/")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _create_folder(self, workspace_id: str, name: str, parent_id: str | None) -> dict:
        """Call the underlying PBI/Fabric client to create a folder.

        The PBI client is expected to expose ``create_folder(workspace_id, name,
        parent_folder_id=None)``. Implementations that lack this method should
        raise AttributeError, which the caller logs and continues.
        """
        if not hasattr(self.client, "create_folder"):
            raise AttributeError("pbi_client does not support create_folder")
        return self.client.create_folder(
            workspace_id=workspace_id,
            name=name,
            parent_folder_id=parent_id if parent_id and parent_id != workspace_id else None,
        )
