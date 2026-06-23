"""Benchmark harness — synthetic catalog generator + phase timer.

Lets you measure how the migration pipeline scales with catalog size without
needing a real PBIRS server. Generates a synthetic ``inventory.json`` with
configurable numbers of reports, datasets, folders, then times user-supplied
phase callables and writes a comparable JSON report.
"""

from __future__ import annotations

import json
import logging
import random
import statistics
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


_TYPES = ["PowerBIReport", "Report", "DataSet", "Kpi", "MobileReport"]


def generate_synthetic_catalog(
    size: int,
    seed: int = 42,
    folders: int = 20,
) -> dict[str, Any]:
    """Build a deterministic synthetic catalog of ``size`` items."""
    rng = random.Random(seed)
    folder_paths = [f"/synthetic/folder-{i:03d}" for i in range(folders)]
    items: list[dict[str, Any]] = []
    for i in range(size):
        t = rng.choice(_TYPES)
        items.append({
            "Id": f"syn-{i:06d}",
            "Name": f"item-{i:06d}",
            "Type": t,
            "Path": f"{rng.choice(folder_paths)}/item-{i:06d}",
            "Size": rng.randint(1024, 5_000_000),
            "ModifiedDate": "2026-01-01T00:00:00Z",
            "Owner": f"user{rng.randint(1, 25)}@example.com",
        })
    return {
        "metadata": {"synthetic": True, "seed": seed, "size": size},
        "items": items,
        "powerbi_reports": [i for i in items if i["Type"] == "PowerBIReport"],
        "paginated_reports": [i for i in items if i["Type"] == "Report"],
        "datasets": [i for i in items if i["Type"] == "DataSet"],
        "kpis": [i for i in items if i["Type"] == "Kpi"],
        "mobile_reports": [i for i in items if i["Type"] == "MobileReport"],
        "folders": [{"Path": p, "Name": p.rsplit("/", 1)[-1]} for p in folder_paths],
    }


def write_synthetic_catalog(
    size: int,
    output_path: str | Path,
    seed: int = 42,
) -> Path:
    """Generate + write a synthetic ``inventory.json``."""
    catalog = generate_synthetic_catalog(size=size, seed=seed)
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(catalog, f, default=str)
    logger.info("Wrote synthetic catalog (%d items) → %s", size, p)
    return p


class BenchmarkHarness:
    """Time-and-compare multiple phase callables across catalog sizes."""

    def __init__(self):
        self.results: list[dict[str, Any]] = []

    def run(
        self,
        name: str,
        fn: Callable[[dict], Any],
        catalog: dict,
        repeats: int = 1,
    ) -> dict[str, Any]:
        """Run ``fn(catalog)`` ``repeats`` times and record the timings."""
        timings: list[float] = []
        for _ in range(max(1, repeats)):
            start = time.perf_counter()
            fn(catalog)
            timings.append(time.perf_counter() - start)
        record = {
            "name": name,
            "catalog_size": len(catalog.get("items", [])),
            "repeats": len(timings),
            "min_seconds": round(min(timings), 4),
            "max_seconds": round(max(timings), 4),
            "mean_seconds": round(statistics.fmean(timings), 4),
            "median_seconds": round(statistics.median(timings), 4),
        }
        self.results.append(record)
        return record

    def compare(self) -> dict[str, Any]:
        """Group results by phase name."""
        grouped: dict[str, list[dict]] = {}
        for r in self.results:
            grouped.setdefault(r["name"], []).append(r)
        # Sort each group by catalog size for nicer reporting
        for name in grouped:
            grouped[name].sort(key=lambda x: x["catalog_size"])
        return grouped

    def write_report(self, path: str | Path) -> None:
        payload = {
            "results": self.results,
            "grouped": self.compare(),
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        logger.info("Benchmark report written → %s", path)
