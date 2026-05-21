"""Tests for ContentDownloader — parallel download and progress bar."""

from unittest.mock import MagicMock, patch
import pytest

from pbirs_export.content_downloader import ContentDownloader


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.download_powerbi_report.return_value = b"pbix-fake-content"
    client.download_report.return_value = b"rdl-fake-content"
    client.download_dataset.return_value = b"rsd-fake-content"
    client.get_catalog_item_content.return_value = b"rds-fake-content"
    return client


@pytest.fixture
def catalog_3_items():
    return {
        "items": [
            {"Id": "1", "Name": "Report A", "Path": "/Dir/Report A", "Type": "PowerBIReport"},
            {"Id": "2", "Name": "Report B", "Path": "/Dir/Report B", "Type": "Report"},
            {"Id": "3", "Name": "DS C", "Path": "/Dir/DS C", "Type": "DataSet"},
        ],
    }


class TestContentDownloaderParallel:

    def test_sequential_download(self, mock_client, catalog_3_items, tmp_path):
        dl = ContentDownloader(mock_client, str(tmp_path), workers=1)
        results = dl.download_all(catalog_3_items, show_progress=False)
        assert len(results["success"]) == 3
        assert len(results["failed"]) == 0

    def test_parallel_download(self, mock_client, catalog_3_items, tmp_path):
        dl = ContentDownloader(mock_client, str(tmp_path), workers=4)
        results = dl.download_all(catalog_3_items, show_progress=False)
        assert len(results["success"]) == 3
        assert len(results["failed"]) == 0

    def test_parallel_default_workers(self, mock_client, catalog_3_items, tmp_path):
        dl = ContentDownloader(mock_client, str(tmp_path))
        assert dl.workers == 4

    def test_custom_workers(self, mock_client, catalog_3_items, tmp_path):
        dl = ContentDownloader(mock_client, str(tmp_path), workers=8)
        assert dl.workers == 8

    def test_dry_run_is_sequential(self, mock_client, catalog_3_items, tmp_path):
        dl = ContentDownloader(mock_client, str(tmp_path), workers=4)
        results = dl.download_all(catalog_3_items, dry_run=True, show_progress=False)
        assert len(results["success"]) == 3
        assert all(r.get("dry_run") for r in results["success"])
        # No actual download calls
        mock_client.download_powerbi_report.assert_not_called()

    def test_skip_non_downloadable(self, mock_client, tmp_path):
        catalog = {"items": [
            {"Id": "1", "Name": "KPI", "Path": "/KPI", "Type": "Kpi"},
        ]}
        dl = ContentDownloader(mock_client, str(tmp_path), workers=2)
        results = dl.download_all(catalog, show_progress=False)
        assert len(results["skipped"]) == 1
        assert len(results["success"]) == 0

    def test_handles_download_failure(self, mock_client, tmp_path):
        mock_client.download_powerbi_report.side_effect = RuntimeError("network error")
        catalog = {"items": [
            {"Id": "1", "Name": "Bad Report", "Path": "/Bad Report", "Type": "PowerBIReport"},
        ]}
        dl = ContentDownloader(mock_client, str(tmp_path), workers=2)
        results = dl.download_all(catalog, show_progress=False)
        assert len(results["failed"]) == 1
        assert "network error" in results["failed"][0]["error"]

    def test_empty_catalog(self, mock_client, tmp_path):
        dl = ContentDownloader(mock_client, str(tmp_path), workers=4)
        results = dl.download_all({"items": []}, show_progress=False)
        assert results == {"success": [], "failed": [], "skipped": []}

    def test_files_written_parallel(self, mock_client, catalog_3_items, tmp_path):
        dl = ContentDownloader(mock_client, str(tmp_path), workers=4)
        dl.download_all(catalog_3_items, show_progress=False)
        # Check content files exist (exclude checkpoint file)
        written = list(tmp_path.rglob("*"))
        files = [f for f in written if f.is_file() and f.name != ".checkpoint.json"]
        assert len(files) == 3
