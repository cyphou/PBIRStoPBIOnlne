"""
Progress Reporter — lightweight console progress bar (stdlib only).
"""

import sys
import threading
import time


class ProgressReporter:
    """Thread-safe console progress bar for long-running operations.

    Usage::

        progress = ProgressReporter(total=100, label="Downloading")
        progress.start()
        for item in items:
            do_work(item)
            progress.advance()
        progress.finish()

    Or as a context manager::

        with ProgressReporter(total=100, label="Downloading") as p:
            for item in items:
                do_work(item)
                p.advance()
    """

    def __init__(
        self,
        total: int,
        label: str = "Progress",
        bar_width: int = 40,
        stream: object | None = None,
    ):
        self.total = max(total, 1)  # avoid division by zero
        self.label = label
        self.bar_width = bar_width
        self.stream = stream or sys.stderr
        self._current = 0
        self._lock = threading.Lock()
        self._start_time: float | None = None
        self._finished = False

    def start(self) -> None:
        """Start the progress tracker."""
        self._start_time = time.monotonic()
        self._render()

    def advance(self, n: int = 1) -> None:
        """Advance the progress counter by *n* items."""
        with self._lock:
            self._current = min(self._current + n, self.total)
        self._render()

    def finish(self) -> None:
        """Mark progress as complete and print final summary."""
        with self._lock:
            self._current = self.total
            self._finished = True
        self._render()
        self.stream.write("\n")
        self.stream.flush()

    @property
    def current(self) -> int:
        return self._current

    # Context manager support
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        if not self._finished:
            self.finish()

    def _render(self) -> None:
        """Render the progress bar to the stream."""
        pct = self._current / self.total
        filled = int(self.bar_width * pct)
        bar = "█" * filled + "░" * (self.bar_width - filled)

        elapsed = ""
        if self._start_time is not None:
            secs = time.monotonic() - self._start_time
            elapsed = f" [{self._format_time(secs)}]"

        line = f"\r{self.label}: |{bar}| {self._current}/{self.total} ({pct:.0%}){elapsed}"
        self.stream.write(line)
        self.stream.flush()

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds as mm:ss or hh:mm:ss."""
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"
