"""
Cache Plan Migrator — converts PBIRS CacheRefreshPlans into PBI dataset refresh schedules.

PBIRS reports/datasets can have CacheRefreshPlan entries that pre-render cached
snapshots on a schedule. The PBI Online equivalent is a scheduled dataset
refresh. This module translates the PBIRS cadence (Daily/Weekly/Monthly +
StartTime + TimeZone) into the PBI ``refreshSchedule`` REST payload shape so
``refresh_scheduler.RefreshScheduler`` can apply it.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

DAYS_FULL = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


class CachePlanMigrator:
    """Translate PBIRS cache plans into PBI refresh-schedule payloads."""

    def __init__(self, default_timezone: str = "UTC"):
        self.default_timezone = default_timezone

    def migrate(self, cache_plan: dict) -> dict | None:
        """Convert a single PBIRS CacheRefreshPlan entry.

        Returns a PBI-shaped ``refreshSchedule`` payload, or None if the plan
        is disabled / cannot be translated.
        """
        if not cache_plan:
            return None
        if cache_plan.get("Enabled") is False or cache_plan.get("enabled") is False:
            return None

        schedule = cache_plan.get("Schedule") or cache_plan.get("schedule") or {}
        recurrence = (
            schedule.get("Definition")
            or schedule.get("definition")
            or schedule
        )
        tz = cache_plan.get("TimeZone") or recurrence.get("TimeZone") or self.default_timezone

        days = self._extract_days(recurrence)
        times = self._extract_times(recurrence)
        if not days or not times:
            logger.warning("Cache plan %s missing days/times", cache_plan.get("Name", "?"))
            return None

        return {
            "value": {
                "enabled": True,
                "days": days,
                "times": times,
                "localTimeZoneId": tz,
                "notifyOption": "MailOnFailure",
            }
        }

    def migrate_all(self, cache_plans: list[dict]) -> dict:
        """Translate every plan in *cache_plans*."""
        translated = []
        skipped = 0
        for plan in cache_plans:
            payload = self.migrate(plan)
            if payload is None:
                skipped += 1
                continue
            translated.append({
                "source": plan.get("Name") or plan.get("name") or "",
                "item_id": plan.get("ItemId") or plan.get("itemId") or "",
                "schedule": payload,
            })
        logger.info(
            "Cache-plan migration: %d translated, %d skipped",
            len(translated), skipped,
        )
        return {"translated": translated, "skipped": skipped}

    # ------------------------------------------------------------------
    # Recurrence helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_days(recurrence: dict) -> list[str]:
        if "DaysOfWeek" in recurrence or "daysOfWeek" in recurrence:
            raw = recurrence.get("DaysOfWeek") or recurrence.get("daysOfWeek")
            if isinstance(raw, list):
                return [_full_day(d) for d in raw if _full_day(d)]
        if recurrence.get("Daily") or recurrence.get("daily"):
            return list(DAYS_FULL)
        if recurrence.get("Weekly") or recurrence.get("weekly"):
            weekly = recurrence.get("Weekly") or recurrence.get("weekly")
            raw_days = weekly.get("DaysOfWeek") if isinstance(weekly, dict) else None
            if raw_days:
                return [_full_day(d) for d in raw_days if _full_day(d)]
        if recurrence.get("Monthly") or recurrence.get("monthly"):
            return ["Monday"]
        return []

    @staticmethod
    def _extract_times(recurrence: dict) -> list[str]:
        start = (
            recurrence.get("StartDateTime")
            or recurrence.get("startDateTime")
            or recurrence.get("StartTime")
            or recurrence.get("startTime")
            or ""
        )
        if "T" in start:
            time = start.split("T", 1)[1][:5]
            return [time]
        if start and ":" in start:
            return [start[:5]]
        return ["02:00"]


def _full_day(name: str) -> str | None:
    if not name:
        return None
    n = str(name).strip().lower()
    for full in DAYS_FULL:
        if full.lower() == n or full.lower().startswith(n):
            return full
    return None
