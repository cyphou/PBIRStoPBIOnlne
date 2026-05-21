"""Tests for v2.0–v4.0 new modules."""

import json
import os
import tempfile
import pytest


# ── v2.0 Enterprise Scale ──────────────────────────────────────────────

class TestFolderMapper:
    def test_auto_generate(self):
        from pbirs_export.folder_mapper import FolderMapper
        catalog = [
            {"Path": "/Sales/Q1", "Name": "R1", "Type": "PowerBIReport"},
            {"Path": "/Sales/Q2", "Name": "R2", "Type": "PowerBIReport"},
            {"Path": "/HR/Reports", "Name": "R3", "Type": "Report"},
        ]
        fm = FolderMapper.auto_generate(catalog)
        assert fm.resolve("/Sales/Q1/R1") is not None
        assert fm.resolve("/HR/Reports/R3") is not None

    def test_resolve_all(self):
        from pbirs_export.folder_mapper import FolderMapper
        rules = [
            {"folder": "/Sales", "workspace_name": "ws-sales"},
            {"folder": "/HR", "workspace_name": "ws-hr"},
        ]
        fm = FolderMapper(rules)
        catalog = [
            {"Path": "/Sales/Q1"},
            {"Path": "/HR/Reports"},
        ]
        result = fm.resolve_all(catalog)
        assert "ws-sales" in result
        assert "ws-hr" in result

    def test_from_file(self):
        from pbirs_export.folder_mapper import FolderMapper
        rules = [{"folder": "/Finance", "workspace_name": "ws-fin"}]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(rules, f)
            f.flush()
            fm = FolderMapper.from_file(f.name)
        os.unlink(f.name)
        r = fm.resolve("/Finance/Report")
        assert r is not None
        assert r["workspace_name"] == "ws-fin"

    def test_save(self):
        from pbirs_export.folder_mapper import FolderMapper
        rules = [{"folder": "/A", "workspace_name": "ws-a"}]
        fm = FolderMapper(rules)
        with tempfile.TemporaryDirectory() as td:
            path = fm.save(os.path.join(td, "rules.json"))
            assert path.exists()


class TestDeltaTracker:
    def test_detect_and_record(self):
        from pbirs_export.delta_tracker import DeltaTracker
        with tempfile.TemporaryDirectory() as td:
            dt = DeltaTracker(os.path.join(td, "delta.db"))
            item = {"Id": "1", "Name": "R1", "Path": "/R1", "Type": "PowerBIReport", "ModifiedDate": "2024-01-01"}
            changes = dt.detect_changes([item])
            assert len(changes["new"]) == 1
            dt.record(item)
            changes2 = dt.detect_changes([item])
            assert len(changes2["unchanged"]) == 1
            dt.close()

    def test_summary(self):
        from pbirs_export.delta_tracker import DeltaTracker
        with tempfile.TemporaryDirectory() as td:
            dt = DeltaTracker(os.path.join(td, "d.db"))
            s = dt.summary()
            assert s["total"] == 0
            dt.close()


class TestMultiWorkspaceManager:
    def test_dispatch_items(self):
        from pbi_import.multi_workspace import MultiWorkspaceManager
        mgr = MultiWorkspaceManager(None)
        workspace_plan = {
            "ws-1": [{"Name": "R1"}],
            "ws-2": [{"Name": "R2"}],
        }
        workspace_mapping = {"ws-1": "id-1", "ws-2": "id-2"}
        result = mgr.dispatch_items(workspace_plan, workspace_mapping)
        assert len(result) == 2
        assert result[0]["workspace_name"] in ("ws-1", "ws-2")


class TestAppPublisher:
    def test_publish_dry_run(self):
        from pbi_import.app_publisher import AppPublisher
        pub = AppPublisher(None)
        result = pub.publish("ws-1", dry_run=True)
        assert result["status"] == "dry_run"


