"""
Cost Estimator — projects Fabric/PBI capacity costs for the migrated workload.

Calculates estimated monthly costs based on content volume, refresh schedules,
user counts, and capacity SKU pricing.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# PBI pricing tiers (monthly USD, approximate)
_PBI_PRICING = {
    "pro": {"per_user_monthly": 10.0, "max_dataset_gb": 1.0},
    "ppu": {"per_user_monthly": 20.0, "max_dataset_gb": 100.0},
}

# Fabric capacity pricing (monthly USD, approximate)
_FABRIC_PRICING: dict[str, float] = {
    "F2": 262,
    "F4": 525,
    "F8": 1050,
    "F16": 2100,
    "F32": 4200,
    "F64": 8400,
    "F128": 16800,
    "F256": 33600,
    "F512": 67200,
}


class CostEstimator:
    """Estimate capacity and licensing costs for migrated workloads."""

    def estimate(
        self,
        catalog: list[dict],
        user_count: int = 10,
        refresh_per_day: int = 8,
        fabric_sku: str | None = None,
    ) -> dict:
        """Estimate monthly costs.

        Args:
            catalog: content items to migrate.
            user_count: expected number of report consumers.
            refresh_per_day: average dataset refreshes per day.
            fabric_sku: specific Fabric SKU (or None for auto-select).
        """
        # Count content types
        pbi_reports = sum(1 for i in catalog if i.get("Type") == "PowerBIReport")
        paginated = sum(1 for i in catalog if i.get("Type") == "Report")
        datasets = sum(1 for i in catalog if i.get("Type") in ("PowerBIReport", "DataSet"))
        total_size_gb = sum(
            i.get("Size", 0) / (1024 ** 3) for i in catalog
        )

        # Determine licensing need
        needs_premium = paginated > 0 or total_size_gb > 1.0 or datasets > 10

        # PBI Pro/PPU costs
        if needs_premium:
            license_type = "ppu"
            license_cost = user_count * _PBI_PRICING["ppu"]["per_user_monthly"]
        else:
            license_type = "pro"
            license_cost = user_count * _PBI_PRICING["pro"]["per_user_monthly"]

        # Fabric capacity cost
        if fabric_sku:
            fabric_cost = _FABRIC_PRICING.get(fabric_sku, 0)
        elif needs_premium:
            fabric_sku = self._recommend_sku(datasets, total_size_gb)
            fabric_cost = _FABRIC_PRICING.get(fabric_sku, 0)
        else:
            fabric_sku = None
            fabric_cost = 0

        # Gateway cost estimate (if on-prem sources)
        on_prem_sources = sum(
            1 for i in catalog
            if any(ds.get("DataSourceType", "") not in (
                "AzureSqlDatabase", "AzureSynapse", "Fabric",
            ) for ds in i.get("DataSources", []))
        )
        gateway_cost = 50.0 if on_prem_sources > 0 else 0  # VM cost estimate

        total_monthly = license_cost + fabric_cost + gateway_cost

        result = {
            "workload": {
                "pbi_reports": pbi_reports,
                "paginated_reports": paginated,
                "datasets": datasets,
                "total_size_gb": round(total_size_gb, 2),
                "users": user_count,
                "refreshes_per_day": refresh_per_day,
                "on_prem_sources": on_prem_sources,
            },
            "licensing": {
                "type": license_type,
                "per_user_cost": _PBI_PRICING[license_type]["per_user_monthly"],
                "users": user_count,
                "monthly_cost": round(license_cost, 2),
            },
            "capacity": {
                "sku": fabric_sku,
                "monthly_cost": round(fabric_cost, 2),
                "needs_premium": needs_premium,
            },
            "gateway": {
                "needed": on_prem_sources > 0,
                "monthly_cost": round(gateway_cost, 2),
            },
            "total_monthly_usd": round(total_monthly, 2),
            "total_annual_usd": round(total_monthly * 12, 2),
        }

        logger.info(
            "Cost estimate: $%.0f/month ($%.0f/year) — %s license, %s capacity",
            total_monthly, total_monthly * 12,
            license_type.upper(), fabric_sku or "none",
        )
        return result

    def save(self, output_dir: str, result: dict) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "cost_estimate.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        return path

    @staticmethod
    def _recommend_sku(datasets: int, size_gb: float) -> str:
        """Recommend a Fabric SKU based on workload."""
        if datasets <= 10 and size_gb <= 3:
            return "F2"
        elif datasets <= 25 and size_gb <= 5:
            return "F16"
        elif datasets <= 50 and size_gb <= 10:
            return "F32"
        elif datasets <= 200 and size_gb <= 25:
            return "F64"
        elif datasets <= 500 and size_gb <= 50:
            return "F128"
        else:
            return "F256"
