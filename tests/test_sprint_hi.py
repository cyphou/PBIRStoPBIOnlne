"""Tests for Sprint H (parity) and Sprint I (beyond parity) features."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import migrate
from pbi_import.audience_bucketer import AudienceBucketer
from pbi_import.branding_migrator import BrandingMigrator
from pbi_import.cache_plan_migrator import CachePlanMigrator
from pbi_import.linked_report_handler import LinkedReportHandler
from pbi_import.role_mapper import RoleMapper, PBI_ROLES
from pbi_import.sync_daemon import SyncDaemon, SyncIteration
from pbi_import.visual_diff_report import VisualDiffReport
from pbi_import.wave_planner import WavePlanner
from pbi_import.workspace_folder_manager import WorkspaceFolderManager


# ---------------------------------------------------------------------------
# H1 — Workspace folder manager
# ---------------------------------------------------------------------------

class TestWorkspaceFolderManager:
    def test_build_tree_dedupes_paths(self):
        catalog = [
            {"Path": "/Sales/2024/Q1/Report"},
            {"Path": "/Sales/2024/Q2/Report"},
            {"Path": "/HR/Onboarding/Welcome"},
        ]
        wfm = WorkspaceFolderManager(MagicMock())
        paths = wfm.build_tree(catalog)
        # No leaves, just folders
        assert "/Sales" in paths
        assert "/Sales/2024" in paths
        assert "/HR" in paths
        assert "/Sales/2024/Q1" in paths
        assert "/Sales/2024/Q1/Report" not in paths

    def test_ensure_folders_dry_run(self):
        wfm = WorkspaceFolderManager(MagicMock())
        mapping = wfm.ensure_folders("ws1", ["/A", "/A/B"], dry_run=True)
        assert mapping["/"] == "ws1"
        assert mapping["/A"].startswith("dry-run-folder")
        assert mapping["/A/B"].startswith("dry-run-folder")

    def test_ensure_folders_calls_client(self):
        client = MagicMock()
        client.create_folder.side_effect = [
            {"id": "fA"}, {"id": "fAB"},
        ]
        wfm = WorkspaceFolderManager(client)
        mapping = wfm.ensure_folders("ws1", ["/A", "/A/B"], dry_run=False)
        assert mapping["/A"] == "fA"
        assert mapping["/A/B"] == "fAB"
        assert client.create_folder.call_count == 2

    def test_resolve_item_folder(self):
        wfm = WorkspaceFolderManager(MagicMock())
        mapping = {"/": "ws1", "/Sales": "fSales", "/Sales/2024": "f2024"}
        assert wfm.resolve_item_folder("/Sales/2024/Report1", mapping) == "f2024"
        assert wfm.resolve_item_folder("/Other/X", mapping) == "ws1"


# ---------------------------------------------------------------------------
# H2 — Linked report handler
# ---------------------------------------------------------------------------

class TestLinkedReportHandler:
    def _catalog(self):
        return [
            {"Name": "BaseReport", "Type": "Report"},
            {"Name": "Linked1", "Type": "LinkedReport", "LinkSourceId": "abc",
             "Parameters": [{"Name": "Year", "DefaultValues": [2024]}]},
            {"Name": "Linked2", "Type": "LinkedReport", "LinkSourceId": "def"},
        ]

    def test_detect(self):
        h = LinkedReportHandler()
        assert len(h.detect(self._catalog())) == 2

    def test_convert_bookmarks_writes_files(self, tmp_path):
        h = LinkedReportHandler(strategy="bookmarks")
        result = h.convert_all(self._catalog(), tmp_path)
        assert result["detected"] == 2
        assert result["converted"] == 2
        # One bookmark JSON per linked
        files = list(tmp_path.glob("*.bookmark.json"))
        assert len(files) == 2
        payload = json.loads(files[0].read_text(encoding="utf-8"))
        assert "sourceReportId" in payload

    def test_convert_paginated_writes_files(self, tmp_path):
        h = LinkedReportHandler(strategy="paginated")
        result = h.convert_all(self._catalog(), tmp_path)
        assert result["converted"] == 2
        assert len(list(tmp_path.glob("*.paginated.json"))) == 2

    def test_skip_strategy(self, tmp_path):
        h = LinkedReportHandler(strategy="skip")
        result = h.convert_all(self._catalog(), tmp_path)
        assert result["skipped"] == 2
        assert result["converted"] == 0

    def test_invalid_strategy_raises(self):
        with pytest.raises(ValueError):
            LinkedReportHandler(strategy="bogus")


# ---------------------------------------------------------------------------
# H3 — Audience bucketer
# ---------------------------------------------------------------------------

class TestAudienceBucketer:
    def _policies(self):
        return [
            {"item_id": "1", "item_name": "R1",
             "principals": [{"name": "alice@x", "role": "Viewer"}]},
            {"item_id": "2", "item_name": "R2",
             "principals": [{"name": "alice@x", "role": "Viewer"}]},
            {"item_id": "3", "item_name": "R3",
             "principals": [{"name": "bob@x", "role": "Admin"}]},
        ]

    def test_groups_identical_acls(self):
        b = AudienceBucketer().bucket(self._policies())
        # 2 distinct ACL signatures → 2 audiences
        assert len(b["audiences"]) == 2
        # R1 + R2 collapsed
        names = {a["name"]: len(a["items"]) for a in b["audiences"]}
        assert max(names.values()) == 2

    def test_overflow_collapse(self):
        # 12 distinct signatures, max=3 → should collapse to 3 with last being "Other"
        policies = [
            {"item_id": str(i), "item_name": f"R{i}",
             "principals": [{"name": f"user{i}@x", "role": "Viewer"}]}
            for i in range(12)
        ]
        b = AudienceBucketer(max_audiences=3).bucket(policies)
        assert len(b["audiences"]) == 3
        assert b["overflow"] == 12 - 3
        assert b["audiences"][-1]["name"].endswith("Other")


# ---------------------------------------------------------------------------
# H4 — Role mapper
# ---------------------------------------------------------------------------

class TestRoleMapper:
    def test_defaults_match_doc(self):
        rm = RoleMapper()
        assert rm.resolve("Browser") == "Viewer"
        assert rm.resolve("Content Manager") == "Admin"

    def test_overrides_applied(self):
        rm = RoleMapper(overrides={"Auditor": "Viewer", "Browser": "Member"})
        assert rm.resolve("Auditor") == "Viewer"
        assert rm.resolve("Browser") == "Member"

    def test_invalid_pbi_role_raises(self):
        with pytest.raises(ValueError):
            RoleMapper(overrides={"X": "Superuser"})

    def test_from_file(self, tmp_path):
        f = tmp_path / "roles.json"
        f.write_text(json.dumps({"Custom": "Admin"}), encoding="utf-8")
        rm = RoleMapper.from_file(str(f))
        assert rm.resolve("Custom") == "Admin"

    def test_suggest_heuristic(self):
        rm = RoleMapper()
        assert rm.suggest("ReportAuthor") == "Contributor"
        assert rm.suggest("ReadOnlyAuditor") == "Viewer"
        assert rm.suggest("DataAdmin") == "Admin"

    def test_pbi_roles_constant(self):
        assert "Viewer" in PBI_ROLES
        assert "Admin" in PBI_ROLES


# ---------------------------------------------------------------------------
# H5 — Cache plan migrator
# ---------------------------------------------------------------------------

class TestCachePlanMigrator:
    def test_daily_plan(self):
        plan = {
            "Name": "nightly",
            "Enabled": True,
            "TimeZone": "UTC",
            "Schedule": {"Definition": {"Daily": True, "StartDateTime": "2024-01-01T02:30:00"}},
        }
        payload = CachePlanMigrator().migrate(plan)
        assert payload["value"]["enabled"] is True
        assert payload["value"]["times"] == ["02:30"]
        assert len(payload["value"]["days"]) == 7

    def test_weekly_plan(self):
        plan = {
            "Name": "weekly",
            "Enabled": True,
            "Schedule": {"Definition": {"Weekly": {"DaysOfWeek": ["Monday", "Friday"]},
                                         "StartDateTime": "2024-01-01T06:00:00"}},
        }
        payload = CachePlanMigrator().migrate(plan)
        assert set(payload["value"]["days"]) == {"Monday", "Friday"}

    def test_disabled_plan_returns_none(self):
        assert CachePlanMigrator().migrate({"Enabled": False}) is None

    def test_migrate_all_aggregates(self):
        plans = [
            {"Name": "p1", "Enabled": True,
             "Schedule": {"Definition": {"Daily": True, "StartDateTime": "2024-01-01T02:00:00"}}},
            {"Name": "p2", "Enabled": False},
        ]
        result = CachePlanMigrator().migrate_all(plans)
        assert len(result["translated"]) == 1
        assert result["skipped"] == 1


# ---------------------------------------------------------------------------
# H6 — Branding migrator
# ---------------------------------------------------------------------------

class TestBrandingMigrator:
    def test_theme_uses_provided_palette(self, tmp_path):
        brand = {"name": "Corp", "palette": ["#112233", "#445566", "#778899",
                                              "#AABBCC", "#DDEEFF", "#001122"]}
        theme = BrandingMigrator().to_report_theme(brand)
        assert theme["dataColors"] == brand["palette"]

    def test_theme_falls_back_when_palette_invalid(self):
        brand = {"name": "X", "palette": ["not-a-hex"]}
        theme = BrandingMigrator().to_report_theme(brand)
        assert len(theme["dataColors"]) >= 6
        assert all(c.startswith("#") for c in theme["dataColors"])

    def test_write_theme_creates_file(self, tmp_path):
        path = BrandingMigrator().write_theme({"name": "Corp"}, tmp_path)
        assert path.is_file()
        assert json.loads(path.read_text(encoding="utf-8"))["name"] == "Corp"

    def test_migrate_dry_run_skips_client(self, tmp_path):
        client = MagicMock()
        res = BrandingMigrator().migrate(
            {"name": "Corp"}, "ws1", tmp_path, dry_run=True, pbi_client=client
        )
        assert res["status"] == "prepared"
        client.update_workspace.assert_not_called()

    def test_migrate_applies_to_client(self, tmp_path):
        client = MagicMock()
        res = BrandingMigrator().migrate(
            {"name": "Corp", "description": "d"}, "ws1", tmp_path, pbi_client=client
        )
        assert res["status"] == "applied"
        client.update_workspace.assert_called_once()


# ---------------------------------------------------------------------------
# I1 — Sync daemon
# ---------------------------------------------------------------------------

class TestSyncDaemon:
    def test_runs_max_iterations_and_replays_delta(self):
        fetch = MagicMock(return_value=[{"Id": "a"}])
        tracker = MagicMock()
        tracker.detect_changes.return_value = {
            "new": [{"Id": "a"}], "modified": [],
            "unchanged": [], "deleted": [],
        }
        replay = MagicMock(return_value={"replayed": 1})
        daemon = SyncDaemon(fetch, tracker, replay,
                            poll_interval=0.01, max_iterations=2)
        results = daemon.run()
        assert len(results) == 2
        assert replay.call_count == 2
        assert results[0].new == 1

    def test_stop_request_breaks_loop(self):
        fetch = MagicMock(return_value=[])
        tracker = MagicMock()
        tracker.detect_changes.return_value = {"new": [], "modified": [], "unchanged": [], "deleted": []}
        replay = MagicMock()

        def slow_replay(_):
            return {}

        replay.side_effect = slow_replay
        daemon = SyncDaemon(fetch, tracker, replay,
                            poll_interval=0.05, max_iterations=10)

        # Stop immediately after first iteration
        def stopper(_iter: SyncIteration):
            daemon.request_stop()

        daemon.on_iteration = stopper
        results = daemon.run()
        assert len(results) == 1

    def test_exception_recorded(self):
        fetch = MagicMock(side_effect=RuntimeError("boom"))
        tracker = MagicMock()
        replay = MagicMock()
        daemon = SyncDaemon(fetch, tracker, replay,
                            poll_interval=0.01, max_iterations=1)
        results = daemon.run()
        assert results[0].errors == ["boom"]


# ---------------------------------------------------------------------------
# I2 — Wave planner
# ---------------------------------------------------------------------------

class TestWavePlanner:
    def test_simple_dependency_order(self):
        catalog = [
            {"Id": "ds1", "Name": "ds1", "Type": "DataSet"},
            {"Id": "r1", "Name": "r1", "Type": "Report", "DependsOn": ["ds1"]},
            {"Id": "r2", "Name": "r2", "Type": "Report", "DependsOn": ["ds1", "r1"]},
        ]
        plan = WavePlanner().plan(catalog)
        # ds1 in wave 1, r1 in wave 2, r2 in wave 3
        assert plan["wave_count"] == 3
        assert {i["id"] for i in plan["waves"][0]} == {"ds1"}
        assert {i["id"] for i in plan["waves"][1]} == {"r1"}
        assert {i["id"] for i in plan["waves"][2]} == {"r2"}

    def test_cycle_detection(self):
        catalog = [
            {"Id": "a", "Name": "a", "DependsOn": ["b"]},
            {"Id": "b", "Name": "b", "DependsOn": ["a"]},
        ]
        plan = WavePlanner().plan(catalog)
        assert len(plan["cycles"]) == 1

    def test_max_wave_size_chunks_items(self):
        catalog = [{"Id": f"i{i}", "Name": f"i{i}"} for i in range(7)]
        plan = WavePlanner(max_wave_size=3).plan(catalog)
        # All independent → one wave by topology, chunked to 3 waves of 3,3,1
        assert plan["wave_count"] == 3

    def test_get_wave_indexing(self, tmp_path):
        plan = WavePlanner().plan([
            {"Id": "a", "Name": "a"},
            {"Id": "b", "Name": "b"},
        ])
        wp = WavePlanner()
        items = wp.get_wave(plan, 1)
        assert len(items) == 2
        with pytest.raises(IndexError):
            wp.get_wave(plan, 99)

    def test_write_plan_persists(self, tmp_path):
        plan = WavePlanner().plan([{"Id": "a", "Name": "a"}])
        path = WavePlanner().write_plan(plan, tmp_path / "plan.json")
        assert path.is_file()
        assert json.loads(path.read_text(encoding="utf-8"))["wave_count"] == 1


# ---------------------------------------------------------------------------
# I3 — Visual diff report
# ---------------------------------------------------------------------------

class TestVisualDiffReport:
    def test_generates_html(self, tmp_path):
        before = tmp_path / "b.png"
        after = tmp_path / "a.png"
        before.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")
        after.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")

        out = tmp_path / "report.html"
        summary = VisualDiffReport().generate(
            [{"name": "Report1", "before": str(before), "after": str(after)}],
            out,
        )
        assert out.is_file()
        html = out.read_text(encoding="utf-8")
        assert "Visual Diff Report" in html
        assert "Report1" in html
        assert summary["total"] == 1

    def test_handles_missing_file(self, tmp_path):
        out = tmp_path / "report.html"
        summary = VisualDiffReport().generate(
            [{"name": "Missing", "before": str(tmp_path / "no.png"),
              "after": str(tmp_path / "no.png")}],
            out,
        )
        assert summary["error"] == 1

    def test_summary_includes_high_risk_and_top_offenders(self, tmp_path):
        before_ok = tmp_path / "ok_before.png"
        after_ok = tmp_path / "ok_after.png"
        before_ok.write_bytes(b"\x89PNG\r\n\x1a\nSAME")
        after_ok.write_bytes(b"\x89PNG\r\n\x1a\nSAME")

        out = tmp_path / "report.html"
        summary = VisualDiffReport().generate(
            [
                {"name": "Missing", "before": str(tmp_path / "none.png"), "after": str(tmp_path / "none.png")},
                {"name": "Same", "before": str(before_ok), "after": str(after_ok)},
            ],
            out,
        )

        assert "high_risk_count" in summary
        assert summary["high_risk_count"] >= 1
        assert "top_offenders" in summary
        assert len(summary["top_offenders"]) >= 1
        html = out.read_text(encoding="utf-8")
        assert "Top Offenders" in html


# ---------------------------------------------------------------------------
# CLI integration — new flags
# ---------------------------------------------------------------------------

def _patched_pbi_client():
    client = MagicMock()
    client.get_workspace_by_name.return_value = {"id": "ws1"}
    return client


@pytest.fixture
def fake_pbi_client(monkeypatch):
    client = _patched_pbi_client()
    monkeypatch.setattr(
        "pbi_import.deploy.client_factory.PbiClientFactory.from_args",
        classmethod(lambda cls, args: client),
    )
    return client


class TestCliFlags:
    def test_help_includes_all_new_flags(self, capsys):
        with pytest.raises(SystemExit):
            migrate._build_parser().parse_args(["--help"])
        out = capsys.readouterr().out
        for flag in (
            "--preserve-folders", "--linked-as", "--ils-as-audiences",
            "--role-map", "--migrate-cache-plans", "--migrate-branding",
            "--sync-daemon", "--plan-waves", "--wave-out", "--wave",
            "--visual-diff-report", "--diff-pairs",
        ):
            assert flag in out, f"{flag} missing from --help output"

    def test_plan_waves_writes_plan(self, tmp_path, monkeypatch, caplog):
        # Seed catalog
        root = tmp_path / "artifacts"
        (root / "export").mkdir(parents=True)
        (root / "export" / "export_manifest.json").write_text(
            json.dumps({
                "catalog": {
                    "items": [
                        {"Id": "a", "Name": "a"},
                        {"Id": "b", "Name": "b", "DependsOn": ["a"]},
                    ]
                }
            }),
            encoding="utf-8",
        )
        argv = [
            "migrate.py", "--plan-waves",
            "--output-dir", str(root),
            "--wave-out", str(root / "plan.json"),
        ]
        monkeypatch.setattr("sys.argv", argv)
        rc = migrate.main()
        assert rc == 0
        assert (root / "plan.json").is_file()
        plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
        assert plan["wave_count"] == 2

    def test_sync_daemon_requires_server(self, tmp_path, monkeypatch):
        argv = ["migrate.py", "--sync-daemon", "--output-dir", str(tmp_path)]
        monkeypatch.setattr("sys.argv", argv)
        rc = migrate.main()
        assert rc != 0  # CONFIG_ERROR

    def test_sync_daemon_runs_one_iteration(self, tmp_path, monkeypatch):
        # Patch the PBIRS client + delta tracker to avoid real I/O
        fake_client = MagicMock()
        fake_client.get_catalog_items.return_value = []
        monkeypatch.setattr(
            "pbirs_export.api_client.PBIRSClient",
            lambda **kw: fake_client,
        )
        argv = [
            "migrate.py", "--sync-daemon",
            "--server", "https://pbirs.local/reports",
            "--sync-poll-interval", "0.01",
            "--sync-max-iterations", "1",
            "--output-dir", str(tmp_path),
        ]
        monkeypatch.setattr("sys.argv", argv)
        rc = migrate.main()
        assert rc == 0
        fake_client.get_catalog_items.assert_called_once()

    def test_role_map_flag_loads_overrides(self, tmp_path, monkeypatch, fake_pbi_client):
        role_file = tmp_path / "roles.json"
        role_file.write_text(json.dumps({"AuditorX": "Viewer"}), encoding="utf-8")

        # Stub permission_mapper.ROLE_MAP through the import chain
        from pbi_import import permission_mapper
        original = dict(permission_mapper.ROLE_MAP)
        try:
            # Build an empty input dir so the import phase exits cleanly
            in_dir = tmp_path / "converted"
            in_dir.mkdir()
            argv = [
                "migrate.py", "--import",
                "--workspace-id", "ws1",
                "--input-dir", str(in_dir),
                "--role-map", str(role_file),
                "--dry-run",
            ]
            monkeypatch.setattr("sys.argv", argv)
            migrate.main()
            assert permission_mapper.ROLE_MAP.get("AuditorX") == "Viewer"
        finally:
            permission_mapper.ROLE_MAP.clear()
            permission_mapper.ROLE_MAP.update(original)