class TestLargeFileHandler:
    def test_needs_chunked(self):
        from pbi_import.large_file_handler import LargeFileHandler
        # needs_chunked_upload is a staticmethod that takes a file path
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pbix") as f:
            # Write >1GB of data indicator — just test with a small file
            f.write(b"x" * 100)
            f.flush()
            assert LargeFileHandler.needs_chunked_upload(f.name) is False
        os.unlink(f.name)


class TestTenantMigrator:
    def test_plan(self):
        from pbi_import.tenant_migrator import TenantMigrator

        class FakeClient:
            def list_reports(self, ws_id):
                return [{"name": "R1", "type": "report"}] if ws_id == "src" else []

        tm = TenantMigrator(FakeClient(), FakeClient())
        plan = tm.plan("src", "target")
        assert plan["summary"]["to_migrate"] >= 0


# ── v2.1 Governance & Compliance ───────────────────────────────────────

class TestAuditLogger:
    def test_log_and_query(self):
        from pbi_import.audit_logger import AuditLogger
        with tempfile.TemporaryDirectory() as td:
            al = AuditLogger(td)
            al.log("test_action", item_name="R1", outcome="success")
            al.log("test_action", item_name="R2", outcome="failure")
            entries = al.query()
            assert len(entries) == 2

    def test_summary(self):
        from pbi_import.audit_logger import AuditLogger
        with tempfile.TemporaryDirectory() as td:
            al = AuditLogger(td)
            al.log("phase", outcome="success")
            s = al.summary()
            assert s["total_entries"] == 1


class TestSensitivityLabeler:
    def test_classify(self):
        from pbi_import.sensitivity_labeler import SensitivityLabeler
        sl = SensitivityLabeler(None)
        catalog = [
            {"Name": "R1", "Type": "PowerBIReport", "classification": {"pii_detected": True}},
            {"Name": "R2", "Type": "Report"},
        ]
        result = sl.classify_catalog(catalog)
        assert len(result) == 2


class TestEndorsementManager:
    def test_plan(self):
        from pbi_import.endorsement_manager import EndorsementManager
        em = EndorsementManager(None)
        published = [
            {"name": "R1"},
            {"name": "R2"},
            {"name": "R3"},
        ]
        assessments = {
            "items": [
                {"name": "R1", "overall_score": 95},
                {"name": "R2", "overall_score": 80},
                {"name": "R3", "overall_score": 50},
            ],
        }
        plan = em.plan(published, assessments)
        assert len(plan) == 3
        assert plan[0]["endorsement"] == "Certified"
        assert plan[1]["endorsement"] == "Promoted"
        assert plan[2]["endorsement"] is None


class TestLineageExtractor:
    def test_extract(self):
        from pbirs_export.lineage_extractor import LineageExtractor
        catalog = [
            {
                "Id": "1", "Name": "DS1", "Type": "DataSource", "Path": "/DS1",
                "ConnectionString": "server=x;db=y",
            },
            {
                "Id": "2", "Name": "R1", "Type": "PowerBIReport", "Path": "/R1",
                "DataSources": [{"Name": "DS1", "Path": "/DS1"}],
            },
        ]
        le = LineageExtractor(catalog)
        graph = le.extract()
        assert len(graph["nodes"]) == 2
        assert len(graph["edges"]) >= 1

    def test_save(self):
        from pbirs_export.lineage_extractor import LineageExtractor
        le = LineageExtractor([])
        with tempfile.TemporaryDirectory() as td:
            path = le.save(td)
            assert path.exists()


class TestDataClassifier:
    def test_scan_detects_sensitive(self):
        from pbirs_export.data_classifier import DataClassifier
        dc = DataClassifier()
        # DataClassifier scans item Name, Description, Path, and DataSource fields
        items = [
            {"Name": "SSN_Report", "Path": "/HR/SSN"},
        ]
        results = dc.scan(items)
        assert len(results) >= 1
        assert results[0]["risk_level"] in ("high", "medium", "low")
        assert len(results[0]["findings"]) >= 1


