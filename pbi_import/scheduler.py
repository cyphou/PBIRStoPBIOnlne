"""
Scheduler — cron-like recurring migration runs.

Provides a lightweight, stdlib-only scheduler that can run migration phases
on a schedule. Uses threading.Timer for recurring execution.
"""

import json
import logging
import time
import threading
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class Scheduler:
    """Lightweight migration task scheduler."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._timers: dict[str, threading.Timer] = {}
        self._running = False
        self._lock = threading.Lock()

    def add_job(
        self,
        name: str,
        func: Callable[..., Any],
        interval_seconds: int,
        args: tuple = (),
        kwargs: dict | None = None,
    ) -> None:
        """Register a recurring job.

        Args:
            name: unique job name.
            func: callable to execute.
            interval_seconds: seconds between executions.
            args: positional arguments for func.
            kwargs: keyword arguments for func.
        """
        with self._lock:
            self._jobs[name] = {
                "name": name,
                "func": func,
                "interval": interval_seconds,
                "args": args,
                "kwargs": kwargs or {},
                "last_run": None,
                "run_count": 0,
                "status": "registered",
            }
        logger.info("Job registered: %s (every %ds)", name, interval_seconds)

    def remove_job(self, name: str) -> None:
        """Remove a job by name."""
        with self._lock:
            timer = self._timers.pop(name, None)
            if timer:
                timer.cancel()
            self._jobs.pop(name, None)
        logger.info("Job removed: %s", name)

    def start(self) -> None:
        """Start all registered jobs."""
        self._running = True
        with self._lock:
            for name, job in self._jobs.items():
                self._schedule_next(name, job)
                job["status"] = "running"
        logger.info("Scheduler started with %d jobs", len(self._jobs))

    def stop(self) -> None:
        """Stop all jobs."""
        self._running = False
        with self._lock:
            for name, timer in self._timers.items():
                timer.cancel()
            self._timers.clear()
            for job in self._jobs.values():
                job["status"] = "stopped"
        logger.info("Scheduler stopped")

    def run_once(self, name: str) -> dict:
        """Run a specific job once immediately."""
        job = self._jobs.get(name)
        if not job:
            return {"error": f"Job not found: {name}"}

        return self._execute_job(name, job)

    def status(self) -> dict:
        """Get scheduler status."""
        with self._lock:
            return {
                "running": self._running,
                "jobs": {
                    name: {
                        "interval": job["interval"],
                        "last_run": job["last_run"],
                        "run_count": job["run_count"],
                        "status": job["status"],
                    }
                    for name, job in self._jobs.items()
                },
            }

    def save_status(self, output_dir: str) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "scheduler_status.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.status(), f, indent=2, default=str)
        return path

    def _schedule_next(self, name: str, job: dict) -> None:
        """Schedule the next execution of a job."""
        if not self._running:
            return

        def _run() -> None:
            self._execute_job(name, job)
            if self._running and name in self._jobs:
                self._schedule_next(name, job)

        timer = threading.Timer(job["interval"], _run)
        timer.daemon = True
        timer.name = f"scheduler-{name}"
        self._timers[name] = timer
        timer.start()

    def _execute_job(self, name: str, job: dict) -> dict:
        """Execute a job and record the result."""
        start = time.time()
        try:
            result = job["func"](*job["args"], **job["kwargs"])
            duration = time.time() - start
            job["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            job["run_count"] += 1
            logger.info("Job %s completed in %.1fs", name, duration)
            return {
                "job": name,
                "status": "completed",
                "duration_seconds": round(duration, 2),
                "result": str(result) if result else None,
            }
        except Exception as e:
            duration = time.time() - start
            logger.error("Job %s failed after %.1fs: %s", name, duration, e)
            return {
                "job": name,
                "status": "failed",
                "duration_seconds": round(duration, 2),
                "error": str(e),
            }
