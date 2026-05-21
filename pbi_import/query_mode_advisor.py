"""
Query Mode Advisor — recommends DirectQuery → Import mode conversion.

Analyses datasource types, report complexity, and refresh patterns to
advise whether a report should stay DirectQuery or convert to Import mode,
with estimated capacity/RU cost implications.
"""

import logging

logger = logging.getLogger(__name__)

# Typical Import mode sizes per row (rough estimates in KB)
_AVG_ROW_SIZE_KB = 0.5
# PBI Pro dataset limit (1 GB), Premium (large model up to 400 GB)
_PRO_LIMIT_GB = 1.0
_PREMIUM_LIMIT_GB = 100.0


class QueryModeAdvisor:
    """Advise on DirectQuery vs Import mode for migrated datasets."""

    def analyse(self, catalog: list[dict]) -> list[dict]:
        """Analyse each item and recommend query mode.

        Returns per-item recommendations with rationale.
        """
        results: list[dict] = []

        for item in catalog:
            recommendation = self._recommend(item)
            results.append(recommendation)

        import_count = sum(1 for r in results if r["recommendation"] == "Import")
        dq_count = sum(1 for r in results if r["recommendation"] == "DirectQuery")
        logger.info(
            "Query mode advice: %d Import, %d DirectQuery, %d total",
            import_count, dq_count, len(results),
        )
        return results

    def summary(self, results: list[dict]) -> dict:
        by_mode: dict[str, int] = {}
        for r in results:
            mode = r["recommendation"]
            by_mode[mode] = by_mode.get(mode, 0) + 1

        return {
            "total": len(results),
            "by_mode": by_mode,
            "estimated_total_size_gb": round(
                sum(r.get("estimated_size_gb", 0) for r in results), 2
            ),
        }

    def _recommend(self, item: dict) -> dict:
        """Generate recommendation for a single item."""
        name = item.get("Name", "")
        item_type = item.get("Type", "")
        ds_list = item.get("DataSources", [])

        # Check for real-time indicators
        is_realtime = any(
            "streaming" in ds.get("ConnectionString", "").lower()
            or "directquery" in ds.get("DataSourceType", "").lower()
            for ds in ds_list
        )

        # Estimate data size from metadata
        row_count = item.get("estimated_rows", 0)
        estimated_gb = (row_count * _AVG_ROW_SIZE_KB) / (1024 * 1024) if row_count else 0

        # Check datasource type
        cloud_sources = {"AzureSqlDatabase", "AzureSynapse", "Fabric", "Dataverse"}
        is_cloud = any(
            ds.get("DataSourceType", "") in cloud_sources for ds in ds_list
        )

        # Decision logic
        reasons: list[str] = []
        if is_realtime:
            recommendation = "DirectQuery"
            reasons.append("Real-time/streaming data detected")
        elif estimated_gb > _PRO_LIMIT_GB:
            recommendation = "DirectQuery"
            reasons.append(f"Estimated size ({estimated_gb:.1f} GB) exceeds Pro limit")
        elif item_type in ("PowerBIReport",) and not is_realtime:
            recommendation = "Import"
            reasons.append("Standard report — Import mode gives best performance")
        elif is_cloud:
            recommendation = "DirectQuery"
            reasons.append("Cloud datasource — DirectQuery avoids data duplication")
        else:
            recommendation = "Import"
            reasons.append("Default — Import mode recommended for best query performance")

        return {
            "name": name,
            "type": item_type,
            "recommendation": recommendation,
            "reasons": reasons,
            "estimated_size_gb": round(estimated_gb, 3),
            "is_cloud_source": is_cloud,
            "is_realtime": is_realtime,
        }