# ── v2.2 Advanced Security ─────────────────────────────────────────────

class TestRLSGenerator:
    def test_generate(self):
        from pbi_import.rls_generator import RLSGenerator
        security = {
            "item_permissions": [
                {"item_path": "/Sales/R1", "policies": [
                    {"principal": "user@test.com"},
                ]},
            ],
            "effective_permissions": [],
        }
        gen = RLSGenerator(security)
        result = gen.generate()
        assert "roles" in result
        assert result["summary"]["total_roles"] >= 1

    def test_save(self):
        from pbi_import.rls_generator import RLSGenerator
        security = {"item_permissions": [], "effective_permissions": []}
        gen = RLSGenerator(security)
        with tempfile.TemporaryDirectory() as td:
            path = gen.save(td)
            assert path.exists()


class TestOLSMapper:
    def test_detect_hidden(self):
        from pbi_import.ols_mapper import OLSMapper
        # OLSMapper uses rdl_analyses in constructor and matches by report name
        rdl_data = [
            {"report_name": "R1", "hidden_fields": [{"name": "SSN", "table": "Employees"}]},
        ]
        mapper = OLSMapper(rdl_data)
        catalog = [{"Name": "R1", "Path": "/R1"}]
        hidden = mapper.detect_hidden_fields(catalog)
        assert len(hidden) == 1
        assert hidden[0]["report_name"] == "R1"


class TestADGroupProvisioner:
    def test_plan(self):
        from pbi_import.ad_group_provisioner import ADGroupProvisioner
        prov = ADGroupProvisioner(None)
        security = {
            "principals": [
                {"name": "SalesGroup", "type": "Group", "domain": "CORP", "members": ["user1"]},
                {"name": "user2", "type": "User", "domain": "CORP"},
            ],
        }
        plan = prov.plan(security)
        assert len(plan) == 1  # Only the Group principal
        assert plan[0]["azure_ad_name"] == "Migrated-SalesGroup"


class TestPermissionDiff:
    def test_compare(self):
        from pbi_import.permission_diff import PermissionDiff
        diff = PermissionDiff()
        pbirs = {
            "effective_permissions": [
                {"principal": "user1@test.com", "pbi_role": "Viewer", "items": ["/R1"]},
                {"principal": "user2@test.com", "pbi_role": "Admin", "items": ["/R2"]},
            ],
        }
        ws_perms = [
            {"emailAddress": "user1@test.com", "groupUserAccessRight": "Viewer"},
        ]
        result = diff.compare(pbirs, "ws-1", ws_perms)
        assert result["summary"]["unchanged"] >= 1
        assert result["summary"]["removed"] >= 1  # user2 not in target


# ── v2.3 Data Source Modernization ─────────────────────────────────────

class TestConnectionTransformer:
    def test_transform_sql(self):
        from pbi_import.connection_transformer import ConnectionTransformer
        ct = ConnectionTransformer()
        ds = [{
            "Name": "ds1",
            "ConnectionString": "Data Source=myserver;Initial Catalog=MyDB",
            "Provider": "System.Data.SqlClient",
        }]
        results = ct.transform_all(ds)
        assert results[0]["changed"] is True
        assert "database.windows.net" in results[0]["transformed"]

    def test_no_match(self):
        from pbi_import.connection_transformer import ConnectionTransformer
        ct = ConnectionTransformer()
        ds = [{"Name": "x", "ConnectionString": "unknown=value", "Provider": "Custom"}]
        results = ct.transform_all(ds)
        assert results[0]["changed"] is False


class TestGatewayCluster:
    def test_recommend_cluster(self):
        from pbi_import.gateway_cluster import GatewayCluster
        gc = GatewayCluster(None)
        clusters = [
            {"name": "C1", "members": [{"status": "Online"}, {"status": "Offline"}]},
            {"name": "C2", "members": [{"status": "Online"}, {"status": "Online"}]},
        ]
        best = gc.recommend_cluster([], clusters)
        assert best["name"] == "C2"


