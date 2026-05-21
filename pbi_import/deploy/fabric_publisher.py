"""
Fabric Publisher — direct publishing to Microsoft Fabric workspaces.

Uses the Fabric REST API to create items (reports, semantic models, notebooks)
directly in Fabric workspaces, bypassing the traditional PBI import flow.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_FABRIC_API = "https://api.fabric.microsoft.com/v1"


class FabricPublisher:
    """Publish items directly to Fabric workspaces via Fabric REST API."""

    def __init__(self, client: Any):
        self.client = client
        self.base_url = _FABRIC_API

    def create_workspace(
        self,
        display_name: str,
        capacity_id: str | None = None,
        description: str = "",
        dry_run: bool = False,
    ) -> dict:
        """Create a Fabric workspace."""
        if dry_run:
            logger.info("[DRY RUN] Would create Fabric workspace: %s", display_name)
            return {"id": "dry-run", "displayName": display_name}

        body: dict = {"displayName": display_name}
        if description:
            body["description"] = description
        if capacity_id:
            body["capacityId"] = capacity_id

        result = self.client.post(f"{self.base_url}/workspaces", json=body)
        ws_id = result.get("id", "")
        logger.info("Created Fabric workspace %s (%s)", display_name, ws_id)
        return result

    def publish_item(
        self,
        workspace_id: str,
        display_name: str,
        item_type: str,
        definition: dict | None = None,
        file_path: str | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Publish an item to a Fabric workspace.

        Args:
            workspace_id: target workspace ID.
            display_name: item display name.
            item_type: Fabric item type (Report, SemanticModel, Notebook, etc).
            definition: item definition payload (for API-based creation).
            file_path: path to file for upload-based creation.
            dry_run: preview only.
        """
        if dry_run:
            logger.info(
                "[DRY RUN] Would publish %s '%s' to workspace %s",
                item_type, display_name, workspace_id,
            )
            return {"id": "dry-run", "type": item_type, "displayName": display_name}

        url = f"{self.base_url}/workspaces/{workspace_id}/items"
        body: dict = {
            "displayName": display_name,
            "type": item_type,
        }

        if definition:
            body["definition"] = definition

        result = self.client.post(url, json=body)
        item_id = result.get("id", "")
        logger.info("Published %s '%s' (%s)", item_type, display_name, item_id)
        return result

    def publish_batch(
        self,
        workspace_id: str,
        items: list[dict],
        dry_run: bool = False,
    ) -> list[dict]:
        """Publish multiple items with rate-limit awareness.

        Each item dict should have: ``display_name``, ``item_type``, ``definition``.
        """
        results: list[dict] = []

        for item in items:
            result = self.publish_item(
                workspace_id=workspace_id,
                display_name=item["display_name"],
                item_type=item["item_type"],
                definition=item.get("definition"),
                file_path=item.get("file_path"),
                dry_run=dry_run,
            )
            results.append(result)

            # Respect rate limits
            if not dry_run:
                time.sleep(0.5)

        logger.info(
            "Batch publish: %d items to workspace %s", len(results), workspace_id,
        )
        return results

    def save_manifest(self, output_dir: str, results: list[dict]) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "fabric_publish_manifest.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        return path
