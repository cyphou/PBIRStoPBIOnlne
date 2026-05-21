"""
Metrics Exporter — exports migration metrics in Prometheus text format.

Generates Prometheus-compatible metrics for monitoring migration progress,
success rates, and performance via any Prometheus-compatible scraper.
"""

import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class MetricsExporter:
    """Export migration metrics in Prometheus exposition format."""

    def __init__(self) -> None:
        self._metrics: dict[str, dict] = {}

    def gauge(self, name: str, value: float, help_text: str = "", labels: dict[str, str] | None = None) -> None:
        """Set a gauge metric."""
        self._metrics[self._key(name, labels)] = {
            "name": name,
            "type": "gauge",
            "value": value,
            "help": help_text,
            "labels": labels or {},
        }

    def counter(self, name: str, value: float, help_text: str = "", labels: dict[str, str] | None = None) -> None:
        """Set a counter metric."""
        key = self._key(name, labels)
        existing = self._metrics.get(key)
        if existing and existing["type"] == "counter":
            existing["value"] += value
        else:
            self._metrics[key] = {
                "name": name,
                "type": "counter",
                "value": value,
                "help": help_text,
                "labels": labels or {},
            }

    def histogram_observe(self, name: str, value: float, help_text: str = "") -> None:
        """Record a histogram observation (simplified — stores as gauge of last value)."""
        self._metrics[name] = {
            "name": name,
            "type": "gauge",
            "value": value,
            "help": help_text,
            "labels": {},
        }

    def from_migration_results(self, results: dict) -> None:
        """Populate metrics from migration result data."""
        summary = results.get("summary", {})

        self.gauge("migration_items_total", summary.get("total_items", 0),
                   "Total items in migration")
        self.gauge("migration_items_completed", summary.get("completed", 0),
                   "Items successfully migrated")
        self.gauge("migration_items_failed", summary.get("failed", 0),
                   "Items that failed migration")
        self.gauge("migration_items_skipped", summary.get("skipped", 0),
                   "Items skipped")

        # Per-type metrics
        for item_type, count in summary.get("by_type", {}).items():
            self.gauge(
                "migration_items_by_type",
                count,
                "Items by content type",
                labels={"type": item_type},
            )

        # Duration
        duration = summary.get("duration_seconds", 0)
        if duration:
            self.gauge("migration_duration_seconds", duration,
                       "Total migration duration in seconds")

        # Timestamp
        self.gauge("migration_last_run_timestamp", time.time(),
                   "Timestamp of last migration run")

    def render(self) -> str:
        """Render metrics in Prometheus text exposition format."""
        lines: list[str] = []
        rendered_help: set[str] = set()

        for metric in sorted(self._metrics.values(), key=lambda m: m["name"]):
            name = metric["name"]

            # Help and type (only once per metric name)
            if name not in rendered_help:
                if metric["help"]:
                    lines.append(f"# HELP {name} {metric['help']}")
                lines.append(f"# TYPE {name} {metric['type']}")
                rendered_help.add(name)

            # Labels
            labels = metric.get("labels", {})
            if labels:
                label_str = ",".join(
                    f'{k}="{v}"' for k, v in sorted(labels.items())
                )
                lines.append(f"{name}{{{label_str}}} {metric['value']}")
            else:
                lines.append(f"{name} {metric['value']}")

        return "\n".join(lines) + "\n"

    def save(self, output_dir: str) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "metrics.prom"
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.render())
        logger.info("Metrics exported to %s", path)
        return path

    @staticmethod
    def _key(name: str, labels: dict[str, str] | None) -> str:
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
