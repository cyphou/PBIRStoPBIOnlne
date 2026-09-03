"""Smoke test: end-to-end pipeline against an in-memory PBIRS + mocked PBI client.

Exercises the wiring of ``migrate.main()`` for ``--full`` so future signature
drift between the orchestrator and the publisher/mapper/validator classes is
caught immediately.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import zipfile

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
    def test_windows_auth_prompts_for_missing_credentials(self, monkeypatch):
        args = type("NS", (), {
            "use_windows_auth": True,
            "prompt_windows_credentials": True,
            "token": None,
            "username": None,
            "password": None,
        })()
        monkeypatch.delenv("PBIRS_TOKEN", raising=False)
        monkeypatch.delenv("PBIRS_USERNAME", raising=False)
        monkeypatch.delenv("PBIRS_PASSWORD", raising=False)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda prompt: "DOMAIN\\user")
        monkeypatch.setattr(migrate.getpass, "getpass", lambda prompt: "secret")

        migrate._populate_pbirs_credentials(args)

        assert args.username == "DOMAIN\\user"
        assert args.password == "secret"

    def test_windows_auth_does_not_prompt_noninteractive(self, monkeypatch):
        args = type("NS", (), {
            "use_windows_auth": True,
            "prompt_windows_credentials": True,
            "token": None,
            "username": None,
            "password": None,
        })()
        monkeypatch.delenv("PBIRS_TOKEN", raising=False)
        monkeypatch.delenv("PBIRS_USERNAME", raising=False)
        monkeypatch.delenv("PBIRS_PASSWORD", raising=False)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        prompt = MagicMock()
        monkeypatch.setattr("builtins.input", prompt)

        migrate._populate_pbirs_credentials(args)

        prompt.assert_not_called()
        assert args.username is None
        assert args.password is None

    def test_windows_auth_uses_current_user_without_prompt_by_default(self, monkeypatch):
        args = type("NS", (), {
            "use_windows_auth": True,
            "prompt_windows_credentials": False,
            "token": None,
            "username": None,
            "password": None,
        })()
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        prompt = MagicMock()
        monkeypatch.setattr("builtins.input", prompt)

        migrate._populate_pbirs_credentials(args)

        prompt.assert_not_called()
        assert args.username is None
        assert args.password is None

    def test_assess_only_succeeds(self, tmp_path, monkeypatch, fake_pbirs_client, fake_pbi_client):
        fake_pbirs_client.list_datasources.return_value = []
        fake_pbirs_client.get_system_policies.return_value = []
        fake_pbirs_client.get_item_policies.return_value = []
        rc = _run_cli(
            ["--server", "http://x", "--assess", "--output-dir", str(tmp_path)],
            monkeypatch, fake_pbirs_client, fake_pbi_client,
        )
        assert rc == migrate.ExitCode.SUCCESS
        assert (tmp_path / "assessment_report.json").exists()
        assert (tmp_path / "assessment_report.html").exists()
        assert (tmp_path / "folders_mapping.csv").exists()
        assert (tmp_path / "users_mapping.csv").exists()
        assert (tmp_path / "folder_access_mapping.csv").exists()
        assert (tmp_path / "connections_mapping.csv").exists()
        assert (tmp_path / "rls_ols_role_accounts.csv").exists()
        assert (tmp_path / "bpa_accounts.csv").exists()
        assert (tmp_path / "permissions.json").exists()
        assert (tmp_path / "security.json").exists()

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

    def test_capability_report_includes_powerbi_desktop_rs_readiness(self, tmp_path, monkeypatch,
                                                                      fake_pbirs_client, fake_pbi_client):
        program_files = tmp_path / "Program Files"
        desktop_bin = program_files / "Microsoft Power BI Desktop RS" / "bin"
        desktop_bin.mkdir(parents=True)
        (desktop_bin / "PBIDesktop.exe").write_text("", encoding="utf-8")

        local_app_data = tmp_path / "LocalAppData"
        workspace = local_app_data / "Microsoft" / "Power BI Desktop SSRS" / "AnalysisServicesWorkspaces" / "Workspace1"
        workspace.mkdir(parents=True)
        (workspace / "msmdsrv.port.txt").write_text("12345", encoding="utf-8")

        monkeypatch.setenv("ProgramFiles", str(program_files))
        monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))

        out_json = tmp_path / "capabilities.json"
        rc = _run_cli(
            ["--capability-report", "--capability-report-out", str(out_json)],
            monkeypatch, fake_pbirs_client, fake_pbi_client,
        )
        assert rc == migrate.ExitCode.SUCCESS

        payload = json.loads(out_json.read_text(encoding="utf-8"))
        ids = {c.get("id") for c in payload["capabilities"]}
        assert "tool.powerbi_desktop_rs.installed" in ids
        assert "tool.powerbi_desktop_rs.authoring_session" in ids

    def test_capability_report_marks_large_pbix_path_ready(self, tmp_path, monkeypatch,
                                                            fake_pbirs_client, fake_pbi_client):
        out_json = tmp_path / "capabilities.json"
        rc = _run_cli(
            ["--capability-report", "--capability-report-out", str(out_json)],
            monkeypatch, fake_pbirs_client, fake_pbi_client,
        )
        assert rc == migrate.ExitCode.SUCCESS

        payload = json.loads(out_json.read_text(encoding="utf-8"))
        caps = {c.get("id"): c for c in payload["capabilities"]}
        assert caps["limitation.large_pbix_over_1gb"]["state"] == "ready"

    def test_capability_report_marks_db_bridges_partial_without_connection(self, tmp_path, monkeypatch,
                                                                            fake_pbirs_client, fake_pbi_client):
        monkeypatch.delenv("REPORTSERVER_DB_CONN", raising=False)
        out_json = tmp_path / "capabilities.json"
        rc = _run_cli(
            ["--capability-report", "--capability-report-out", str(out_json)],
            monkeypatch, fake_pbirs_client, fake_pbi_client,
        )
        assert rc == migrate.ExitCode.SUCCESS

        payload = json.loads(out_json.read_text(encoding="utf-8"))
        caps = {c.get("id"): c for c in payload["capabilities"]}
        assert caps["limitation.data_driven_query_bridge"]["state"] == "partial"
        assert caps["limitation.security_inheritance_db_bridge"]["state"] == "partial"


class TestSemanticMergeAssessment:
    def test_semantic_merge_assessment_generates_json_and_html(
        self, tmp_path, monkeypatch, fake_pbirs_client, fake_pbi_client
    ):
        catalog = {
            "items": [
                {"Name": "Sales Overview", "Type": "PowerBIReport", "DataSetReference": "SharedSales"},
                {"Name": "Sales Deep Dive", "Type": "PowerBIReport", "DataSetReference": "SharedSales"},
            ]
        }
        (tmp_path / "inventory.json").write_text(json.dumps(catalog), encoding="utf-8")

        rc = _run_cli(
            ["--assess-semantic-merge", "--output-dir", str(tmp_path)],
            monkeypatch,
            fake_pbirs_client,
            fake_pbi_client,
        )
        assert rc == migrate.ExitCode.SUCCESS
        assert (tmp_path / "semantic_merge_assessment.json").exists()
        assert (tmp_path / "semantic_merge_assessment.html").exists()

    def test_semantic_merge_assessment_marks_ready_for_shared_model_groups(
        self, tmp_path, monkeypatch, fake_pbirs_client, fake_pbi_client
    ):
        catalog = {
            "items": [
                {"Name": "Finance 1", "Type": "PowerBIReport", "DataSetReference": "FinanceModel"},
                {"Name": "Finance 2", "Type": "PowerBIReport", "DataSetReference": "FinanceModel"},
            ]
        }
        (tmp_path / "inventory.json").write_text(json.dumps(catalog), encoding="utf-8")

        rc = _run_cli(
            ["--assess-semantic-merge", "--output-dir", str(tmp_path)],
            monkeypatch,
            fake_pbirs_client,
            fake_pbi_client,
        )
        assert rc == migrate.ExitCode.SUCCESS

        payload = json.loads((tmp_path / "semantic_merge_assessment.json").read_text(encoding="utf-8"))
        summary = payload.get("summary", {})
        assert summary.get("semantic_merge_groups", 0) >= 1
        assert summary.get("status") in {"READY", "CONDITIONAL"}


class TestPbixCompatibilityReport:
    def _write_pbix(self, path: Path, *, include_data_model: bool = True) -> None:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("Version", "1.0")
            zf.writestr("[Content_Types].xml", "<Types />")
            zf.writestr("Report/Layout", json.dumps({"sections": [{"displayName": "ReportSection"}]}))
            zf.writestr("Settings", json.dumps({"Version": 1}))
            zf.writestr("Metadata", json.dumps({"Version": 3}))
            zf.writestr("Connections", json.dumps({"Version": 1, "Connections": []}))
            zf.writestr("SecurityBindings", "")
            zf.writestr("DiagramLayout", json.dumps({"version": "1.0"}))
            zf.writestr("docProps/custom.xml", "<Properties><property name='PBIDesktopVersion'><vt:lpwstr>2.125.816.0</vt:lpwstr></property></Properties>")
            if include_data_model:
                zf.writestr("DataModel", b"\x00" * 16)
                zf.writestr("DataMashup", b"\x00" * 16)

    def test_pbix_compatibility_report_generates_json_and_html(
        self, tmp_path, monkeypatch, fake_pbirs_client, fake_pbi_client
    ):
        converted = tmp_path / "converted"
        pbix_dir = converted / "powerbi"
        pbix_dir.mkdir(parents=True)
        self._write_pbix(pbix_dir / "Good.pbix")
        (pbix_dir / "Broken.pbix").write_text("not a zip", encoding="utf-8")

        rc = _run_cli(
            ["--pbix-compatibility-report", "--output-dir", str(tmp_path), "--input-dir", str(converted)],
            monkeypatch,
            fake_pbirs_client,
            fake_pbi_client,
        )

        assert rc == migrate.ExitCode.SUCCESS
        assert (tmp_path / "pbix_compatibility_report.json").exists()
        assert (tmp_path / "pbix_compatibility_report.html").exists()

        payload = json.loads((tmp_path / "pbix_compatibility_report.json").read_text(encoding="utf-8"))
        summary = payload.get("summary", {})
        assert summary.get("total_files") == 2
        assert summary.get("failed", 0) >= 1

    def test_pbix_compatibility_report_marks_good_packages_warn_or_pass(
        self, tmp_path, monkeypatch, fake_pbirs_client, fake_pbi_client
    ):
        converted = tmp_path / "converted"
        pbix_dir = converted / "powerbi"
        pbix_dir.mkdir(parents=True)
        self._write_pbix(pbix_dir / "Good.pbix")

        rc = _run_cli(
            ["--pbix-compatibility-report", "--output-dir", str(tmp_path), "--input-dir", str(converted)],
            monkeypatch,
            fake_pbirs_client,
            fake_pbi_client,
        )

        assert rc == migrate.ExitCode.SUCCESS
        payload = json.loads((tmp_path / "pbix_compatibility_report.json").read_text(encoding="utf-8"))
        summary = payload.get("summary", {})
        assert summary.get("status") in {"PASS", "WARN"}


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
    def _write_minimal_pbix(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("Version", "1.0")
            zf.writestr("[Content_Types].xml", "<Types />")
            zf.writestr("Report/Layout", json.dumps({"sections": [{"displayName": "ReportSection"}]}))
            zf.writestr("Settings", json.dumps({"Version": 1}))
            zf.writestr("Metadata", json.dumps({"Version": 3}))
            zf.writestr("Connections", json.dumps({"Version": 1, "Connections": []}))
            zf.writestr("SecurityBindings", "")
            zf.writestr("DiagramLayout", json.dumps({"version": "1.0"}))

    def test_gateway_auto_creates_and_binds(self, tmp_path, monkeypatch, fake_pbirs_client, fake_pbi_client):
        converted = tmp_path / "converted"
        (converted / "powerbi").mkdir(parents=True)
        self._write_minimal_pbix(converted / "powerbi" / "Report.pbix")
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


class TestExportModelRolePropagation:
    def test_export_includes_model_role_principals_in_artifacts(
        self, tmp_path, monkeypatch, fake_pbirs_client, fake_pbi_client
    ):
        class _FakeLoader:
            def load(self, _source_path):
                return {
                    "available": True,
                    "source": str(tmp_path / "model_snapshot.json"),
                    "roles": [
                        {"name": "RLS_Finance", "members": ["CONTOSO\\FinanceReaders"]},
                        {"name": "OLS_Restricted"},
                    ],
                }

        with patch("pbi_import.model_snapshot.ModelSnapshotLoader", _FakeLoader):
            rc = _run_cli(
                ["--server", "http://x", "--export", "--output-dir", str(tmp_path)],
                monkeypatch,
                fake_pbirs_client,
                fake_pbi_client,
            )

        assert rc == migrate.ExitCode.SUCCESS

        role_payload = json.loads((tmp_path / "rls_ols_role_accounts.json").read_text(encoding="utf-8"))
        role_rows = role_payload.get("rows", [])
        assert any(
            r.get("source") == "model_snapshot.roles" and r.get("account") == "CONTOSO\\FinanceReaders"
            for r in role_rows
        )
        assert "OLS_Restricted" in role_payload.get("summary", {}).get("model_roles_without_members", [])

        bpa_payload = json.loads((tmp_path / "bpa_accounts.json").read_text(encoding="utf-8"))
        assert bpa_payload.get("summary", {}).get("model_role_principal_count", 0) >= 1
        assert any(
            "CONTOSO\\FinanceReaders" in item.get("model_role_principals", [])
            for item in bpa_payload.get("items", [])
        )
