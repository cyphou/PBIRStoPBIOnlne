"""Tests for ReportPublisher."""

import pytest
from pathlib import Path
from pbi_import.report_publisher import ReportPublisher


class TestReportPublisher:

    def test_publish_no_files(self, mock_pbi_client, tmp_path):
        publisher = ReportPublisher(mock_pbi_client)
        result = publisher.publish_all(str(tmp_path), "ws-001")
        assert result["success"] == []

    def test_publish_dry_run(self, mock_pbi_client, tmp_path):
        powerbi_dir = tmp_path / "powerbi"
        powerbi_dir.mkdir()
        (powerbi_dir / "Sales.pbix").write_bytes(b"PK\x03\x04fake")

        publisher = ReportPublisher(mock_pbi_client)
        result = publisher.publish_all(str(tmp_path), "ws-001", dry_run=True)
        assert len(result["success"]) == 1
        assert result["success"][0]["status"] == "dry_run"
        mock_pbi_client.import_pbix.assert_not_called()

    def test_publish_pbix(self, mock_pbi_client, tmp_path):
        powerbi_dir = tmp_path / "powerbi"
        powerbi_dir.mkdir()
        (powerbi_dir / "Report.pbix").write_bytes(b"PK\x03\x04fake")

        publisher = ReportPublisher(mock_pbi_client)
        result = publisher.publish_all(str(tmp_path), "ws-001")
        assert len(result["success"]) == 1
        assert result["success"][0]["status"] == "published"
        mock_pbi_client.import_pbix.assert_called_once()