class TestDatasourceConsolidator:
    def test_consolidate(self):
        from pbi_import.datasource_consolidator import DatasourceConsolidator
        dc = DatasourceConsolidator()
        ds = [
            {"Name": "ds1", "ConnectionString": "Server=A;Database=B", "Provider": "Sql"},
            {"Name": "ds2", "ConnectionString": "Server=A; Database=B", "Provider": "Sql"},
            {"Name": "ds3", "ConnectionString": "Server=C;Database=D", "Provider": "Sql"},
        ]
        result = dc.consolidate(ds)
        assert result["summary"]["duplicates_found"] >= 1
        assert result["summary"]["unique_connections"] <= 3


class TestQueryModeAdvisor:
    def test_analyse(self):
        from pbi_import.query_mode_advisor import QueryModeAdvisor
        advisor = QueryModeAdvisor()
        catalog = [
            {"Name": "R1", "Type": "PowerBIReport", "DataSources": []},
            {"Name": "R2", "Type": "PowerBIReport", "DataSources": [
                {"DataSourceType": "AzureSqlDatabase"},
            ]},
        ]
        results = advisor.analyse(catalog)
        assert len(results) == 2
        summary = advisor.summary(results)
        assert summary["total"] == 2


# ── v2.4 Semantic Model Intelligence ──────────────────────────────────

class TestDAXHealthChecker:
    def test_check_healthy(self):
        from pbi_import.dax_health_checker import DAXHealthChecker
        checker = DAXHealthChecker()
        measures = [{"name": "Total Sales", "expression": "SUM(Sales[Amount])"}]
        results = checker.check(measures)
        assert results[0]["health"] == "healthy"

    def test_check_antipattern(self):
        from pbi_import.dax_health_checker import DAXHealthChecker
        checker = DAXHealthChecker()
        measures = [{"name": "Bad", "expression": 'FORMAT(Sales[Date], "YYYY-MM-DD")'}]
        results = checker.check(measures)
        assert len(results[0]["issues"]) >= 1

    def test_deprecated(self):
        from pbi_import.dax_health_checker import DAXHealthChecker
        checker = DAXHealthChecker()
        measures = [{"name": "Old", "expression": "EARLIER(Sales[Amount])"}]
        results = checker.check(measures)
        assert any(i["type"] == "deprecated" for i in results[0]["issues"])


class TestModelSplitter:
    def test_analyse(self):
        from pbi_import.model_splitter import ModelSplitter
        ms = ModelSplitter()
        catalog = [
            {"Name": "R1", "Type": "PowerBIReport", "DataSetReference": "DS1"},
            {"Name": "R2", "Type": "PowerBIReport", "DataSetReference": "DS1"},
            {"Name": "R3", "Type": "PowerBIReport", "DataSetReference": "DS2"},
        ]
        result = ms.analyse(catalog)
        assert result["summary"]["split_recommended"] >= 1


class TestCompositeModelPlanner:
    def test_plan(self):
        from pbi_import.composite_model_planner import CompositeModelPlanner
        planner = CompositeModelPlanner()
        catalog = [
            {"Name": "R1", "Type": "PowerBIReport", "DataSources": [
                {"Name": "SQL", "DataSourceType": "Sql"},
                {"Name": "Azure", "DataSourceType": "AzureSqlDatabase"},
            ]},
        ]
        result = planner.plan(catalog)
        assert result["summary"]["composite_candidates"] >= 1


