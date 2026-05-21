"""
Batch Orchestrator — multi-server batch migration orchestration.

Coordinates extraction and migration across multiple PBIRS/SSRS servers
in parallel or sequential batches with progress tracking.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class BatchOrchestrator:
    """Orchestrate migration across multiple PBIRS/SSRS servers."""

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results: list[dict] = []

    def plan(self, servers: list[dict]) -> dict:
        """Create a batch migration plan.

        Args:
            servers: list of server configs with ``url``, ``name``, ``priority``.
        """
        plan: list[dict] = []

        for i, server in enumerate(servers):
            plan.append({
                "order": i + 1,
                "server_name": server.get("name", f"server_{i}"),
                "server_url": server.get("url", ""),
                "priority": server.get("priority", "normal"),
                "content_types": server.get("content_types", ["all"]),
                "target_workspace": server.get("target_workspace"),
                "status": "pending",
            })

        # Sort by priority
        priority_order = {"high": 0, "normal": 1, "low": 2}
        plan.sort(key=lambda s: priority_order.get(s["priority"], 1))

        result = {
            "batch_plan": plan,
            "total_servers": len(plan),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        logger.info("Batch plan created for %d servers", len(plan))
        return result

    def execute_sequential(
        self,
        plan: dict,
        extract_fn: Any,
        migrate_fn: Any,
        dry_run: bool = False,
    ) -> dict:
        """Execute batch plan sequentially.

        Args:
            plan: output from ``plan()``.
            extract_fn: ``(server_url, output_dir) -> extraction_result``.
            migrate_fn: ``(extraction_result, workspace_id) -> migration_result``.
            dry_run: preview only.
        """
        batch_results: list[dict] = []

        for entry in plan["batch_plan"]:
            server_name = entry["server_name"]
            server_url = entry["server_url"]
            workspace = entry.get("target_workspace")

            logger.info("Processing server: %s (%s)", server_name, server_url)
            start_time = time.time()

            try:
                if dry_run:
                    result = {
                        "server": server_name,
                        "status": "dry_run",
                        "items_found": 0,
                    }
                else:
                    # Extract
                    server_output = str(self.output_dir / server_name)
                    extraction = extract_fn(server_url, server_output)

                    # Migrate
                    migration = migrate_fn(extraction, workspace) if workspace else None

                    result = {
                        "server": server_name,
                        "status": "completed",
                        "extraction": extraction,
                        "migration": migration,
                    }

            except Exception as e:
                logger.error("Failed to process %s: %s", server_name, e)
                result = {
                    "server": server_name,
                    "status": "failed",
                    "error": str(e),
                }

            result["duration_seconds"] = round(time.time() - start_time, 2)
            batch_results.append(result)
            entry["status"] = result["status"]

        summary = {
            "batch_results": batch_results,
            "summary": {
                "total": len(batch_results),
                "completed": sum(1 for r in batch_results if r["status"] == "completed"),
                "failed": sum(1 for r in batch_results if r["status"] == "failed"),
                "dry_run": sum(1 for r in batch_results if r["status"] == "dry_run"),
            },
        }

        logger.info(
            "Batch complete: %d/%d succeeded",
            summary["summary"]["completed"],
            summary["summary"]["total"],
        )
        self.results = batch_results
        return summary

    def save(self, result: dict | None = None) -> Path:
        data = result or {"results": self.results}
        path = self.output_dir / "batch_results.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return path
