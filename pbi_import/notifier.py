"""
Notifier — Slack / Teams webhook notifications for migration events.

Sends formatted webhook payloads for migration milestones, failures, and
completion events. Stdlib-only (uses urllib.request).
"""

import json
import logging
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class Notifier:
    """Send migration notifications via webhooks (Teams/Slack)."""

    def __init__(
        self,
        teams_webhook: str | None = None,
        slack_webhook: str | None = None,
    ):
        self.teams_webhook = teams_webhook
        self.slack_webhook = slack_webhook
        self._history: list[dict] = []

    def notify(
        self,
        title: str,
        message: str,
        level: str = "info",
        details: dict | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Send a notification to configured channels.

        Args:
            title: notification title.
            message: notification body text.
            level: info, warning, error, success.
            details: optional key-value details to include.
            dry_run: log instead of sending.
        """
        results: dict[str, str] = {}

        if self.teams_webhook:
            payload = self._teams_payload(title, message, level, details)
            result = self._send(self.teams_webhook, payload, "Teams", dry_run)
            results["teams"] = result

        if self.slack_webhook:
            payload = self._slack_payload(title, message, level, details)
            result = self._send(self.slack_webhook, payload, "Slack", dry_run)
            results["slack"] = result

        if not self.teams_webhook and not self.slack_webhook:
            results["status"] = "no_webhooks_configured"

        notification = {
            "title": title,
            "message": message,
            "level": level,
            "results": results,
        }
        self._history.append(notification)
        return notification

    def notify_phase_complete(
        self,
        phase: str,
        items_processed: int,
        items_failed: int,
        duration_seconds: float,
        dry_run: bool = False,
    ) -> dict:
        """Send a phase completion notification."""
        level = "success" if items_failed == 0 else "warning"
        return self.notify(
            title=f"Migration Phase Complete: {phase}",
            message=f"Processed {items_processed} items ({items_failed} failed) "
                    f"in {duration_seconds:.0f}s",
            level=level,
            details={
                "phase": phase,
                "items_processed": str(items_processed),
                "items_failed": str(items_failed),
                "duration": f"{duration_seconds:.0f}s",
            },
            dry_run=dry_run,
        )

    def notify_error(self, error: str, context: str = "", dry_run: bool = False) -> dict:
        """Send an error notification."""
        return self.notify(
            title="Migration Error",
            message=error,
            level="error",
            details={"context": context} if context else None,
            dry_run=dry_run,
        )

    def save_history(self, output_dir: str) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "notification_history.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._history, f, indent=2)
        return path

    def _send(self, url: str, payload: dict, channel: str, dry_run: bool) -> str:
        if dry_run:
            logger.info("[DRY RUN] Would send to %s: %s", channel, payload.get("title", ""))
            return "dry_run"

        try:
            data = json.dumps(payload).encode("utf-8")
            req = Request(url, data=data, headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=10) as resp:  # noqa: S310 — webhook URL is user-configured
                status = resp.status
                logger.info("Sent notification to %s (HTTP %d)", channel, status)
                return "sent"
        except URLError as e:
            logger.error("Failed to send to %s: %s", channel, e)
            return f"failed: {e}"

    @staticmethod
    def _teams_payload(title: str, message: str, level: str, details: dict | None) -> dict:
        """Build Microsoft Teams Adaptive Card payload."""
        color = {
            "info": "0078D4",
            "success": "00A36C",
            "warning": "FFA500",
            "error": "FF0000",
        }.get(level, "0078D4")

        facts = []
        if details:
            facts = [{"title": k, "value": v} for k, v in details.items()]

        return {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": color,
            "summary": title,
            "sections": [{
                "activityTitle": title,
                "facts": facts,
                "text": message,
            }],
        }

    @staticmethod
    def _slack_payload(title: str, message: str, level: str, details: dict | None) -> dict:
        """Build Slack Block Kit payload."""
        emoji = {
            "info": ":information_source:",
            "success": ":white_check_mark:",
            "warning": ":warning:",
            "error": ":x:",
        }.get(level, ":information_source:")

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{emoji} {title}"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": message},
            },
        ]

        if details:
            fields = [
                {"type": "mrkdwn", "text": f"*{k}:* {v}"}
                for k, v in details.items()
            ]
            blocks.append({"type": "section", "fields": fields})

        return {"blocks": blocks}
