"""
Lineage Extractor — maps PBIRS catalog lineage for PBI lineage view.

Extracts datasource → dataset → report dependency chains from PBIRS
and outputs them in a format that can be preserved in PBI Online lineage.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class LineageExtractor:
    """Extract and map PBIRS content lineage (datasource → report chains)."""

    def __init__(self, catalog: list[dict]):
        self.catalog = catalog

    def extract(self) -> dict:
        """Build lineage graph from catalog metadata.

        Returns a lineage structure with nodes and edges.
        """
        nodes: list[dict] = []
        edges: list[dict] = []

        # Index items by path and ID
        by_id: dict[str, dict] = {}
        by_path: dict[str, dict] = {}
        for item in self.catalog:
            item_id = item.get("Id", "")
            path = item.get("Path", "")
            by_id[item_id] = item
            by_path[path] = item

            nodes.append({
                "id": item_id,
                "name": item.get("Name", ""),
                "path": path,
                "type": item.get("Type", ""),
            })

        # Build edges from datasource references
        for item in self.catalog:
            item_id = item.get("Id", "")
            item_type = item.get("Type", "")

            # Report → DataSource edges
            datasources = item.get("DataSources", [])
            for ds in datasources:
                ds_path = ds.get("Path", "")
                if ds_path and ds_path in by_path:
                    edges.append({
                        "source": by_path[ds_path]["Id"],
                        "target": item_id,
                        "relationship": "datasource",
                    })

                # Inline connection string → synthetic node
                conn_string = ds.get("ConnectionString", "")
                if conn_string and not ds_path:
                    ds_node_id = f"ds:{conn_string[:64]}"
                    if not any(n["id"] == ds_node_id for n in nodes):
                        nodes.append({
                            "id": ds_node_id,
                            "name": ds.get("Name", conn_string[:50]),
                            "type": "ExternalDataSource",
                            "connection": conn_string,
                        })
                    edges.append({
                        "source": ds_node_id,
                        "target": item_id,
                        "relationship": "connection",
                    })

            # Report → Dataset edges (shared datasets)
            shared_ds = item.get("SharedDataSets", [])
            for sds in shared_ds:
                ref_path = sds.get("SharedDataSetReference", "")
                if ref_path and ref_path in by_path:
                    edges.append({
                        "source": by_path[ref_path]["Id"],
                        "target": item_id,
                        "relationship": "shared_dataset",
                    })

            # Subreport edges
            subreports = item.get("Subreports", [])
            for sub in subreports:
                sub_path = sub.get("ReportPath", sub.get("path", ""))
                if sub_path and sub_path in by_path:
                    edges.append({
                        "source": item_id,
                        "target": by_path[sub_path]["Id"],
                        "relationship": "subreport",
                    })

        lineage = {
            "nodes": nodes,
            "edges": edges,
            "summary": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "by_type": self._count_by_type(nodes),
                "by_relationship": self._count_by_key(edges, "relationship"),
            },
        }

        logger.info(
            "Lineage: %d nodes, %d edges extracted",
            len(nodes), len(edges),
        )
        return lineage

    def save(self, output_dir: str, lineage: dict | None = None) -> Path:
        """Save lineage graph to disk."""
        if lineage is None:
            lineage = self.extract()
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "lineage.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(lineage, f, indent=2, default=str)
        logger.info("Lineage saved to %s", path)
        return path

    @staticmethod
    def _count_by_type(nodes: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for n in nodes:
            t = n.get("type", "unknown")
            counts[t] = counts.get(t, 0) + 1
        return counts

    @staticmethod
    def _count_by_key(items: list[dict], key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            v = item.get(key, "unknown")
            counts[v] = counts.get(v, 0) + 1
        return counts
