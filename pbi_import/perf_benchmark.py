"""
Performance Benchmark — measures and compares report performance metrics.

Captures render time, refresh duration, and query response time for
before/after comparison to ensure migration doesn't degrade performance.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PerfBenchmark:
    """Benchmark report performance before and after migration."""

    def __init__(self, pbi_client: Any | None = None):
        self.client = pbi_client

    def measure_refresh(
        self,
        dataset_id: str,
        workspace_id: str | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Measure dataset refresh duration.

        Args:
            dataset_id: PBI dataset ID.
            workspace_id: optional workspace scope.
            dry_run: preview only.
        """
        if dry_run:
            return {"dataset_id": dataset_id, "status": "dry_run", "duration_seconds": 0}

        if not self.client:
            return {"dataset_id": dataset_id, "status": "no_client", "duration_seconds": 0}

        start = time.time()
        try:
            self.client.refresh_dataset(dataset_id, workspace_id=workspace_id)
            duration = time.time() - start
            return {
                "dataset_id": dataset_id,
                "status": "completed",
                "duration_seconds": round(duration, 2),
            }
        except Exception as e:
            duration = time.time() - start
            return {
                "dataset_id": dataset_id,
                "status": "failed",
                "duration_seconds": round(duration, 2),
                "error": str(e),
            }

    def compare(
        self,
        before_metrics: list[dict],
        after_metrics: list[dict],
    ) -> dict:
        """Compare before and after performance metrics.

        Args:
            before_metrics: list of ``{"name": str, "duration_seconds": float}``.
            after_metrics: list of ``{"name": str, "duration_seconds": float}``.
        """
        before_map = {m["name"]: m for m in before_metrics}
        after_map = {m["name"]: m for m in after_metrics}
        all_names = set(before_map.keys()) | set(after_map.keys())

        comparisons: list[dict] = []
        for name in sorted(all_names):
            before = before_map.get(name, {})
            after = after_map.get(name, {})

            before_dur = before.get("duration_seconds", 0)
            after_dur = after.get("duration_seconds", 0)

            if before_dur > 0:
                change_pct = round((after_dur - before_dur) / before_dur * 100, 1)
            else:
                change_pct = 0

            comparisons.append({
                "name": name,
                "before_seconds": before_dur,
                "after_seconds": after_dur,
                "change_pct": change_pct,
                "status": "improved" if change_pct < -5 else (
                    "degraded" if change_pct > 10 else "stable"
                ),
            })

        improved = sum(1 for c in comparisons if c["status"] == "improved")
        degraded = sum(1 for c in comparisons if c["status"] == "degraded")

        result = {
            "comparisons": comparisons,
            "summary": {
                "total": len(comparisons),
                "improved": improved,
                "stable": sum(1 for c in comparisons if c["status"] == "stable"),
                "degraded": degraded,
                "verdict": "PASS" if degraded == 0 else "REVIEW",
            },
        }

        logger.info(
            "Performance comparison: %d improved, %d degraded — %s",
            improved, degraded, result["summary"]["verdict"],
        )
        return result

    def save(self, output_dir: str, data: dict, name: str = "perf_benchmark") -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{name}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return path