class TestCalcGroupMigrator:
    def test_detect(self):
        from pbi_import.calc_group_migrator import CalcGroupMigrator
        migrator = CalcGroupMigrator()
        models = [
            {"name": "Model1", "tables": [
                {"name": "TimeCalc", "calculationGroup": {
                    "precedence": 1,
                    "calculationItems": [
                        {"name": "YTD", "expression": "TOTALYTD(...)"},
                    ],
                }},
            ]},
        ]
        results = migrator.detect(models)
        assert len(results) == 1
        assert results[0]["total_items"] == 1

    def test_generate_tmsl(self):
        from pbi_import.calc_group_migrator import CalcGroupMigrator
        migrator = CalcGroupMigrator()
        info = {
            "dataset_name": "DS1",
            "calculation_groups": [{
                "table_name": "CalcTable",
                "precedence": 0,
                "items": [{"name": "YTD", "expression": "TOTALYTD(...)", "format_string": ""}],
            }],
        }
        tmsl = migrator.generate_tmsl(info)
        parsed = json.loads(tmsl)
        assert "createOrReplace" in parsed


class TestFieldParameterCreator:
    def test_detect(self):
        from pbi_import.field_parameter_creator import FieldParameterCreator
        fpc = FieldParameterCreator()
        visuals = [
            {"page": "P1", "type": "lineChart", "fields": [
                {"role": "axis", "column": "Date"},
                {"role": "values", "measure": "Revenue"},
            ]},
            {"page": "P1", "type": "clusteredBarChart", "fields": [
                {"role": "axis", "column": "Region"},
                {"role": "values", "measure": "Cost"},
                {"role": "values", "measure": "Profit"},
            ]},
        ]
        candidates = fpc.detect(visuals)
        # Should detect axis parameter (Date, Region)
        assert len(candidates) >= 1


# ── v3.0 Fabric-Native Pipeline ────────────────────────────────────────

class TestFabricPublisher:
    def test_publish_dry_run(self):
        from pbi_import.deploy.fabric_publisher import FabricPublisher
        pub = FabricPublisher(None)
        result = pub.publish_item("ws-1", "Report1", "Report", dry_run=True)
        assert result["displayName"] == "Report1"


class TestOneLakeMigrator:
    def test_upload_file_not_found(self):
        from pbi_import.deploy.onelake_migrator import OneLakeMigrator
        migrator = OneLakeMigrator(None)
        result = migrator.upload_file("ws", "item", "/nonexistent", "dest")
        assert result["status"] == "error"

    def test_upload_dry_run(self):
        from pbi_import.deploy.onelake_migrator import OneLakeMigrator
        migrator = OneLakeMigrator(None)
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test data")
            f.flush()
            result = migrator.upload_file("ws", "item", f.name, "dest", dry_run=True)
        os.unlink(f.name)
        assert result["status"] == "dry_run"


class TestFabricNotebookGen:
    def test_generate_data_copy(self):
        from pbi_import.deploy.fabric_notebook_gen import FabricNotebookGen
        gen = FabricNotebookGen()
        nb = gen.generate_data_copy_notebook("jdbc:...", "lh1", ["t1", "t2"])
        assert nb["nbformat"] == 4
        assert len(nb["cells"]) >= 2

    def test_save(self):
        from pbi_import.deploy.fabric_notebook_gen import FabricNotebookGen
        gen = FabricNotebookGen()
        nb = gen.generate_data_copy_notebook("jdbc:...", "lh1", ["t1"])
        with tempfile.TemporaryDirectory() as td:
            path = gen.save(td, nb, "test_nb")
            assert path.exists()


class TestDataflowGen2:
    def test_generate(self):
        from pbi_import.deploy.dataflow_gen2 import DataflowGen2
        gen = DataflowGen2()
        ds = [
            {"Name": "ds1", "ConnectionString": "Server=A;Database=B", "DataSourceType": "Sql"},
        ]
        result = gen.generate(ds, "lh1", "ws-1")
        assert len(result) == 1
        assert "DF_ds1" == result[0]["displayName"]


class TestFabricScaler:
    def test_assess(self):
        from pbi_import.deploy.fabric_scaler import FabricScaler
        scaler = FabricScaler()
        catalog = [
            {"Type": "PowerBIReport", "Name": "R1", "Size": 100 * 1024 * 1024},
            {"Type": "Report", "Name": "R2", "Size": 50 * 1024 * 1024},
        ]
        result = scaler.assess(catalog)
        assert result["recommended_sku"] is not None
        assert result["workload"]["reports"] == 1


