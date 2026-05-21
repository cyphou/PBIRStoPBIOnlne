"""Tests for CheckpointManager."""

import json
import pytest
from pbirs_export.checkpoint import CheckpointManager


class TestCheckpointManager:

    def test_fresh_start(self, tmp_path):
        cm = CheckpointManager(str(tmp_path))
        assert cm.completed_count == 0
        assert cm.failed_count == 0

    def test_mark_done(self, tmp_path):
        cm = CheckpointManager(str(tmp_path))
        cm.mark_done("item-1", {"name": "Report A"})
        assert cm.is_done("item-1")
        assert cm.completed_count == 1

    def test_mark_failed(self, tmp_path):
        cm = CheckpointManager(str(tmp_path))
        cm.mark_failed("item-2", "network error")
        assert not cm.is_done("item-2")
        assert cm.failed_count == 1

    def test_resume_from_checkpoint(self, tmp_path):
        cm1 = CheckpointManager(str(tmp_path))
        cm1.mark_done("item-1")
        cm1.mark_done("item-2")

        # Simulate restart
        cm2 = CheckpointManager(str(tmp_path))
        assert cm2.is_done("item-1")
        assert cm2.is_done("item-2")
        assert cm2.completed_count == 2

    def test_reset(self, tmp_path):
        cm = CheckpointManager(str(tmp_path))
        cm.mark_done("item-1")
        cm.reset()
        assert cm.completed_count == 0
        assert not cm.is_done("item-1")

    def test_failed_then_done(self, tmp_path):
        cm = CheckpointManager(str(tmp_path))
        cm.mark_failed("item-1", "error")
        assert cm.failed_count == 1
        cm.mark_done("item-1")
        assert cm.is_done("item-1")

    def test_summary(self, tmp_path):
        cm = CheckpointManager(str(tmp_path))
        cm.mark_done("a")
        cm.mark_failed("b", "err")
        s = cm.summary()
        assert s["completed"] == 1
        assert s["failed"] == 1

    def test_completed_ids(self, tmp_path):
        cm = CheckpointManager(str(tmp_path))
        cm.mark_done("x")
        cm.mark_done("y")
        assert cm.completed_ids == {"x", "y"}

    def test_corrupt_checkpoint(self, tmp_path):
        # Write invalid JSON
        (tmp_path / ".checkpoint.json").write_text("not json", encoding="utf-8")
        cm = CheckpointManager(str(tmp_path))
        assert cm.completed_count == 0  # falls back to fresh
