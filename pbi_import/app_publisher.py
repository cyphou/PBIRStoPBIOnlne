"""
App Publisher — publishes PBI Online workspace apps with audience configuration.

Wraps the Power BI REST API ``/apps`` endpoints to create and update
workspace apps, configure audiences, and manage access lists.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class AppPublisher:
    """Publish and manage PBI Online workspace apps."""

    def __init__(self, pbi_client: Any):
        self.client = pbi_client

    def publish(
        self,
        workspace_id: str,
        audiences: list[dict] | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Publish a workspace as an app.

        Args:
            workspace_id: target workspace.
            audiences: list of ``{"name": "...", "users": [...], "groups": [...]}``.
            dry_run: preview only.
        """
        if dry_run:
            logger.info("[DRY RUN] Would publish app for workspace %s", workspace_id)
            return {"workspace_id": workspace_id, "status": "dry_run"}

        payload: dict = {}
        if audiences:
            payload["targetAudiences"] = [
                self._build_audience(a) for a in audiences
            ]

        result = self.client.publish_app(workspace_id, payload)
        app_id = result.get("id", "")
        logger.info("Published app %s for workspace %s", app_id, workspace_id)
        return {
            "workspace_id": workspace_id,
            "app_id": app_id,
            "status": "published",
            "audiences": len(audiences or []),
        }

    def update(
        self,
        workspace_id: str,
        audiences: list[dict] | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Update an existing workspace app."""
        if dry_run:
            logger.info("[DRY RUN] Would update app for workspace %s", workspace_id)
            return {"workspace_id": workspace_id, "status": "dry_run"}

        payload: dict = {}
        if audiences:
            payload["targetAudiences"] = [
                self._build_audience(a) for a in audiences
            ]

        result = self.client.update_app(workspace_id, payload)
        logger.info("Updated app for workspace %s", workspace_id)
        return {"workspace_id": workspace_id, "status": "updated", **result}

    @staticmethod
    def _build_audience(audience: dict) -> dict:
        """Build a PBI API audience payload."""
        return {
            "audienceName": audience.get("name", "Default"),
            "users": [
                {"emailAddress": u} for u in audience.get("users", [])
            ],
            "groups": [
                {"groupId": g} for g in audience.get("groups", [])
            ],
        }
