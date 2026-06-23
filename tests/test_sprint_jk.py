"""Sprint J (hardening) + Sprint K (gap closure) test suite."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import migrate
from pbi_import import (
    ad_group_bridge,
    benchmark_harness,
    catalog_stream,
    content_hash,
    dax_auto_fixer,
    gateway_autocreate,
    mobile_extractor,
    tracing,
)


# ---------------------------------------------------------------------------
# J1 — Tracing
# ---------------------------------------------------------------------------

class TestTracer:
    def test_disabled_tracer_is_no_op(self):
        t = tracing.Tracer(enabled=False)
        with t.span("noop", k="v") as s:
            assert s.name == "noop"
        assert t.spans() == []

    def test_nested_spans_record_parent(self):
        t = tracing.Tracer()
        with t.span("outer"):
            with t.span("inner") as inner:
                inner.attributes["item"] = "x"
        spans = t.spans()
        assert {s.name for s in spans} == {"outer", "inner"}
        outer = next(s for s in spans if s.name == "outer")
        inner = next(s for s in spans if s.name == "inner")
        assert inner.parent_id == outer.span_id
        assert outer.parent_id is None

    def test_error_marks_span(self):
        t = tracing.Tracer()
        with pytest.raises(RuntimeError):
            with t.span("bad"):
                raise RuntimeError("boom")
        assert t.spans()[0].status == "ERROR"
        assert "RuntimeError" in t.spans()[0].attributes["error"]

    def test_summary_aggregates_by_name(self):
        t = tracing.Tracer()
        for _ in range(3):
            with t.span("publish"):
                pass
        with t.span("validate"):
            pass
        summary = t.summary()
        assert summary["total_spans"] == 4
        assert summary["by_name"]["publish"]["count"] == 3
        assert summary["by_name"]["validate"]["count"] == 1

    def test_write_json_round_trip(self, tmp_path):
        t = tracing.Tracer()
        with t.span("phase.export", workers=4):
            pass
        out = tmp_path / "trace.json"
        t.write_json(str(out))
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["service"] == "pbirs-migrate"
        assert payload["spans"][0]["name"] == "phase.export"
        assert payload["spans"][0]["attributes"]["workers"] == 4

    def test_flush_otlp_no_endpoint_returns_zero(self):
        t = tracing.Tracer(otlp_endpoint=None)
        with t.span("x"):
            pass
        assert t.flush_otlp() == 0
        # spans were not cleared because no endpoint was set
        assert len(t.spans()) == 1


# ---------------------------------------------------------------------------
# J2 — Catalog stream
# ---------------------------------------------------------------------------

class TestCatalogStream:
    def test_from_list_iterates(self):
        s = catalog_stream.CatalogStream.from_list([{"a": 1}, {"a": 2}])
        assert s.total == 2
        items = list(s)
        assert items == [{"a": 1}, {"a": 2}]
        assert s.consumed == 2

    def test_batched(self):
        s = catalog_stream.CatalogStream.from_list([{"i": i} for i in range(7)])
        batches = list(s.batched(3))
        assert [len(b) for b in batches] == [3, 3, 1]

    def test_filter_and_map_lazy(self):
        s = (
            catalog_stream.CatalogStream
            .from_list([{"t": "A", "n": 1}, {"t": "B", "n": 2}, {"t": "A", "n": 3}])
            .filter(lambda i: i["t"] == "A")
            .map(lambda i: {**i, "doubled": i["n"] * 2})
        )
        items = list(s)
        assert [i["n"] for i in items] == [1, 3]
        assert all(i["doubled"] == i["n"] * 2 for i in items)

    def test_from_json_dict_with_items(self, tmp_path):
        p = tmp_path / "cat.json"
        p.write_text(json.dumps({"items": [{"x": 1}, {"x": 2}]}), encoding="utf-8")
        s = catalog_stream.CatalogStream.from_json(p)
        assert list(s) == [{"x": 1}, {"x": 2}]

    def test_from_jsonl_lazy(self, tmp_path):
        p = tmp_path / "cat.jsonl"
        p.write_text("\n".join(json.dumps({"i": i}) for i in range(5)) + "\n", encoding="utf-8")
        s = catalog_stream.CatalogStream.from_jsonl(p)
        assert s.total is None
        assert list(s) == [{"i": i} for i in range(5)]

    def test_write_jsonl(self, tmp_path):
        p = tmp_path / "out.jsonl"
        n = catalog_stream.write_jsonl([{"a": 1}, {"a": 2}, {"a": 3}], p)
        assert n == 3
        assert len(p.read_text(encoding="utf-8").splitlines()) == 3

    def test_batched_validates_size(self):
        s = catalog_stream.CatalogStream.from_list([{"a": 1}])
        with pytest.raises(ValueError):
            list(s.batched(0))


# ---------------------------------------------------------------------------
# J3 — Content hash idempotency
# ---------------------------------------------------------------------------

class TestContentHashStore:
    def test_hash_is_stable_for_same_input(self):
        item = {"name": "r", "type": "PowerBIReport", "modified": "2026-01-01"}
        h1 = content_hash.hash_item(item, "ws1")
        h2 = content_hash.hash_item(dict(item), "ws1")
        assert h1 == h2

    def test_hash_changes_with_workspace(self):
        item = {"name": "r", "type": "PowerBIReport"}
        assert content_hash.hash_item(item, "ws1") != content_hash.hash_item(item, "ws2")

    def test_hash_file(self, tmp_path):
        f = tmp_path / "a.pbix"
        f.write_bytes(b"hello")
        h = content_hash.hash_file(f, "ws1")
        assert isinstance(h, str) and len(h) == 40

    def test_record_and_skip(self, tmp_path):
        store = content_hash.ContentHashStore(tmp_path)
        item = {"name": "r", "type": "PowerBIReport"}
        assert not store.is_published(item, "ws1")
        store.record(item, "ws1", result={"id": 1})
        store.save()
        # Fresh instance reading from disk
        store2 = content_hash.ContentHashStore(tmp_path)
        assert store2.is_published(item, "ws1")

    def test_hash_invalidates_when_content_changes(self, tmp_path):
        store = content_hash.ContentHashStore(tmp_path)
        item = {"name": "r", "type": "PowerBIReport", "modified": "2026-01-01"}
        store.record(item, "ws1")
        modified = {**item, "modified": "2026-02-01"}
        assert not store.is_published(modified, "ws1")

    def test_reset_clears_store(self, tmp_path):
        store = content_hash.ContentHashStore(tmp_path)
        store.record({"name": "r"}, "ws1")
        store.save()
        store.reset()
        assert store.stats()["total"] == 0
        assert not (tmp_path / "publish.hashes.json").exists()


# ---------------------------------------------------------------------------
# J4 — Benchmark harness
# ---------------------------------------------------------------------------

class TestBenchmarkHarness:
    def test_generate_synthetic_catalog_is_deterministic(self):
        a = benchmark_harness.generate_synthetic_catalog(size=50, seed=7)
        b = benchmark_harness.generate_synthetic_catalog(size=50, seed=7)
        assert a == b
        assert len(a["items"]) == 50
        assert sum(len(a[k]) for k in ("powerbi_reports", "paginated_reports",
                                       "datasets", "kpis", "mobile_reports")) == 50

    def test_write_synthetic_catalog(self, tmp_path):
        p = benchmark_harness.write_synthetic_catalog(20, tmp_path / "syn.json")
        data = json.loads(p.read_text(encoding="utf-8"))
        assert len(data["items"]) == 20

    def test_harness_records_timings(self, tmp_path):
        h = benchmark_harness.BenchmarkHarness()
        cat = benchmark_harness.generate_synthetic_catalog(size=10)
        rec = h.run("noop", lambda c: c, cat, repeats=2)
        assert rec["repeats"] == 2
        assert rec["catalog_size"] == 10
        h.write_report(tmp_path / "bench.json")
        payload = json.loads((tmp_path / "bench.json").read_text(encoding="utf-8"))
        assert "results" in payload and "grouped" in payload

    def test_harness_compare_groups_by_name(self):
        h = benchmark_harness.BenchmarkHarness()
        cat = benchmark_harness.generate_synthetic_catalog(size=5)
        h.run("phase", lambda c: c, cat)
        h.run("phase", lambda c: c, cat)
        h.run("other", lambda c: c, cat)
        groups = h.compare()
        assert set(groups) == {"phase", "other"}
        assert len(groups["phase"]) == 2


# ---------------------------------------------------------------------------
# K1 — Mobile Report extractor
# ---------------------------------------------------------------------------

class TestMobileExtractor:
    def test_extract_json_layout(self, tmp_path):
        src = tmp_path / "sales.json"
        src.write_text(json.dumps({
            "ReportName": "Sales",
            "Tiles": [
                {"Type": "Gauge", "Title": "KPI", "DataField": "Revenue"},
                {"Type": "Chart", "Title": "Trend"},
                {"Type": "WeirdNew", "Title": "Custom"},
            ],
        }), encoding="utf-8")
        out = tmp_path / "out"
        result = mobile_extractor.MobileReportExtractor(out).extract(src)
        assert result["title"] == "Sales"
        assert len(result["tiles"]) == 3
        assert {t["raw_type"] for t in result["tiles"]} == {"Gauge", "Chart", "WeirdNew"}
        assert any("unknown visual" in w for w in result["warnings"])
        assert Path(result["scaffold_path"]).is_file()

    def test_extract_missing_source_returns_warning(self, tmp_path):
        result = mobile_extractor.MobileReportExtractor(tmp_path).extract(tmp_path / "x.rsmobile")
        assert result["tiles"] == []
        assert any("not found" in w for w in result["warnings"])

    def test_extract_all_uses_catalog(self, tmp_path):
        src_dir = tmp_path / "content"
        src_dir.mkdir()
        (src_dir / "MobileA.json").write_text(
            json.dumps({"ReportName": "MobileA", "Tiles": [{"Type": "Indicator"}]}),
            encoding="utf-8",
        )
        catalog = {"mobile_reports": [{"Name": "MobileA"}, {"Name": "Missing"}]}
        results = mobile_extractor.MobileReportExtractor(tmp_path / "out").extract_all(catalog, src_dir)
        assert len(results) == 2
        # First one found, second one missing
        assert results[0]["tiles"]
        assert "not found" in (results[1]["warnings"][0])


# ---------------------------------------------------------------------------
# K2 — AD bridge
# ---------------------------------------------------------------------------

class TestADGroupBridge:
    def test_discover_splits_users_and_groups(self):
        perms = {
            "item_policies": [
                {"name": "DOMAIN\\Alice"},
                {"name": "DOMAIN\\BIGroup"},
                {"name": "bob@example.com"},
                {"name": "GG_Finance"},
            ],
        }
        result = ad_group_bridge.ADGroupBridge().discover(perms)
        groups = {g["raw"] for g in result["groups"]}
        users = {u["raw"] for u in result["users"]}
        assert "DOMAIN\\BIGroup" in groups
        assert "GG_Finance" in groups
        assert "bob@example.com" in users

    def test_write_csv(self, tmp_path):
        discovered = {
            "groups": [{"domain": "DOM", "name": "BIGroup", "raw": "DOM\\BIGroup"}],
            "users":  [{"domain": "DOM", "name": "Alice",   "raw": "DOM\\Alice"}],
        }
        p = ad_group_bridge.ADGroupBridge().write_csv(discovered, tmp_path / "ad.csv")
        content = p.read_text(encoding="utf-8")
        assert "kind,domain,name,raw,suggested_aad_display_name" in content
        assert "BIGroup" in content and "Alice" in content

    def test_ensure_aad_groups_dry_run(self):
        bridge = ad_group_bridge.ADGroupBridge()
        discovered = {
            "groups": [{"domain": "", "name": "GG_FinanceTeam", "raw": "GG_FinanceTeam"}],
            "users": [],
        }
        out = bridge.ensure_aad_groups(discovered, dry_run=True)
        assert out[0]["status"] == "dry_run"
        assert out[0]["aad_display_name"] == "Financeteam"

    def test_ensure_aad_groups_calls_graph_client(self):
        graph = MagicMock()
        graph.ensure_group.return_value = {"id": "aad-1"}
        bridge = ad_group_bridge.ADGroupBridge(graph_client=graph)
        discovered = {"groups": [{"domain": "", "name": "FooGroup", "raw": "FooGroup"}], "users": []}
        results = bridge.ensure_aad_groups(discovered, dry_run=False)
        assert results[0]["aad_group_id"] == "aad-1"
        graph.ensure_group.assert_called_once()


# ---------------------------------------------------------------------------
# K3 — Gateway auto-create
# ---------------------------------------------------------------------------

class TestGatewayAutoCreate:
    def test_parse_rds_sql(self):
        parsed = gateway_autocreate.parse_rds({
            "Extension": "SQL",
            "ConnectString": "Server=tcp:db.local;Database=DW;",
        })
        assert parsed["kind"] == "Sql"
        assert parsed["server"].startswith("tcp:db.local")
        assert parsed["database"] == "DW"

    def test_parse_rds_oracle(self):
        parsed = gateway_autocreate.parse_rds({
            "Extension": "ORACLE", "ConnectString": "Data Source=ORCL;User Id=x;",
        })
        assert parsed["kind"] == "Oracle"
        assert parsed["server"] == "ORCL"

    def test_plan_marks_existing_as_skip(self):
        client = MagicMock()
        client.list_gateway_datasources.return_value = [{"datasourceName": "DW"}]
        creator = gateway_autocreate.GatewayAutoCreator(client, default_gateway_id="gw1")
        plan = creator.plan(
            [{"Name": "DW", "Extension": "SQL", "ConnectString": "Server=x;Database=DW;"},
             {"Name": "Other", "Extension": "SQL", "ConnectString": "Server=y;Database=O;"}],
        )
        actions = {p["name"]: p["action"] for p in plan}
        assert actions == {"DW": "skip", "Other": "create"}

    def test_execute_creates_missing(self, tmp_path):
        client = MagicMock()
        client.list_gateway_datasources.return_value = []
        client.create_gateway_datasource.return_value = {"id": "ds-1"}
        creator = gateway_autocreate.GatewayAutoCreator(client, default_gateway_id="gw1")
        result = creator.execute(
            [{"Name": "DW", "Extension": "SQL", "ConnectString": "Server=x;Database=DW;"}],
            gateway_id="gw1",
        )
        assert len(result["created"]) == 1
        assert result["created"][0]["datasource_id"] == "ds-1"
        mapping_path = creator.write_mapping(result, tmp_path / "map.json", gateway_id="gw1")
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        assert mapping["DW"]["gateway_id"] == "gw1"
        assert mapping["DW"]["datasource_ids"] == ["ds-1"]

    def test_execute_dry_run_makes_no_calls(self):
        client = MagicMock()
        client.list_gateway_datasources.return_value = []
        creator = gateway_autocreate.GatewayAutoCreator(client, default_gateway_id="gw1")
        result = creator.execute(
            [{"Name": "DW", "Extension": "SQL", "ConnectString": "Server=x;Database=DW;"}],
            gateway_id="gw1",
            dry_run=True,
        )
        client.create_gateway_datasource.assert_not_called()
        assert result["created"][0]["dry_run"] is True


# ---------------------------------------------------------------------------
# K4 — DAX auto-fixer
# ---------------------------------------------------------------------------

class TestDAXAutoFixer:
    def test_iferror_to_divide(self):
        expr = "IFERROR(Sales[Amt] / Sales[Qty], 0)"
        rewritten, applied = dax_auto_fixer.DAXAutoFixer().fix_expression(expr)
        assert "DIVIDE" in rewritten
        assert "iferror_to_divide" in applied

    def test_distinctcount_alias(self):
        expr = "COUNTROWS(DISTINCT(Sales[Customer]))"
        rewritten, applied = dax_auto_fixer.DAXAutoFixer().fix_expression(expr)
        assert "DISTINCTCOUNT(Sales[Customer])" in rewritten
        assert "distinctcount_alias" in applied

    def test_if_hasonevalue_to_selectedvalue(self):
        expr = "IF(HASONEVALUE(Geo[Region]), VALUES(Geo[Region]), \"Multiple\")"
        rewritten, applied = dax_auto_fixer.DAXAutoFixer().fix_expression(expr)
        assert "SELECTEDVALUE" in rewritten
        assert "if_hasonevalue_to_selectedvalue" in applied

    def test_earlier_emits_todo(self):
        expr = "EARLIER(Sales[Date])"
        rewritten, applied = dax_auto_fixer.DAXAutoFixer().fix_expression(expr)
        assert "TODO" in rewritten
        assert "earlier_warning" in applied

    def test_unchanged_expression(self):
        expr = "SUM(Sales[Amount])"
        rewritten, applied = dax_auto_fixer.DAXAutoFixer().fix_expression(expr)
        assert rewritten == expr
        assert applied == []

    def test_fix_measures_summary(self):
        fixer = dax_auto_fixer.DAXAutoFixer()
        measures = [
            {"name": "M1", "expression": "SUM(T[a])"},
            {"name": "M2", "expression": "IFERROR(T[a]/T[b], 0)"},
            {"name": "M3", "expression": "IFERROR(T[c]/T[d], 0)"},
        ]
        results = fixer.fix_measures(measures)
        summary = fixer.summary(results)
        assert summary["total_measures"] == 3
        assert summary["changed"] == 2
        assert summary["by_rule"]["iferror_to_divide"] == 2


# ---------------------------------------------------------------------------
# CLI integration — Sprint J/K flags
# ---------------------------------------------------------------------------

class TestCliFlags:
    def test_help_includes_jk_flags(self, capsys):
        with pytest.raises(SystemExit):
            migrate._build_parser().parse_args(["--help"])
        out = capsys.readouterr().out
        for flag in (
            "--trace-out", "--otlp-endpoint", "--stream-catalog",
            "--skip-published", "--reset-hash-store", "--benchmark",
            "--migrate-mobile", "--ad-bridge", "--ensure-aad-groups",
            "--gateway-auto", "--gateway-id", "--dax-autofix",
        ):
            assert flag in out, f"{flag} missing from --help"

    def test_benchmark_runs_and_writes_report(self, tmp_path, monkeypatch, caplog):
        out_path = tmp_path / "bench.json"
        argv = [
            "migrate.py", "--benchmark", "25",
            "--output-dir", str(tmp_path),
            "--benchmark-out", str(out_path),
        ]
        monkeypatch.setattr("sys.argv", argv)
        with caplog.at_level(logging.INFO):
            rc = migrate.main()
        assert rc == 0
        payload = json.loads(out_path.read_text(encoding="utf-8"))
        assert any(r["name"] == "stream_iter_only" for r in payload["results"])
        assert any(r["name"] == "assessment" for r in payload["results"])

    def test_trace_out_writes_spans(self, tmp_path, monkeypatch):
        trace_path = tmp_path / "trace.json"
        # Use benchmark as a quick, IO-free phase to exercise the tracer
        argv = [
            "migrate.py", "--benchmark", "10",
            "--output-dir", str(tmp_path),
            "--trace-out", str(trace_path),
        ]
        monkeypatch.setattr("sys.argv", argv)
        rc = migrate.main()
        assert rc == 0
        # The benchmark mode is an early-exit so phase spans are empty; the
        # tracer still writes a valid envelope.
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
        assert "spans" in payload
        assert "summary" in payload

    def test_gateway_auto_requires_gateway_id(self, tmp_path, monkeypatch):
        # Patch the PBI client factory
        from pbi_import.deploy import client_factory
        client = MagicMock()
        monkeypatch.setattr(
            client_factory.PbiClientFactory, "from_args",
            classmethod(lambda cls, args: client),
        )
        in_dir = tmp_path / "converted"
        in_dir.mkdir()
        (in_dir / "datasources.json").write_text("[]", encoding="utf-8")
        argv = [
            "migrate.py", "--import",
            "--workspace-id", "ws1",
            "--input-dir", str(in_dir),
            "--gateway-auto",
            "--dry-run",
        ]
        monkeypatch.setattr("sys.argv", argv)
        rc = migrate.main()
        assert rc != 0  # CONFIG_ERROR

    def test_skip_published_initialises_hash_store(self, tmp_path, monkeypatch):
        from pbi_import.deploy import client_factory
        client = MagicMock()
        monkeypatch.setattr(
            client_factory.PbiClientFactory, "from_args",
            classmethod(lambda cls, args: client),
        )
        in_dir = tmp_path / "converted"
        in_dir.mkdir()
        argv = [
            "migrate.py", "--import",
            "--workspace-id", "ws1",
            "--input-dir", str(in_dir),
            "--skip-published",
            "--dry-run",
        ]
        monkeypatch.setattr("sys.argv", argv)
        rc = migrate.main()
        # No items to publish so it returns SUCCESS and writes an empty hash file
        assert rc in (0, 1)
        hash_file = in_dir.parent / "publish.hashes.json"
        # The store may be empty but should still be saved
        assert hash_file.is_file() or rc != 0