# ── v3.1 Multi-Source Federation ────────────────────────────────────────

class TestSSRSClient:
    def test_parse_catalog_items(self):
        from pbirs_export.ssrs_client import SSRSClient
        items = SSRSClient._parse_catalog_items("<root><CatalogItem><Name>R1</Name></CatalogItem></root>")
        assert len(items) >= 1

    def test_test_connection_no_client(self):
        from pbirs_export.ssrs_client import SSRSClient

        class FakeClient:
            def get(self, url):
                raise ConnectionError("no server")
            def post_xml(self, url, body):
                raise ConnectionError("no server")

        client = SSRSClient("http://localhost/reports", FakeClient())
        result = client.test_connection()
        assert result["status"] == "failed"


class TestBatchOrchestrator:
    def test_plan(self):
        from pbirs_export.batch_orchestrator import BatchOrchestrator
        with tempfile.TemporaryDirectory() as td:
            bo = BatchOrchestrator(td)
            servers = [
                {"name": "S1", "url": "http://s1/reports", "priority": "high"},
                {"name": "S2", "url": "http://s2/reports", "priority": "low"},
            ]
            plan = bo.plan(servers)
            assert plan["total_servers"] == 2
            # High priority should be first
            assert plan["batch_plan"][0]["server_name"] == "S1"

    def test_execute_dry_run(self):
        from pbirs_export.batch_orchestrator import BatchOrchestrator
        with tempfile.TemporaryDirectory() as td:
            bo = BatchOrchestrator(td)
            plan = bo.plan([{"name": "S1", "url": "http://s1"}])
            result = bo.execute_sequential(plan, None, None, dry_run=True)
            assert result["summary"]["dry_run"] == 1


class TestDeduplicator:
    def test_scan(self):
        from pbirs_export.deduplicator import Deduplicator
        dedup = Deduplicator()
        catalogs = {
            "server1": [
                {"Name": "R1", "Type": "PowerBIReport", "Size": 100, "ModifiedDate": "2024-01-01"},
            ],
            "server2": [
                {"Name": "R1", "Type": "PowerBIReport", "Size": 100, "ModifiedDate": "2024-06-01"},
                {"Name": "R2", "Type": "Report", "Size": 200, "ModifiedDate": "2024-03-01"},
            ],
        }
        result = dedup.scan(catalogs)
        assert result["summary"]["servers_scanned"] == 2
        assert result["summary"]["items_deduplicated"] >= 1


class TestMigrationRegistry:
    def test_register_and_query(self):
        from pbi_import.migration_registry import MigrationRegistry
        import uuid
        db_path = os.path.join(tempfile.gettempdir(), f"test_reg_{uuid.uuid4().hex[:8]}.db")
        try:
            reg = MigrationRegistry(db_path)
            row_id = reg.register_item("1", "R1", "PowerBIReport", "server1", "/R1")
            assert row_id > 0
            reg.update_status(row_id, "completed", "ws-1", "target-1")
            items = reg.query(status="completed")
            assert len(items) == 1
        finally:
            try:
                os.unlink(db_path)
            except OSError:
                pass

    def test_summary(self):
        from pbi_import.migration_registry import MigrationRegistry
        import uuid
        db_path = os.path.join(tempfile.gettempdir(), f"test_reg_{uuid.uuid4().hex[:8]}.db")
        try:
            reg = MigrationRegistry(db_path)
            reg.register_item("1", "R1", "Report", "s1", "/R1")
            s = reg.summary()
            assert s["total_items"] == 1
        finally:
            try:
                os.unlink(db_path)
            except OSError:
                pass


# ── v3.3 Validation & Testing ──────────────────────────────────────────

