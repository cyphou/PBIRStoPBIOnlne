"""Tests for MigrationReport."""

import pytest
from pbi_import.migration_report import MigrationReport


class TestMigrationReport:

    def test_generate_report(self, tmp_path):
        report = MigrationReport()
        result = report.generate(
            assessment={"summary": {"total_items": 5, "green": 3, "yellow": 1, "red": 1}},
            export_results={"download_results": {"success": [1, 2, 3], "failed": [], "skipped": []}},
            conversion_results={"converted": 3, "skipped": 0, "failed": 0},
            import_results={"reports": {"success": [1, 2], "failed": []}},
            validation_results={"overall": "PASS", "issues": []},
            output_dir=str(tmp_path),
        )

        assert result["overall_status"] == "PASS"
        assert (tmp_path / "migration_report.json").exists()
        assert (tmp_path / "migration_report.html").exists()
