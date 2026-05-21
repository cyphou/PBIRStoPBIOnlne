"""
Folder Mapper — maps PBIRS folder hierarchy to PBI Online workspace rules.

Converts the flat PBIRS catalog folder tree into workspace assignment rules
so that each logical folder (or subtree) maps to a target PBI Online workspace.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class FolderMapper:
    """Map PBIRS folder paths to PBI Online workspace targets."""

    def __init__(self, rules: list[dict] | None = None):
        """Initialise with optional mapping rules.

        Each rule is ``{"folder": "/Sales", "workspace_id": "...", "workspace_name": "..."}``.
        Rules are matched longest-prefix-first.
        """
        self.rules: list[dict] = sorted(
            rules or [],
            key=lambda r: len(r.get("folder", "")),
            reverse=True,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def from_file(cls, path: str) -> "FolderMapper":
        """Load mapping rules from a JSON file."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        rules = data if isinstance(data, list) else data.get("rules", [])
        logger.info("Loaded %d folder-mapping rules from %s", len(rules), path)
        return cls(rules)

    @classmethod
    def auto_generate(cls, catalog: list[dict], depth: int = 1) -> "FolderMapper":
        """Auto-generate one workspace per top-level folder.

        Args:
            catalog: PBIRS catalog items with ``Path`` fields.
            depth: folder depth for workspace splitting (1 = top-level).
        """
        folders: set[str] = set()
        for item in catalog:
            parts = [p for p in item.get("Path", "").split("/") if p]
            if len(parts) > depth:
                folder = "/" + "/".join(parts[:depth])
                folders.add(folder)

        rules = [
            {"folder": f, "workspace_name": f.strip("/").replace("/", " - ")}
            for f in sorted(folders)
        ]
        logger.info("Auto-generated %d workspace mapping rules (depth=%d)", len(rules), depth)
        return cls(rules)

    def resolve(self, item_path: str) -> dict | None:
        """Return the workspace rule that matches *item_path* (longest prefix wins)."""
        normalised = item_path.rstrip("/")
        for rule in self.rules:
            prefix = rule["folder"].rstrip("/")
            if normalised == prefix or normalised.startswith(prefix + "/"):
                return rule
        return None

    def resolve_all(self, catalog: list[dict]) -> dict[str, list[dict]]:
        """Partition *catalog* items by target workspace.

        Returns ``{workspace_name: [items…]}``.
        """
        result: dict[str, list[dict]] = {}
        unmapped: list[dict] = []

        for item in catalog:
            rule = self.resolve(item.get("Path", ""))
            if rule:
                ws = rule.get("workspace_name") or rule.get("workspace_id", "default")
                result.setdefault(ws, []).append(item)
            else:
                unmapped.append(item)

        if unmapped:
            result["_unmapped"] = unmapped
            logger.warning("%d items did not match any folder rule", len(unmapped))

        return result

    def save(self, output_path: str) -> Path:
        """Persist current rules to a JSON file."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"rules": self.rules}, f, indent=2)
        logger.info("Saved %d folder-mapping rules to %s", len(self.rules), out)
        return out
