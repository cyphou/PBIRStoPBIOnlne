"""Tests for MappingGenerator."""

import csv
import pytest
from pbirs_export.mapping_generator import MappingGenerator


@pytest.fixture
def catalog():
    return {
        "items": [
            {
                "Id": "1", "Name": "Sales Dashboard",
                "Path": "/Finance/Sales Dashboard", "Type": "PowerBIReport",
                "datasources": [{"ConnectionString": "Data Source=sql01.corp.local;Initial Catalog=SalesDB", "DataSourceType": "SQL"}],
                "policies": [{"GroupUserName": "DOMAIN\\Finance", "Roles": [{"Name": "Browser"}]}],
            },
            {
                "Id": "2", "Name": "Invoice Report",
                "Path": "/Finance/Invoice Report", "Type": "Report",
                "datasources": [{"ConnectionString": "Data Source=oracle01;Initial Catalog=InvoiceDB", "DataSourceType": "Oracle"}],
                "policies": [{"GroupUserName": "user@corp.com", "Roles": [{"Name": "Publisher"}]}],
            },
            {
                "Id": "3", "Name": "HR Summary",
                "Path": "/HR/HR Summary", "Type": "PowerBIReport",
                "datasources": [{"ConnectionString": "Data Source=myserver.database.windows.net;Initial Catalog=HrDB", "DataSourceType": "SQL"}],
                "policies": [{"GroupUserName": "DOMAIN\\HR", "Roles": [{"Name": "Content Manager"}]}],
            },
        ],
        "folders": [
            {"path": "/Finance"},
            {"path": "/HR"},
        ],
    }


@pytest.fixture
def permissions():
    return {
        "system_policies": [
            {"GroupUserName": "BUILTIN\\Administrators", "Roles": [{"Name": "System Administrator"}]},
        ],
        "item_policies": [
            {
                "item_path": "/Finance/Sales Dashboard",
                "policies": [{"GroupUserName": "DOMAIN\\Finance", "Roles": [{"Name": "Browser"}]}],
            },
            {
                "item_path": "/Finance/Invoice Report",
                "policies": [{"GroupUserName": "user@corp.com", "Roles": [{"Name": "Publisher"}]}],
            },
            {
                "item_path": "/HR/HR Summary",
                "policies": [{"GroupUserName": "DOMAIN\\HR", "Roles": [{"Name": "Content Manager"}]}],
            },
        ],
    }


@pytest.fixture
def datasources():
    return {
        "shared_datasources": [
            {"Name": "SharedSQL", "Path": "/DataSources/SharedSQL",
             "ConnectionString": "Data Source=shared-sql.corp.local;Initial Catalog=SharedDB",
             "DataSourceType": "SQL"},
        ],
        "embedded_datasources": [
            {"item_name": "Sales Dashboard", "item_path": "/Finance/Sales Dashboard",
             "item_type": "PowerBIReport",
             "datasource": {"ConnectionString": "Data Source=sql01.corp.local;Initial Catalog=SalesDB", "DataSourceType": "SQL"}},
            {"item_name": "Invoice Report", "item_path": "/Finance/Invoice Report",
             "item_type": "Report",
             "datasource": {"ConnectionString": "Data Source=oracle01;Initial Catalog=InvoiceDB", "DataSourceType": "Oracle"}},
            {"item_name": "HR Summary", "item_path": "/HR/HR Summary",
             "item_type": "PowerBIReport",
             "datasource": {"ConnectionString": "Data Source=myserver.database.windows.net;Initial Catalog=HrDB", "DataSourceType": "SQL"}},
        ],
    }


