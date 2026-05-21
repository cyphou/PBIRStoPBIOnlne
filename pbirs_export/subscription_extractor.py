"""
Subscription Extractor — extracts email/file-share subscriptions from PBIRS.
"""

import logging
from typing import Any

from pbirs_export.api_client import PBIRSClient

logger = logging.getLogger(__name__)


class SubscriptionExtractor:
    """Extract subscription and schedule data from PBIRS."""

    def __init__(self, client: PBIRSClient):
        self.client = client

    def extract_all(self, catalog: dict) -> dict:
        """Extract all subscriptions and schedules."""
        subscriptions: dict[str, Any] = {
            "subscriptions": [],
            "schedules": [],
        }

        # All subscriptions
        try:
            subs = self.client.list_subscriptions()
            subscriptions["subscriptions"] = subs
            logger.info("Found %d subscriptions", len(subs))
        except Exception as e:
            logger.warning("Could not extract subscriptions: %s", e)

        # All schedules
        try:
            schedules = self.client.list_schedules()
            subscriptions["schedules"] = schedules
            logger.info("Found %d schedules", len(schedules))
        except Exception as e:
            logger.warning("Could not extract schedules: %s", e)

        return subscriptions
