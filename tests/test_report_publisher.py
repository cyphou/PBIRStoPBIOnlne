"""Tests for ReportPublisher."""

import zipfile
import json
from pathlib import Path

import pytest

from pbi_import.report_publisher import ReportPublisher


def _write_valid_pbix(path: Path, display_name: str = "Report", connections_payload: dict | None = None) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Version", "1.0")
        zf.writestr("[Content_Types].xml", "<Types />")
        zf.writestr("Report/Layout", '{"sections":[{"displayName":"%s"}]}' % display_name)
        zf.writestr("Settings", '{"Version":1}')
        zf.writestr("Metadata", '{"Version":3}')
        zf.writestr("Connections", json.dumps(connections_payload or {"Version": 1, "Connections": []}))
        zf.writestr("SecurityBindings", "")
        zf.writestr("DiagramLayout", '{"version":"1.0"}')
        zf.writestr("docProps/custom.xml", "<Properties><property name='PBIDesktopVersion'><vt:lpwstr>2.125.816.0</vt:lpwstr></property></Properties>")


class TestReportPublisher:

    def test_publish_no_files(self, mock_pbi_client, tmp_path):
        publisher = ReportPublisher(mock_pbi_client)
        result = publisher.publish_all(str(tmp_path), "ws-001")
        assert result["success"] == []

    def test_publish_dry_run(self, mock_pbi_client, tmp_path):
        powerbi_dir = tmp_path / "powerbi"
        powerbi_dir.mkdir()
        _write_valid_pbix(powerbi_dir / "Sales.pbix", "Sales")

        publisher = ReportPublisher(mock_pbi_client)
        result = publisher.publish_all(str(tmp_path), "ws-001", dry_run=True)
        assert len(result["success"]) == 1
        assert result["success"][0]["status"] == "dry_run"
        mock_pbi_client.import_pbix.assert_not_called()

    def test_publish_pbix(self, mock_pbi_client, tmp_path):
        powerbi_dir = tmp_path / "powerbi"
        powerbi_dir.mkdir()
        _write_valid_pbix(powerbi_dir / "Report.pbix", "Report")

        publisher = ReportPublisher(mock_pbi_client)
        result = publisher.publish_all(str(tmp_path), "ws-001")
        assert len(result["success"]) == 1
        assert result["success"][0]["status"] == "published"
        mock_pbi_client.import_pbix.assert_called_once()

    def test_publish_pbix_uses_large_strategy(self, mock_pbi_client, tmp_path):
        powerbi_dir = tmp_path / "powerbi"
        powerbi_dir.mkdir()
        _write_valid_pbix(powerbi_dir / "Large.pbix", "Large")

        mock_pbi_client.create_temporary_upload_location.return_value = "https://upload.example"
        mock_pbi_client.upload_chunk.return_value = None
        mock_pbi_client.complete_upload.return_value = {"id": "imp-large", "datasets": [{"id": "ds-large"}]}

        # Force large strategy by setting a tiny threshold.
        publisher = ReportPublisher(mock_pbi_client, large_file_threshold_mb=0)
        result = publisher.publish_all(str(tmp_path), "ws-001")

        assert len(result["success"]) == 1
        assert result["success"][0]["status"] == "published"
        assert result["success"][0]["strategy"] == "large"
        mock_pbi_client.import_pbix.assert_not_called()
        mock_pbi_client.create_temporary_upload_location.assert_called_once()
        mock_pbi_client.complete_upload.assert_called_once()

    def test_publish_pbix_large_strategy_missing_methods_fails(self, tmp_path):
        from unittest.mock import MagicMock

        powerbi_dir = tmp_path / "powerbi"
        powerbi_dir.mkdir()
        _write_valid_pbix(powerbi_dir / "Large.pbix", "Large")

        client = MagicMock(spec=["import_pbix"])  # no enhanced methods
        publisher = ReportPublisher(client, large_file_threshold_mb=0)
        result = publisher.publish_all(str(tmp_path), "ws-001")

        assert len(result["failed"]) == 1
        assert "enhanced large-file import methods" in result["failed"][0]["error"]

    def test_publish_pbix_three_size_bands_strategy_matrix(self, mock_pbi_client, tmp_path, monkeypatch):
        """Cover roadmap strategy matrix for <500MB, 500MB-1GB, and >1GB bands."""
        powerbi_dir = tmp_path / "powerbi"
        powerbi_dir.mkdir()

        small = powerbi_dir / "small.pbix"
        mid = powerbi_dir / "mid.pbix"
        large = powerbi_dir / "large.pbix"
        _write_valid_pbix(small, "small")
        _write_valid_pbix(mid, "mid")
        _write_valid_pbix(large, "large")

        # Simulate effective file-band classification without creating massive files on disk.
        def _fake_needs_chunked(path: str, threshold_mb: int = 1024) -> bool:
            name = Path(path).name
            if name == "large.pbix":
                return True
            return False

        monkeypatch.setattr(
            "pbi_import.report_publisher.LargeFileHandler.needs_chunked_upload",
            _fake_needs_chunked,
        )

        publisher = ReportPublisher(mock_pbi_client)
        result = publisher.publish_all(str(tmp_path), "ws-001", dry_run=True)

        assert len(result["success"]) == 3
        by_name = {item["name"]: item for item in result["success"]}

        # <500MB: standard
        assert by_name["small"]["strategy"] == "standard"
        # 500MB-1GB: standard
        assert by_name["mid"]["strategy"] == "standard"
        # >1GB: large
        assert by_name["large"]["strategy"] == "large"

    def test_publish_skips_service_live_pbix_before_upload(self, mock_pbi_client, tmp_path):
        powerbi_dir = tmp_path / "powerbi"
        powerbi_dir.mkdir()
        _write_valid_pbix(
            powerbi_dir / "Live.pbix",
            "Live",
            connections_payload={
                "Version": 1,
                "Connections": [{"ConnectionType": "pbiServiceLive"}],
            },
        )

        publisher = ReportPublisher(mock_pbi_client)
        result = publisher.publish_all(str(tmp_path), "ws-001")

        assert len(result["success"]) == 0
        assert len(result["failed"]) == 0
        assert len(result["skipped"]) == 1
        assert "pbiServiceLive" in json.dumps(result["skipped"][0].get("compatibility", {}))
        mock_pbi_client.import_pbix.assert_not_called()
