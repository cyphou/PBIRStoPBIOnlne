"""Smoke test: end-to-end pipeline against an in-memory PBIRS + mocked PBI client.

Exercises the wiring of ``migrate.main()`` for ``--full`` so future signature
drift between the orchestrator and the publisher/mapper/validator classes is
caught immediately.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import migrate


@pytest.fixture
def fake_pbi_client():
    """Mock PBIClient that satisfies every publisher / mapper / validator call."""
    client = MagicMock()
    client.list_workspaces.return_value = [{"id": "ws-1", "name": "Test WS"}]
    client.get_workspace_by_name.return_value = {"id": "ws-1", "name": "Test WS"}
    client.list_reports.return_value = [{"id": "r1"}]
    client.list_datasets.return_value = [{"id": "d1", "name": "DS1"}]
    client.list_gateways.return_value = []
    client.list_workspace_users.return_value = [{"u": "a"}, {"u": "b"}]
    client.get_dataset_datasources.return_value = [{"gatewayId": "gw1"}]
    client.get_refresh_schedule.return_value = {"enabled": True}
    client.import_pbix.return_value = {"id": "imp1", "datasets": [{"id": "d1"}]}
    client.import_rdl.return_value = {"id": "imp2"}
    return client


@pytest.fixture
def fake_pbirs_client():
    client = MagicMock()
    client.get_system_info.return_value = {"ProductName": "PBIRS"}
    client.list_catalog_items.return_value = [
        {"Id": "i1", "Name": "Sales", "Path": "/Sales", "Type": "PowerBIReport"},
    ]
    client.list_subscriptions.return_value = []
    client.list_schedules.return_value = []
    return client


def _run_cli(argv, monkeypatch, fake_pbirs_client, fake_pbi_client):
    monkeypatch.setattr(sys, "argv", ["migrate"] + argv)
    with patch("pbirs_export.api_client.PBIRSClient", return_value=fake_pbirs_client), \
         patch("pbi_import.deploy.client_factory.PbiClientFactory.from_args",
               return_value=fake_pbi_client):
        return migrate.main()


class TestCliWiring:
    def test_assess_only_succeeds(self, tmp_path, monkeypatch, fake_pbirs_client, fake_pbi_client):
        rc = _run_cli(
            ["--server", "http://x", "--assess", "--output-dir", str(tmp_path)],
            monkeypatch, fake_pbirs_client, fake_pbi_client,
        )
        assert rc == migrate.ExitCode.SUCCESS
        assert (tmp_path / "assessment_report.json").exists()
        assert (tmp_path / "assessment_report.html").exists()

    def test_import_phase_uses_real_apis(self, tmp_path, monkeypatch, fake_pbirs_client, fake_pbi_client):
        """The import phase must construct publishers with a pbi_client (not a workspace id)."""
        # Seed minimal converted output
        converted = tmp_path / "converted"
        (converted / "powerbi").mkdir(parents=True)
        (converted / "paginated").mkdir(parents=True)
        (converted / "datasets").mkdir(parents=True)

        rc = _run_cli(
            ["--import", "--input-dir", str(converted), "--workspace-id", "ws-1",
             "--no-migrate-permissions", "--no-migrate-subscriptions",
             "--no-migrate-schedules", "--dry-run"],
            monkeypatch, fake_pbirs_client, fake_pbi_client,
        )
        # No items to publish but pipeline should not crash with TypeError.
        assert rc in (migrate.ExitCode.SUCCESS, migrate.ExitCode.PARTIAL)

    def test_validate_phase_uses_real_apis(self, tmp_path, monkeypatch, fake_pbirs_client, fake_pbi_client):
        """Validation must use validate_all + generate_html_report on MigrationValidator."""
        (tmp_path / "inventory.json").write_text(json.dumps({"items": []}))
        rc = _run_cli(
            ["--validate", "--input-dir", str(tmp_path), "--output-dir", str(tmp_path),
             "--workspace-id", "ws-1"],
            monkeypatch, fake_pbirs_client, fake_pbi_client,
        )
        assert rc == migrate.ExitCode.SUCCESS
        assert (tmp_path / "validation_report.json").exists()
        assert (tmp_path / "validation_report.html").exists()

    def test_full_pipeline_uses_chained_subdirs(self, tmp_path, monkeypatch, fake_pbirs_client, fake_pbi_client):
        """--full must chain phases under one root using fixed subfolders."""
        rc = _run_cli(
            ["--server", "http://x", "--full", "--output-dir", str(tmp_path),
             "--workspace-id", "ws-1",
             "--no-migrate-permissions", "--no-migrate-subscriptions",
             "--no-migrate-schedules", "--dry-run"],
            monkeypatch, fake_pbirs_client, fake_pbi_client,
        )
        assert rc in (migrate.ExitCode.SUCCESS, migrate.ExitCode.PARTIAL)
        # Assessment dropped at root, export under /export, conversion under /converted
        assert (tmp_path / "assessment_report.json").exists()
        assert (tmp_path / "export" / "export_manifest.json").exists()


class TestPhaseDirs:
    def test_full_chains_root(self):
        ns = type("NS", (), {"output_dir": "out", "input_dir": None, "full": True})()
        assert migrate._phase_dirs(ns, "convert") == (Path("out/export"), Path("out/converted"))

    def test_export_propagates_filters(self, tmp_path, monkeypatch, fake_pbirs_client, fake_pbi_client):
        captured = {}

        def fake_extract(self, folder=None, content_types=None, include_pattern=None, exclude_pattern=None):
            captured.update(folder=folder, content_types=content_types,
                            include_pattern=include_pattern, exclude_pattern=exclude_pattern)
            return {"items": [], "folders": [], "total_count": 0, "server_info": {}}

        with patch("pbirs_export.catalog_extractor.CatalogExtractor.extract_catalog", fake_extract):
            _run_cli(
                ["--server", "http://x", "--export", "--output-dir", str(tmp_path),
                 "--include-pattern", "Sales.*", "--exclude-pattern", "Archived"],
                monkeypatch, fake_pbirs_client, fake_pbi_client,
            )
        assert captured["include_pattern"] == "Sales.*"
        assert captured["exclude_pattern"] == "Archived"


class TestEventLog:
    def test_jsonl_records_phase_events(self, tmp_path, monkeypatch, fake_pbirs_client, fake_pbi_client):
        log_path = tmp_path / "events.jsonl"
        _run_cli(
            ["--server", "http://x", "--assess", "--output-dir", str(tmp_path),
             "--event-log", str(log_path)],
            monkeypatch, fake_pbirs_client, fake_pbi_client,
        )
        lines = [json.loads(l) for l in log_path.read_text().splitlines() if l]
        events = [(e["phase"], e["event"]) for e in lines]
        assert ("pipeline", "start") in events
        assert ("assess", "phase_start") in events
        assert ("assess", "phase_end") in events
        assert ("pipeline", "end") in events
