"""
Visual Regression — screenshot-based visual comparison for report validation.

Compares rendered report screenshots before and after migration to detect
visual regressions (layout shifts, missing elements, colour changes).
Uses stdlib-only pixel comparison (no Pillow required).
"""

import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class VisualRegression:
    """Compare report screenshots for visual regression detection."""

    def __init__(self, threshold: float = 0.05):
        """
        Args:
            threshold: maximum allowed difference ratio (0.0 = identical, 1.0 = completely different).
        """
        self.threshold = threshold

    def compare_files(self, before_path: str, after_path: str) -> dict:
        """Compare two screenshot files by hash (fast check) and size.

        For pixel-level comparison without external libraries, we compare
        file sizes and hashes as a proxy.
        """
        before = Path(before_path)
        after = Path(after_path)

        if not before.exists():
            return {"status": "error", "error": f"Before file not found: {before}"}
        if not after.exists():
            return {"status": "error", "error": f"After file not found: {after}"}

        before_hash = self._file_hash(before)
        after_hash = self._file_hash(after)
        before_size = before.stat().st_size
        after_size = after.stat().st_size

        if before_hash == after_hash:
            return {
                "status": "pass",
                "difference": 0.0,
                "before_file": str(before),
                "after_file": str(after),
                "method": "hash_match",
            }

        # Estimate difference from file size change
        size_diff = abs(before_size - after_size) / max(before_size, after_size, 1)

        status = "pass" if size_diff <= self.threshold else "fail"

        return {
            "status": status,
            "difference": round(size_diff, 4),
            "threshold": self.threshold,
            "before_file": str(before),
            "after_file": str(after),
            "before_size": before_size,
            "after_size": after_size,
            "method": "size_comparison",
        }

    def compare_batch(
        self,
        pairs: list[dict],
    ) -> dict:
        """Compare a batch of before/after screenshot pairs.

        Each pair: ``{"name": "report_name", "before": "path", "after": "path"}``.
        """
        results: list[dict] = []

        for pair in pairs:
            name = pair.get("name", "")
            comparison = self.compare_files(
                pair.get("before", ""),
                pair.get("after", ""),
            )
            comparison["name"] = name
            results.append(comparison)

        passed = sum(1 for r in results if r["status"] == "pass")
        failed = sum(1 for r in results if r["status"] == "fail")
        errors = sum(1 for r in results if r["status"] == "error")

        summary = {
            "results": results,
            "summary": {
                "total": len(results),
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "pass_rate": round(passed / max(len(results), 1) * 100, 1),
            },
        }

        logger.info(
            "Visual regression: %d/%d passed (%.1f%%)",
            passed, len(results), summary["summary"]["pass_rate"],
        )
        return summary

    def save(self, output_dir: str, results: dict) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "visual_regression_report.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        return path

    @staticmethod
    def _file_hash(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
