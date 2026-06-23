"""
Sync Daemon — long-running poller that drives incremental PBIRS → PBI migration.

Builds on ``pbirs_export.delta_tracker.DeltaTracker`` to detect changes between
runs and replays just the new/modified items through the existing migration
pipeline. Designed to be invoked from ``migrate.py --sync-daemon`` and to exit
cleanly on SIGINT/SIGTERM or when ``max_iterations`` is reached.
"""

from __future__ import annotations

import logging
import signal
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class SyncIteration:
    """Per-iteration accounting for a sync run."""

    index: int
    started_at: float
    finished_at: float = 0.0
    new: int = 0
    modified: int = 0
    unchanged: int = 0
    deleted: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def elapsed(self) -> float:
        return self.finished_at - self.started_at if self.finished_at else 0.0

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "elapsed": round(self.elapsed, 3),
            "new": self.new,
            "modified": self.modified,
            "unchanged": self.unchanged,
            "deleted": self.deleted,
            "errors": self.errors,
        }


class SyncDaemon:
    """Polls PBIRS and replays delta through the migration pipeline."""

    def __init__(
        self,
        catalog_fetcher: Callable[[], list[dict]],
        delta_tracker: Any,
        replay: Callable[[list[dict]], dict],
        poll_interval: float = 300.0,
        max_iterations: int | None = None,
        on_iteration: Callable[[SyncIteration], None] | None = None,
    ):
        self.fetch = catalog_fetcher
        self.tracker = delta_tracker
        self.replay = replay
        self.poll_interval = max(1.0, float(poll_interval))
        self.max_iterations = max_iterations
        self.on_iteration = on_iteration
        self._stop = False
        self._iterations: list[SyncIteration] = []

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def install_signal_handlers(self) -> None:
        """Register SIGINT/SIGTERM to request graceful shutdown."""
        for sig_name in ("SIGINT", "SIGTERM"):
            sig = getattr(signal, sig_name, None)
            if sig is not None:
                try:
                    signal.signal(sig, lambda *_a: self.request_stop())
                except (ValueError, OSError):
                    # Not running in main thread → ignore.
                    pass

    def request_stop(self) -> None:
        logger.info("Sync daemon stop requested")
        self._stop = True

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> list[SyncIteration]:
        """Run the daemon loop until ``request_stop()`` or ``max_iterations``."""
        i = 0
        while not self._stop:
            if self.max_iterations is not None and i >= self.max_iterations:
                break
            i += 1
            iteration = SyncIteration(index=i, started_at=time.time())
            try:
                catalog = self.fetch()
                changes = self.tracker.detect_changes(catalog)
                iteration.new = len(changes.get("new", []))
                iteration.modified = len(changes.get("modified", []))
                iteration.unchanged = len(changes.get("unchanged", []))
                iteration.deleted = len(changes.get("deleted", []))
                if iteration.new or iteration.modified:
                    delta = changes["new"] + changes["modified"]
                    logger.info(
                        "Sync iter %d: replaying %d changed items", i, len(delta),
                    )
                    self.replay(delta)
                else:
                    logger.info("Sync iter %d: nothing to do", i)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Sync iteration %d failed", i)
                iteration.errors.append(str(exc))
            finally:
                iteration.finished_at = time.time()
                self._iterations.append(iteration)
                if self.on_iteration:
                    try:
                        self.on_iteration(iteration)
                    except Exception:  # noqa: BLE001
                        logger.exception("on_iteration hook raised")

            self._sleep(self.poll_interval)
        return self._iterations

    # ------------------------------------------------------------------

    def _sleep(self, total: float) -> None:
        """Sleep in small chunks so stop requests are honoured promptly."""
        chunk = 0.5
        elapsed = 0.0
        while elapsed < total and not self._stop:
            time.sleep(min(chunk, total - elapsed))
            elapsed += chunk
