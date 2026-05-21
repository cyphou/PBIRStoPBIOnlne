"""
Deduplicator — cross-server content deduplication.

When migrating from multiple PBIRS/SSRS servers, the same report or dataset
may exist on multiple servers. This module detects duplicates by content hash
and produces a deduplicated migration plan.
"""

import hashlib
import json
import logging
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


class Deduplicator:
    """Detect and resolve cross-server content duplicates."""

    def scan(self, catalogs: dict[str, list[dict]]) -> dict:
        """Scan multiple server catalogs for duplicate content.

        Args:
            catalogs: ``{server_name: [catalog_items]}``.
        """
        # Build fingerprint index
        fingerprints: dict[str, list[dict]] = defaultdict(list)

        for server_name, items in catalogs.items():
            for item in items:
                fp = self._fingerprint(item)
                fingerprints[fp].append({
                    "server": server_name,
                    "name": item.get("Name", ""),
                    "path": item.get("Path", ""),
                    "type": item.get("Type", ""),
                    "modified": item.get("ModifiedDate", ""),
                    "size": item.get("Size", 0),
                })

        # Separate unique from duplicate
        unique: list[dict] = []
        duplicates: list[dict] = []

        for fp, entries in fingerprints.items():
            if len(entries) == 1:
                unique.append(entries[0])
            else:
                # Pick canonical (latest modified, or first by server priority)
                canonical = self._pick_canonical(entries)
                duplicates.append({
                    "canonical": canonical,
                    "duplicates": [e for e in entries if e is not canonical],
                    "fingerprint": fp,
                    "count": len(entries),
                })

        result = {
            "unique_items": unique,
            "duplicate_groups": duplicates,
            "summary": {
                "total_items": sum(len(items) for items in catalogs.values()),
                "unique_items": len(unique),
                "duplicate_groups": len(duplicates),
                "items_deduplicated": sum(d["count"] - 1 for d in duplicates),
                "servers_scanned": len(catalogs),
            },
        }

        logger.info(
            "Deduplication: %d unique, %d duplicate groups (%d items removed)",
            len(unique), len(duplicates),
            result["summary"]["items_deduplicated"],
        )
        return result

    def deduplicated_catalog(self, scan_result: dict) -> list[dict]:
        """Return a flat, deduplicated catalog (canonical entries only)."""
        items = list(scan_result.get("unique_items", []))
        for group in scan_result.get("duplicate_groups", []):
            items.append(group["canonical"])
        return items

    def save(self, output_dir: str, result: dict) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "deduplication_report.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        return path

    @staticmethod
    def _fingerprint(item: dict) -> str:
        """Create a content fingerprint for deduplication.

        Uses name + type + content hash if available, otherwise name + type + size.
        """
        content_hash = item.get("ContentHash", "")
        if content_hash:
            return content_hash

        key = f"{item.get('Name', '')}|{item.get('Type', '')}|{item.get('Size', 0)}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    @staticmethod
    def _pick_canonical(entries: list[dict]) -> dict:
        """Pick the canonical entry from duplicates (most recently modified)."""
        return max(entries, key=lambda e: e.get("modified", ""))
