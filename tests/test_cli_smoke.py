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


class TestCapabilityReport:
    def test_capability_report_early_exit(self, tmp_path, monkeypatch, fake_pbirs_client, fake_pbi_client):
        out_json = tmp_path / "capabilities.json"
        rc = _run_cli(
            ["--capability-report", "--capability-report-out", str(out_json)],
            monkeypatch, fake_pbirs_client, fake_pbi_client,
        )
        assert rc == migrate.ExitCode.SUCCESS
        assert out_json.exists()

        payload = json.loads(out_json.read_text(encoding="utf-8"))
        assert "capabilities" in payload
        assert any(c.get("id") == "feature.capability_report" for c in payload["capabilities"])


class TestSecurityDbAssist:
    def test_export_strict_fail_on_security_diff(
        self, tmp_path, monkeypatch, fake_pbirs_client, fake_pbi_client
    ):
        fake_result = {
            "merged_item_policies": [],
            "gap_report": {
                "enabled": True,
                "conflict_strategy": "strict-fail-on-diff",
                "total_items": 1,
                "diff_items_count": 1,
                "items": [{"item_path": "/Sales", "conflict": True}],
            },
        }

        with patch(
            "pbirs_export.security_inheritance_resolver.SecurityInheritanceResolver.resolve",
            return_value=fake_result,
        ):
            rc = _run_cli(
                [
                    "--server", "http://x", "--export", "--output-dir", str(tmp_path),
                    "--security-db-assist", "--security-conflict-strategy", "strict-fail-on-diff",
                    "--reportserver-db-conn", "Server=.;Database=ReportServer;Trusted_Connection=yes;",
                ],
                monkeypatch,
                fake_pbirs_client,
                fake_pbi_client,
            )
        assert rc == migrate.ExitCode.VALIDATION_ERROR
        assert (tmp_path / "security_gap_report.json").exists()


class TestGatewayAutoConnectionFlow:
    def test_gateway_auto_creates_and_binds(self, tmp_path, monkeypatch, fake_pbirs_client, fake_pbi_client):
        converted = tmp_path / "converted"
        (converted / "powerbi").mkdir(parents=True)
        (converted / "powerbi" / "Report.pbix").write_bytes(b"PK\x03\x04")
        (converted / "datasets").mkdir(parents=True)
        (converted / "paginated").mkdir(parents=True)

        # Export-style datasource payload with shared datasources
        (converted / "datasources.json").write_text(
            json.dumps(
                {
                    "shared_datasources": [
                        {
                            "Name": "Report",
                            "Extension": "SQL",
                            "ConnectString": "Server=tcp:db.local;Database=DW;",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        fake_pbi_client.list_gateway_datasources.return_value = []
        fake_pbi_client.create_gateway_datasource.return_value = {"id": "ds-created-1"}

        rc = _run_cli(
            [
                "--import",
                "--input-dir", str(converted),
                "--workspace-id", "ws-1",
                "--gateway-auto", "--gateway-id", "gw-1",
                "--no-migrate-permissions", "--no-migrate-subscriptions", "--no-migrate-schedules",
            ],
            monkeypatch,
            fake_pbirs_client,
            fake_pbi_client,
        )

        assert rc in (migrate.ExitCode.SUCCESS, migrate.ExitCode.PARTIAL)
        assert (converted / "gateway_mapping.auto.json").exists()
        assert (converted / "gateway_connection_report.json").exists()
        assert (converted / "connection_mapping.csv").exists()
        assert (converted / "connection_mapping_by_endpoint.csv").exists()
        fake_pbi_client.create_gateway_datasource.assert_called_once()
        assert fake_pbi_client.bind_to_gateway.called
