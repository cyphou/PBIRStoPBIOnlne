"""
Gateway Mapper — maps on-premises datasources to gateway bindings in PBI Online.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class GatewayMapper:
    """Map PBIRS datasource connections to PBI Online gateway datasources."""

    def __init__(self, pbi_client: Any, gateway_mapping_file: str | None = None):
        self.client = pbi_client
        self.mapping: dict = {}

        if gateway_mapping_file:
            with open(gateway_mapping_file, encoding="utf-8") as f:
                self.mapping = json.load(f)

    def bind_datasets(
        self,
        workspace_id: str,
        published_items: list[dict],
        dry_run: bool = False,
    ) -> dict:
        """Bind published datasets to gateway datasources."""
        results: dict[str, list] = {"bound": [], "skipped": [], "failed": []}

        for item in published_items:
            dataset_id = item.get("dataset_id", "")
            if not dataset_id:
                results["skipped"].append({
                    "name": item.get("name"),
                    "reason": "No dataset ID",
                })
                continue

            try:
                result = self._bind_dataset(dataset_id, item, dry_run)
                results["bound"].append(result)
            except Exception as e:
                logger.error("Failed to bind %s: %s", item.get("name"), e)
                results["failed"].append({
                    "name": item.get("name"),
                    "error": str(e),
                })

        return results

    def _bind_dataset(self, dataset_id: str, item: dict, dry_run: bool) -> dict:
        """Bind a single dataset to a gateway."""
        name = item.get("name", "")

        # Find matching gateway mapping
        gateway_info = self.mapping.get(name)
        if not gateway_info:
            return {"name": name, "status": "no_mapping"}

        if dry_run:
            logger.info("[DRY RUN] Would bind %s to gateway %s", name, gateway_info.get("gateway_id"))
            return {"name": name, "status": "dry_run"}

        self.client.bind_to_gateway(
            dataset_id=dataset_id,
            gateway_id=gateway_info["gateway_id"],
            datasource_ids=gateway_info.get("datasource_ids", []),
        )

        logger.info("Bound %s to gateway %s", name, gateway_info["gateway_id"])
        return {"name": name, "status": "bound", "gateway_id": gateway_info["gateway_id"]}

    def discover_gateways(self) -> list[dict]:
        """List available gateways in the PBI Online tenant."""
        return self.client.list_gateways()

    def generate_mapping_template(
        self,
        datasources: dict,
        output_path: str,
    ) -> None:
        """Generate a gateway mapping template from extracted datasources."""
        template = {}
        for ds in datasources.get("embedded_datasources", []):
            item_name = ds.get("item_name", "")
            if item_name not in template:
                template[item_name] = {
                    "gateway_id": "",
                    "datasource_ids": [],
                    "connection_info": ds.get("datasource", {}),
                }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2)

        logger.info("Generated gateway mapping template at %s (%d items)", output_path, len(template))