class TestVisualRegression:
    def test_compare_identical(self):
        from pbi_import.visual_regression import VisualRegression
        vr = VisualRegression()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f:
            f.write(b"fake image data")
            f.flush()
            result = vr.compare_files(f.name, f.name)
        os.unlink(f.name)
        assert result["status"] == "pass"

    def test_compare_missing(self):
        from pbi_import.visual_regression import VisualRegression
        vr = VisualRegression()
        result = vr.compare_files("/nonexistent", "/also_nonexistent")
        assert result["status"] == "error"


class TestDataValidator:
    def test_validate_row_counts(self):
        from pbi_import.data_validator import DataValidator
        dv = DataValidator()
        result = dv.validate_row_counts(
            {"t1": 100, "t2": 200},
            {"t1": 100, "t2": 195},
        )
        assert result["summary"]["matched"] == 1
        assert result["summary"]["mismatched"] == 1

    def test_validate_schema(self):
        from pbi_import.data_validator import DataValidator
        dv = DataValidator()
        result = dv.validate_schema(
            {"t1": [{"name": "a", "type": "int"}, {"name": "b", "type": "str"}]},
            {"t1": [{"name": "a", "type": "int"}]},
        )
        assert result["summary"]["mismatched"] == 1


class TestUATGenerator:
    def test_generate_test_plan(self):
        from pbi_import.uat_generator import UATGenerator
        gen = UATGenerator()
        catalog = [
            {"Name": "R1", "Type": "PowerBIReport"},
            {"Name": "R2", "Type": "Report"},
        ]
        plan = gen.generate_test_plan(catalog)
        assert plan["test_plan"]["total_test_cases"] > 0

    def test_generate_report(self):
        from pbi_import.uat_generator import UATGenerator
        gen = UATGenerator()
        plan = gen.generate_test_plan([{"Name": "R1", "Type": "PowerBIReport"}])
        test_ids = [tc["test_id"] for tc in plan["test_plan"]["test_cases"]]
        results = [{"test_id": test_ids[0], "status": "pass"}]
        report = gen.generate_report(plan, results)
        assert report["summary"]["passed"] >= 1


class TestPerfBenchmark:
    def test_compare(self):
        from pbi_import.perf_benchmark import PerfBenchmark
        pb = PerfBenchmark()
        before = [{"name": "R1", "duration_seconds": 10}]
        after = [{"name": "R1", "duration_seconds": 9}]
        result = pb.compare(before, after)
        assert result["summary"]["improved"] == 1

    def test_compare_degraded(self):
        from pbi_import.perf_benchmark import PerfBenchmark
        pb = PerfBenchmark()
        before = [{"name": "R1", "duration_seconds": 10}]
        after = [{"name": "R1", "duration_seconds": 15}]
        result = pb.compare(before, after)
        assert result["summary"]["degraded"] == 1


class TestSubscriptionVerifier:
    def test_verify(self):
        from pbi_import.subscription_verifier import SubscriptionVerifier
        sv = SubscriptionVerifier()
        subs = [
            {"Id": "1", "Report": "/R1", "DeliveryExtension": "Email",
             "DeliverySettings": {"TO": "user@test.com"}, "Schedule": "daily"},
            {"Id": "2", "Report": "/R2", "DeliveryExtension": "FileShare",
             "DeliverySettings": {}, "Schedule": "weekly"},
        ]
        result = sv.verify(subs)
        assert result["summary"]["supported"] == 1
        assert result["summary"]["unsupported"] == 1


# ── v3.4 Operations & Observability ────────────────────────────────────

class TestMetricsExporter:
    def test_render(self):
        from pbi_import.metrics_exporter import MetricsExporter
        me = MetricsExporter()
        me.gauge("test_metric", 42, "A test metric")
        output = me.render()
        assert "test_metric 42" in output
        assert "# HELP" in output

    def test_from_results(self):
        from pbi_import.metrics_exporter import MetricsExporter
        me = MetricsExporter()
        me.from_migration_results({"summary": {"total_items": 10, "completed": 8, "failed": 2}})
        output = me.render()
        assert "migration_items_total" in output


