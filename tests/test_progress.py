"""Tests for ProgressReporter."""

import io
import threading

from pbirs_export.progress import ProgressReporter


class TestProgressReporter:

    def test_basic_progress(self):
        stream = io.StringIO()
        p = ProgressReporter(total=5, label="Test", stream=stream)
        p.start()
        for _ in range(5):
            p.advance()
        p.finish()
        output = stream.getvalue()
        assert "5/5" in output
        assert "100%" in output

    def test_context_manager(self):
        stream = io.StringIO()
        with ProgressReporter(total=3, label="CM", stream=stream) as p:
            for _ in range(3):
                p.advance()
        output = stream.getvalue()
        assert "3/3" in output

    def test_zero_total_no_crash(self):
        stream = io.StringIO()
        p = ProgressReporter(total=0, label="Empty", stream=stream)
        p.start()
        p.finish()
        # Should not crash, total clamped to 1
        assert p.total == 1

    def test_thread_safety(self):
        stream = io.StringIO()
        p = ProgressReporter(total=100, label="Threaded", stream=stream)
        p.start()

        def worker():
            for _ in range(25):
                p.advance()

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        p.finish()
        assert p.current == 100

    def test_advance_past_total(self):
        stream = io.StringIO()
        p = ProgressReporter(total=3, stream=stream)
        p.start()
        for _ in range(10):
            p.advance()
        assert p.current == 3  # clamped

    def test_format_time(self):
        assert ProgressReporter._format_time(65) == "1:05"
        assert ProgressReporter._format_time(3661) == "1:01:01"
        assert ProgressReporter._format_time(0) == "0:00"
