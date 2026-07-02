"""Optional ReportServer DB bridge for data-driven subscription query extraction.

This module is opt-in and has no hard dependency on database drivers. It can
use ``pyodbc`` if available, or an injected fetcher in tests.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class ReportServerDbBridge:
    """Extract data-driven query text from ReportServer DB and merge into payload."""

    def __init__(
        self,
        connection_string: str,
        query_fetcher: Callable[[list[str]], dict[str, str]] | None = None,
        logger_: logging.Logger | None = None,
    ) -> None:
        self.connection_string = connection_string
        self.query_fetcher = query_fetcher
        self.logger = logger_ or logger

    def merge_into_subscriptions(self, subscriptions_payload: dict[str, Any]) -> dict[str, Any]:
        """Merge DB-extracted query metadata into data-driven subscriptions."""
        subs = subscriptions_payload.get("subscriptions", [])
        data_driven = [s for s in subs if s.get("IsDataDriven")]
        ids = [str(s.get("SubscriptionID", "")) for s in data_driven if s.get("SubscriptionID")]

        query_map: dict[str, str] = {}
        errors: list[str] = []
        if ids:
            try:
                query_map = self._fetch_query_map(ids)
            except Exception as e:  # noqa: BLE001
                errors.append(str(e))
                self.logger.warning(
                    "DB query bridge disabled for this run: %s (conn=%s)",
                    e,
                    self.redact_connection_string(self.connection_string),
                )

        merged = 0
        report_entries: list[dict[str, str]] = []
        for sub in data_driven:
            sub_id = str(sub.get("SubscriptionID", ""))
            query_text = query_map.get(sub_id, "")
            if query_text:
                sub["DbQueryMetadata"] = {
                    "query_text": query_text,
                    "query_text_redacted": self.redact_text(query_text),
                    "query_source": "reportserver_db",
                }
                merged += 1
            report_entries.append(
                {
                    "subscription_id": sub_id,
                    "merged": "true" if bool(query_text) else "false",
                    "query_preview": self.redact_text(query_text)[:160] if query_text else "",
                }
            )

        report = {
            "enabled": True,
            "connection": self.redact_connection_string(self.connection_string),
            "data_driven_total": len(data_driven),
            "merged_count": merged,
            "missing_count": max(0, len(data_driven) - merged),
            "errors": errors,
            "subscriptions": report_entries,
        }
        return {"subscriptions": subscriptions_payload, "report": report}

    def _fetch_query_map(self, subscription_ids: list[str]) -> dict[str, str]:
        if self.query_fetcher is not None:
            return self.query_fetcher(subscription_ids)

        try:
            import pyodbc  # type: ignore
        except ImportError as e:  # pragma: no cover - environment dependent
            raise RuntimeError("pyodbc is required for DB query bridge") from e

        placeholders = ",".join("?" for _ in subscription_ids)
        sql = (
            "SELECT CAST(SubscriptionID as nvarchar(128)) AS SubscriptionID, "
            "CAST(DataSettings as nvarchar(max)) AS DataSettings "
            "FROM Subscriptions "
            f"WHERE CAST(SubscriptionID as nvarchar(128)) IN ({placeholders})"
        )

        query_map: dict[str, str] = {}
        conn = pyodbc.connect(self.connection_string)
        try:
            cur = conn.cursor()
            rows = cur.execute(sql, subscription_ids).fetchall()
            for row in rows:
                sub_id = str(getattr(row, "SubscriptionID", "") or row[0] or "")
                ds = str(getattr(row, "DataSettings", "") or row[1] or "")
                query = self._extract_query_from_data_settings(ds)
                if sub_id and query:
                    query_map[sub_id] = query
        finally:
            conn.close()

        return query_map

    @staticmethod
    def _extract_query_from_data_settings(data_settings: str) -> str:
        if not data_settings:
            return ""
        try:
            root = ET.fromstring(data_settings)
        except ET.ParseError:
            return ""

        for elem in root.iter():
            tag = elem.tag.rsplit("}", 1)[-1].lower()
            if tag in {"commandtext", "query", "querytext"} and elem.text:
                return elem.text.strip()
        return ""

    @staticmethod
    def redact_connection_string(connection_string: str) -> str:
        if not connection_string:
            return ""
        redacted = re.sub(r"(?i)(password|pwd)\s*=\s*[^;]+", r"\1=***", connection_string)
        redacted = re.sub(r"(?i)(user id|uid)\s*=\s*[^;]+", r"\1=***", redacted)
        return redacted

    @staticmethod
    def redact_text(text: str) -> str:
        if not text:
            return ""
        out = re.sub(r"(?i)(password|pwd|token|apikey|api_key)\s*[:=]\s*['\"]?[^'\"\s;]+", r"\1=***", text)
        out = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "***@***", out)
        return out