class TestNotifier:
    def test_notify_dry_run(self):
        from pbi_import.notifier import Notifier
        n = Notifier(teams_webhook="http://fake", slack_webhook="http://fake")
        result = n.notify("Test", "Hello", dry_run=True)
        assert result["results"]["teams"] == "dry_run"
        assert result["results"]["slack"] == "dry_run"

    def test_no_webhooks(self):
        from pbi_import.notifier import Notifier
        n = Notifier()
        result = n.notify("Test", "Hello")
        assert "no_webhooks_configured" in str(result)


class TestCostEstimator:
    def test_estimate(self):
        from pbi_import.cost_estimator import CostEstimator
        ce = CostEstimator()
        catalog = [
            {"Type": "PowerBIReport", "Size": 500 * 1024 * 1024},
            {"Type": "Report", "Size": 10 * 1024 * 1024},
        ]
        result = ce.estimate(catalog, user_count=50)
        assert result["total_monthly_usd"] > 0
        assert result["capacity"]["needs_premium"] is True


class TestScheduler:
    def test_add_and_status(self):
        from pbi_import.scheduler import Scheduler
        s = Scheduler()
        s.add_job("test", lambda: None, 60)
        status = s.status()
        assert "test" in status["jobs"]

    def test_run_once(self):
        from pbi_import.scheduler import Scheduler
        s = Scheduler()
        called = []
        s.add_job("j1", lambda: called.append(1), 60)
        result = s.run_once("j1")
        assert result["status"] == "completed"
        assert len(called) == 1


class TestMonitorIntegration:
    def test_log_and_flush_dry(self):
        from pbi_import.monitor_integration import MonitorIntegration
        mi = MonitorIntegration()
        mi.log_event("test", item_name="R1", status="ok")
        result = mi.flush(dry_run=True)
        assert result["events"] == 1


# ── v4.0 Platform & Ecosystem ──────────────────────────────────────────

class TestPluginManager:
    def test_add_hook(self):
        from pbi_import.plugin_manager import PluginManager
        pm = PluginManager()
        pm.add_hook("pre_assessment", lambda ctx: ctx, name="test")
        hooks = pm.list_hooks()
        assert hooks["pre_assessment"] == 1

    def test_execute_hooks(self):
        from pbi_import.plugin_manager import PluginManager
        pm = PluginManager()
        results_list = []
        pm.add_hook("post_export", lambda ctx: results_list.append(ctx), name="collector")
        result = pm.execute_hooks("post_export", {"phase": "export"})
        assert result["hooks_executed"] == 1


class TestAPIServer:
    def test_create_server(self):
        from pbi_import.api_server import MigrationAPIServer
        # Just verify instantiation (don't bind to port)
        server = MigrationAPIServer("127.0.0.1", 0)  # port 0 = OS-assigned
        assert server.state["status"]["status"] == "idle"
        server.server_close()


class TestPipelineTemplates:
    def test_github_actions(self):
        from pbi_import.pipeline_templates import PipelineTemplates
        pt = PipelineTemplates()
        yaml = pt.generate_github_actions("https://pbirs.local/reports")
        assert "PBIRS_SERVER" in yaml
        assert "actions/checkout" in yaml

    def test_azure_devops(self):
        from pbi_import.pipeline_templates import PipelineTemplates
        pt = PipelineTemplates()
        yaml = pt.generate_azure_devops("https://pbirs.local/reports")
        assert "PBIRS_SERVER" in yaml
        assert "UsePythonVersion" in yaml

    def test_save(self):
        from pbi_import.pipeline_templates import PipelineTemplates
        pt = PipelineTemplates()
        with tempfile.TemporaryDirectory() as td:
            path = pt.save(td, "github", server_url="https://pbirs.local")
            assert path.exists()
