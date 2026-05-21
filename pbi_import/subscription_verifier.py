"""
Subscription Verifier — validates that PBIRS subscriptions can be migrated
and recreated as PBI Online subscriptions/alerts.

Checks subscription configurations, validates recipient email addresses,
and maps delivery methods.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# PBIRS delivery methods → PBI Online equivalents
_DELIVERY_MAP: dict[str, dict] = {
    "Email": {"pbi_method": "Email Subscription", "supported": True},
    "FileShare": {"pbi_method": "N/A", "supported": False, "note": "File share delivery not available in PBI Online"},
    "Null": {"pbi_method": "N/A", "supported": False, "note": "Cache refresh — handled by scheduled refresh"},
    "Report Server Document Library": {
        "pbi_method": "SharePoint",
        "supported": True,
        "note": "Map to SharePoint Online integration",
    },
}


class SubscriptionVerifier:
    """Verify and plan subscription migration."""

    def verify(self, subscriptions: list[dict]) -> dict:
        """Verify subscription migration feasibility.

        Args:
            subscriptions: list of PBIRS subscription metadata.
        """
        results: list[dict] = []

        for sub in subscriptions:
            sub_id = sub.get("SubscriptionID", sub.get("Id", ""))
            report = sub.get("Report", sub.get("Path", ""))
            delivery = sub.get("DeliverySettings", {})
            delivery_method = delivery.get("Extension", sub.get("DeliveryExtension", ""))
            schedule = sub.get("ScheduleDefinition", sub.get("Schedule", ""))

            # Map delivery method
            mapping = _DELIVERY_MAP.get(delivery_method, {
                "pbi_method": "Unknown",
                "supported": False,
                "note": f"Unknown delivery method: {delivery_method}",
            })

            # Validate recipients
            recipients = self._extract_recipients(delivery)

            result = {
                "subscription_id": sub_id,
                "report": report,
                "delivery_method": delivery_method,
                "pbi_method": mapping.get("pbi_method", ""),
                "supported": mapping.get("supported", False),
                "recipients": recipients,
                "schedule": str(schedule),
                "owner": sub.get("Owner", ""),
                "description": sub.get("Description", ""),
                "migration_notes": [],
            }

            if not mapping.get("supported"):
                result["migration_notes"].append(
                    mapping.get("note", "Delivery method not supported")
                )

            if not recipients:
                result["migration_notes"].append("No valid recipients found")

            results.append(result)

        supported = sum(1 for r in results if r["supported"])
        return {
            "results": results,
            "summary": {
                "total_subscriptions": len(results),
                "supported": supported,
                "unsupported": len(results) - supported,
                "migration_rate": round(supported / max(len(results), 1) * 100, 1),
                "by_delivery": self._count_by_delivery(results),
            },
        }

    def save(self, output_dir: str, result: dict) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "subscription_verification.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        return path

    @staticmethod
    def _extract_recipients(delivery: dict) -> list[str]:
        """Extract recipient email addresses from delivery settings."""
        recipients: list[str] = []

        # Check common fields
        for field in ("TO", "To", "to", "Recipients"):
            value = delivery.get(field, "")
            if isinstance(value, str) and value:
                recipients.extend(
                    addr.strip() for addr in value.split(";") if addr.strip()
                )
            elif isinstance(value, list):
                recipients.extend(value)

        # Check parameters
        params = delivery.get("ParameterValues", [])
        for param in params:
            if param.get("Name") in ("TO", "To"):
                value = param.get("Value", "")
                if value:
                    recipients.extend(
                        addr.strip() for addr in value.split(";") if addr.strip()
                    )

        return list(set(recipients))

    @staticmethod
    def _count_by_delivery(results: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in results:
            method = r.get("delivery_method", "unknown")
            counts[method] = counts.get(method, 0) + 1
        return counts
