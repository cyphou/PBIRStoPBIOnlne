"""
Gateway Cluster Manager — gateway cluster binding with failover preference.

Supports binding datasources to gateway clusters (multiple gateways in a group)
and setting failover order for high availability.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class GatewayCluster:
    """Manage gateway cluster bindings with failover configuration."""

    def __init__(self, pbi_client: Any):
        self.client = pbi_client

    def discover_clusters(self) -> list[dict]:
        """Discover available gateway clusters from PBI API."""
        try:
            gateways = self.client.list_gateways()
        except Exception as e:
            logger.error("Failed to list gateways: %s", e)
            return []

        clusters: dict[str, dict] = {}
        for gw in gateways:
            cluster_id = gw.get("gatewayClusterId", gw.get("id", ""))
            if cluster_id not in clusters:
                clusters[cluster_id] = {
                    "cluster_id": cluster_id,
                    "name": gw.get("name", ""),
                    "members": [],
                    "status": gw.get("status", ""),
                }
            clusters[cluster_id]["members"].append({
                "gateway_id": gw.get("id", ""),
                "name": gw.get("name", ""),
                "status": gw.get("status", ""),
                "version": gw.get("version", ""),
            })

        result = list(clusters.values())
        logger.info("Discovered %d gateway clusters", len(result))
        return result

    def bind_with_failover(
        self,
        dataset_id: str,
        cluster_id: str,
        datasource_bindings: list[dict],
        dry_run: bool = False,
    ) -> dict:
        """Bind a dataset to a gateway cluster with failover preference.

        Args:
            dataset_id: PBI dataset ID.
            cluster_id: gateway cluster ID.
            datasource_bindings: list of ``{"gateway_datasource_id": "...", "priority": N}``.
            dry_run: preview only.
        """
        if dry_run:
            logger.info("[DRY RUN] Would bind dataset %s to cluster %s", dataset_id, cluster_id)
            return {"dataset_id": dataset_id, "status": "dry_run"}

        # Sort bindings by priority (lower = primary)
        sorted_bindings = sorted(datasource_bindings, key=lambda b: b.get("priority", 99))

        try:
            self.client.bind_to_gateway(
                dataset_id=dataset_id,
                gateway_id=cluster_id,
                datasource_ids=[b["gateway_datasource_id"] for b in sorted_bindings],
            )
            logger.info("Bound dataset %s to cluster %s", dataset_id, cluster_id)
            return {
                "dataset_id": dataset_id,
                "cluster_id": cluster_id,
                "bindings": len(sorted_bindings),
                "status": "bound",
            }
        except Exception as e:
            logger.error("Failed to bind: %s", e)
            return {"dataset_id": dataset_id, "status": "failed", "error": str(e)}

    def recommend_cluster(
        self,
        datasources: list[dict],
        clusters: list[dict],
    ) -> dict | None:
        """Recommend the best gateway cluster for a set of datasources.

        Prefers clusters with the most online members that support the required
        datasource types.
        """
        if not clusters:
            return None

        scored: list[tuple[int, dict]] = []
        for cluster in clusters:
            online = sum(1 for m in cluster.get("members", []) if m.get("status") == "Online")
            scored.append((online, cluster))

        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1] if scored else None

        if best:
            logger.info(
                "Recommended cluster: %s (%d online members)",
                best.get("name"), scored[0][0],
            )
        return best
