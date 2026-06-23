"""
Wave Planner — dependency-aware grouping of items into migration waves.

Reads catalog + lineage (PBIRS datasets/datasources → reports → apps) and
topologically sorts the dependency graph into safe execution waves so that
parents (datasets) always land before children (reports). Cycles are detected
and reported; orphaned items go into the first available wave.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


class WavePlanner:
    """Group catalog items into dependency-safe migration waves."""

    def __init__(self, max_wave_size: int | None = None):
        self.max_wave_size = max_wave_size

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def build_graph(self, catalog: list[dict]) -> tuple[dict[str, set[str]], dict[str, dict]]:
        """Return ``(adjacency, items_by_id)`` from a catalog with lineage info.

        Each catalog entry may declare its dependencies in one of:
        ``DependsOn``, ``dependsOn``, or ``DataSourceIds``/``DatasetId``.
        """
        items_by_id: dict[str, dict] = {}
        deps: dict[str, set[str]] = {}
        for item in catalog:
            item_id = str(item.get("Id") or item.get("id") or item.get("Name"))
            items_by_id[item_id] = item
            edges: set[str] = set()
            for key in ("DependsOn", "dependsOn"):
                val = item.get(key)
                if isinstance(val, list):
                    edges.update(str(v) for v in val)
            for key in ("DataSourceIds", "DatasetId", "datasetId", "dataSourceIds"):
                val = item.get(key)
                if isinstance(val, list):
                    edges.update(str(v) for v in val)
                elif isinstance(val, str):
                    edges.add(val)
            deps[item_id] = edges
        return deps, items_by_id

    # ------------------------------------------------------------------
    # Wave planning
    # ------------------------------------------------------------------

    def plan(self, catalog: list[dict]) -> dict:
        """Topologically sort *catalog* into waves.

        Returns ``{"waves": [[item, ...], ...], "cycles": [[id, ...]], "orphans": [...]}``.
        """
        deps, items = self.build_graph(catalog)
        remaining: dict[str, set[str]] = {k: set(v) & set(items) for k, v in deps.items()}
        waves: list[list[dict]] = []
        cycles: list[list[str]] = []
        orphans: list[dict] = []

        while remaining:
            ready = [iid for iid, edges in remaining.items() if not edges]
            if not ready:
                cycle = sorted(remaining.keys())
                logger.warning("Cycle detected; %d items broken into final wave", len(cycle))
                cycles.append(cycle)
                waves.extend(self._chunk([items[i] for i in cycle]))
                break

            wave_items = [items[i] for i in sorted(ready)]
            waves.extend(self._chunk(wave_items))
            for iid in ready:
                remaining.pop(iid, None)
                for edges in remaining.values():
                    edges.discard(iid)

        for iid, item in items.items():
            if all(item not in w for w in waves):
                orphans.append(item)
        if orphans and waves:
            waves[0].extend(orphans)

        logger.info("Planned %d waves over %d items", len(waves), len(items))
        return {
            "wave_count": len(waves),
            "item_count": len(items),
            "waves": [[_summary(i) for i in wave] for wave in waves],
            "cycles": cycles,
            "orphans": [_summary(o) for o in orphans],
        }

    def write_plan(self, plan: dict, output_path: str | Path) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        logger.info("Wrote wave plan to %s", path)
        return path

    def get_wave(self, plan: dict, wave_index: int) -> list[dict]:
        """Return the items in wave *wave_index* (1-based)."""
        waves = plan.get("waves", [])
        if wave_index < 1 or wave_index > len(waves):
            raise IndexError(f"wave_index {wave_index} out of range (1..{len(waves)})")
        return waves[wave_index - 1]

    # ------------------------------------------------------------------

    def _chunk(self, items: Iterable[dict]) -> list[list[dict]]:
        items = list(items)
        if not self.max_wave_size or len(items) <= self.max_wave_size:
            return [items] if items else []
        return [items[i:i + self.max_wave_size] for i in range(0, len(items), self.max_wave_size)]


def _summary(item: dict) -> dict:
    return {
        "id": item.get("Id") or item.get("id"),
        "name": item.get("Name") or item.get("name"),
        "type": item.get("Type") or item.get("type"),
        "path": item.get("Path") or item.get("path"),
    }
