"""
Fabric Scaler — capacity assessment and SKU recommendations for Fabric.

Analyses migration workload to recommend the right Fabric capacity SKU
and estimates costs based on content volume, query patterns, and refresh needs.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Fabric capacity tiers with CU (Capacity Units) and approximate costs
_FABRIC_SKUS: list[dict] = [
    {"sku": "F2", "cu": 2, "max_memory_gb": 3, "max_datasets": 10, "monthly_usd": 262},
    {"sku": "F4", "cu": 4, "max_memory_gb": 3, "max_datasets": 10, "monthly_usd": 525},
    {"sku": "F8", "cu": 8, "max_memory_gb": 3, "max_datasets": 10, "monthly_usd": 1050},
    {"sku": "F16", "cu": 16, "max_memory_gb": 5, "max_datasets": 25, "monthly_usd": 2100},
    {"sku": "F32", "cu": 32, "max_memory_gb": 10, "max_datasets": 50, "monthly_usd": 4200},
    {"sku": "F64", "cu": 64, "max_memory_gb": 25, "max_datasets": 200, "monthly_usd": 8400},
    {"sku": "F128", "cu": 128, "max_memory_gb": 50, "max_datasets": 500, "monthly_usd": 16800},
    {"sku": "F256", "cu": 256, "max_memory_gb": 100, "max_datasets": 1000, "monthly_usd": 33600},
    {"sku": "F512", "cu": 512, "max_memory_gb": 200, "max_datasets": 2000, "monthly_usd": 67200},
]


class FabricScaler:
    """Recommend Fabric capacity SKUs based on migration workload."""

    def assess(self, catalog: list[dict]) -> dict:
        """Assess workload and recommend a Fabric SKU.

        Args:
            catalog: list of content items with metadata.
        """
        # Count content types
        report_count = 0
        dataset_count = 0
        paginated_count = 0
        total_size_mb = 0

        for item in catalog:
            item_type = item.get("Type", "")
            size = item.get("Size", 0) / (1024 * 1024) if item.get("Size") else 0
            total_size_mb += size

            if item_type == "PowerBIReport":
                report_count += 1
                dataset_count += 1  # Each report has an embedded dataset
            elif item_type == "Report":
                paginated_count += 1
            elif item_type == "DataSet":
                dataset_count += 1

        total_size_gb = total_size_mb / 1024

        # Estimate memory need (datasets loaded + query overhead)
        estimated_memory_gb = total_size_gb * 2.5  # 2.5x for in-memory + overhead

        # Find suitable SKU
        recommended = None
        for sku in _FABRIC_SKUS:
            if (
                sku["max_memory_gb"] >= estimated_memory_gb
                and sku["max_datasets"] >= dataset_count
            ):
                recommended = sku
                break

        if not recommended:
            recommended = _FABRIC_SKUS[-1]  # Largest available

        # Also recommend minimum viable SKU and growth SKU
        min_sku = recommended
        growth_sku = None
        for sku in _FABRIC_SKUS:
            if sku["cu"] > recommended["cu"]:
                growth_sku = sku
                break

        result = {
            "workload": {
                "reports": report_count,
                "datasets": dataset_count,
                "paginated_reports": paginated_count,
                "total_size_gb": round(total_size_gb, 2),
                "estimated_memory_gb": round(estimated_memory_gb, 2),
            },
            "recommended_sku": recommended,
            "growth_sku": growth_sku,
            "notes": self._generate_notes(
                report_count, dataset_count, paginated_count, estimated_memory_gb,
            ),
        }

        logger.info(
            "Fabric capacity recommendation: %s (%.1f GB memory needed)",
            recommended["sku"], estimated_memory_gb,
        )
        return result

    def save(self, output_dir: str, result: dict) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "fabric_capacity_recommendation.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        return path

    @staticmethod
    def _generate_notes(
        reports: int,
        datasets: int,
        paginated: int,
        memory_gb: float,
    ) -> list[str]:
        notes: list[str] = []

        if paginated > 0:
            notes.append(
                f"Paginated reports ({paginated}) require Fabric capacity "
                "(F64 or above for best performance)"
            )

        if datasets > 50:
            notes.append(
                f"Large dataset count ({datasets}) — consider F32+ for concurrent queries"
            )

        if memory_gb > 25:
            notes.append(
                f"High memory estimate ({memory_gb:.1f} GB) — "
                "consider enabling large dataset format"
            )

        notes.append(
            "Start with the recommended SKU and scale up based on actual usage. "
            "Fabric supports autoscale."
        )

        return notes