def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class TestMappingGenerator:

    def test_generate_all_creates_three_files(self, catalog, permissions, datasources, tmp_path):
        gen = MappingGenerator(catalog, permissions, datasources)
        paths = gen.generate_all(str(tmp_path))
        assert set(paths.keys()) == {"folders", "users", "connections"}
        for p in paths.values():
            assert p.exists()

    # -- Folders CSV --

    def test_folders_csv_content(self, catalog, permissions, datasources, tmp_path):
        gen = MappingGenerator(catalog, permissions, datasources)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["folders"])
        folder_paths = {r["folder_path"] for r in rows}
        assert "/Finance" in folder_paths
        assert "/HR" in folder_paths

    def test_folders_csv_item_count(self, catalog, permissions, datasources, tmp_path):
        gen = MappingGenerator(catalog, permissions, datasources)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["folders"])
        finance = next(r for r in rows if r["folder_path"] == "/Finance")
        assert int(finance["item_count"]) == 2

    def test_folders_csv_has_target_column(self, catalog, permissions, datasources, tmp_path):
        gen = MappingGenerator(catalog, permissions, datasources)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["folders"])
        assert "target_workspace" in rows[0]

    # -- Users CSV --

    def test_users_csv_content(self, catalog, permissions, datasources, tmp_path):
        gen = MappingGenerator(catalog, permissions, datasources)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["users"])
        names = {r["pbirs_principal"] for r in rows}
        assert "DOMAIN\\Finance" in names
        assert "user@corp.com" in names
        assert "DOMAIN\\HR" in names

    def test_users_csv_type_classification(self, catalog, permissions, datasources, tmp_path):
        gen = MappingGenerator(catalog, permissions, datasources)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["users"])
        ad_user = next(r for r in rows if r["pbirs_principal"] == "DOMAIN\\Finance")
        assert ad_user["type"] == "ad_account"
        email_user = next(r for r in rows if r["pbirs_principal"] == "user@corp.com")
        assert email_user["type"] == "email"

    def test_users_csv_suggested_role(self, catalog, permissions, datasources, tmp_path):
        gen = MappingGenerator(catalog, permissions, datasources)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["users"])
        admin = next(r for r in rows if r["pbirs_principal"] == "DOMAIN\\HR")
        assert admin["target_pbi_role"] == "Admin"
        viewer = next(r for r in rows if r["pbirs_principal"] == "DOMAIN\\Finance")
        assert viewer["target_pbi_role"] == "Viewer"

    def test_users_csv_has_target_column(self, catalog, permissions, datasources, tmp_path):
        gen = MappingGenerator(catalog, permissions, datasources)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["users"])
        assert "target_azure_ad" in rows[0]

    # -- Connections CSV --

    def test_connections_csv_content(self, catalog, permissions, datasources, tmp_path):
        gen = MappingGenerator(catalog, permissions, datasources)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["connections"])
        names = {r["report_name"] for r in rows}
        assert "Sales Dashboard" in names
        assert "Invoice Report" in names
        assert "[Shared] SharedSQL" in names

    def test_connections_csv_server_extraction(self, catalog, permissions, datasources, tmp_path):
        gen = MappingGenerator(catalog, permissions, datasources)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["connections"])
        sales = next(r for r in rows if r["report_name"] == "Sales Dashboard")
        assert sales["server_name"] == "sql01.corp.local"
        assert sales["database_name"] == "SalesDB"

    def test_connections_csv_gateway_detection(self, catalog, permissions, datasources, tmp_path):
        gen = MappingGenerator(catalog, permissions, datasources)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["connections"])
        # On-prem SQL → needs gateway
        sales = next(r for r in rows if r["report_name"] == "Sales Dashboard")
        assert sales["needs_gateway"] == "yes"
        # Azure SQL → no gateway
        hr = next(r for r in rows if r["report_name"] == "HR Summary")
        assert hr["needs_gateway"] == "no"

    def test_connections_csv_has_target_columns(self, catalog, permissions, datasources, tmp_path):
        gen = MappingGenerator(catalog, permissions, datasources)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["connections"])
        assert "target_gateway_id" in rows[0]
        assert "target_datasource_id" in rows[0]

    def test_connections_deduplication(self, catalog, permissions, datasources, tmp_path):
        # Add duplicate connection
        datasources["embedded_datasources"].append(
            datasources["embedded_datasources"][0].copy()
        )
        gen = MappingGenerator(catalog, permissions, datasources)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["connections"])
        sales_rows = [r for r in rows if r["report_name"] == "Sales Dashboard"]
        assert len(sales_rows) == 1

    # -- Edge cases --

    def test_empty_catalog(self, tmp_path):
        gen = MappingGenerator(
            {"items": [], "folders": []},
            {"system_policies": [], "item_policies": []},
            {"shared_datasources": [], "embedded_datasources": []},
        )
        paths = gen.generate_all(str(tmp_path))
        for p in paths.values():
            rows = _read_csv(p)
            assert len(rows) == 0

    def test_with_security_data(self, catalog, permissions, datasources, tmp_path):
        security = {
            "principals": [
                {"name": "DOMAIN\\Finance", "type": "ad_account", "domain": "DOMAIN", "ssrs_roles": ["Browser"]},
                {"name": "cloud@contoso.com", "type": "email", "domain": "", "ssrs_roles": ["Publisher"]},
            ],
            "effective_permissions": [
                {"principal": "DOMAIN\\Finance", "item_path": "/Finance/Sales", "ssrs_role": "Browser"},
                {"principal": "DOMAIN\\Finance", "item_path": "/Finance/Invoice", "ssrs_role": "Browser"},
            ],
        }
        gen = MappingGenerator(catalog, permissions, datasources, security=security)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["users"])
        names = {r["pbirs_principal"] for r in rows}
        assert "cloud@contoso.com" in names


class TestParseConnectionString:

    def test_standard_sql(self):
        server, db = MappingGenerator._parse_connection_string(
            "Data Source=sql01.corp.local;Initial Catalog=SalesDB"
        )
        assert server == "sql01.corp.local"
        assert db == "SalesDB"

    def test_server_database(self):
        server, db = MappingGenerator._parse_connection_string(
            "Server=myhost;Database=mydb"
        )
        assert server == "myhost"
        assert db == "mydb"

    def test_empty(self):
        server, db = MappingGenerator._parse_connection_string("")
        assert server == ""
        assert db == ""

    def test_host_dbname(self):
        server, db = MappingGenerator._parse_connection_string(
            "Host=pgserver;DBName=analytics"
        )
        assert server == "pgserver"
        assert db == "analytics"


class TestNeedsGateway:

    def test_onprem_sql(self):
        assert MappingGenerator._needs_gateway(
            "Data Source=sql01.corp.local;Initial Catalog=DB"
        ) is True

    def test_azure_sql(self):
        assert MappingGenerator._needs_gateway(
            "Data Source=myserver.database.windows.net;Initial Catalog=DB"
        ) is False

    def test_no_server(self):
        assert MappingGenerator._needs_gateway("some-random-string") is False
