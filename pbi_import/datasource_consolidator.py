"""
Datasource Consolidator — deduplicates identical datasource connections across reports.

Scans all extracted datasources, identifies duplicates by normalised connection
string, and produces a consolidated mapping for gateway binding.
"""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


class DatasourceConsolidator:
    """Deduplicate and consolidate datasource connections."""

    def consolidate(self, datasources: list[dict]) -> dict:
        """Group datasources by normalised connection string.

        Returns consolidated groups with canonical entries and duplicate references.
        """
        groups: dict[str, list[dict]] = {}

        for ds in datasources:
            key = self._normalise(ds.get("ConnectionString", ""))
            groups.setdefault(key, []).append(ds)

        consolidated: list[dict] = []
        duplicates_found = 0

        for key, members in groups.items():
            canonical = members[0]
            dupes = members[1:]
            duplicates_found += len(dupes)

            consolidated.append({
                "canonical": {
                    "name": canonical.get("Name", ""),
                    "connection_string": canonical.get("ConnectionString", ""),
                    "provider": canonical.get("Provider", ""),
                    "path": canonical.get("Path", ""),
                },
                "duplicates": [
                    {"name": d.get("Name", ""), "path": d.get("Path", "")}
                    for d in dupes
                ],
                "total_references": len(members),
            })

        result = {
            "groups": consolidated,
            "summary": {
                "unique_connections": len(consolidated),
                "total_datasources": len(datasources),
                "duplicates_found": duplicates_found,
                "dedup_ratio": round(
                    duplicates_found / max(len(datasources), 1) * 100, 1
                ),
            },
        }

        logger.info(
            "Consolidation: %d unique connections from %d datasources (%d duplicates)",
            len(consolidated), len(datasources), duplicates_found,
        )
        return result

    def save(self, output_dir: str, result: dict) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "datasource_consolidation.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        return path

    @staticmethod
    def _normalise(conn_str: str) -> str:
        """Normalise a connection string for deduplication.

        Strips whitespace, lowercases, removes password/token fields.
        """
        s = conn_str.strip().lower()
        # Remove passwords and tokens for comparison
        s = re.sub(r"password=[^;]*;?", "", s, flags=re.IGNORECASE)
        s = re.sub(r"pwd=[^;]*;?", "", s, flags=re.IGNORECASE)
        s = re.sub(r"token=[^;]*;?", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s+", "", s)
        return s
