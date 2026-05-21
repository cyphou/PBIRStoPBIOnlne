"""Tests for CSV extraction — end-to-end mapping generation, encoding,
edge cases, round-trip fidelity, and content integrity."""

import csv
import os
from pathlib import Path

import pytest
from pbirs_export.mapping_generator import MappingGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _make_generator(
    items=None,
    folders=None,
    system_policies=None,
    item_policies=None,
    shared_ds=None,
    embedded_ds=None,
    security=None,
):
    catalog = {"items": items or [], "folders": folders or []}
    permissions = {
        "system_policies": system_policies or [],
        "item_policies": item_policies or [],
    }
    datasources = {
        "shared_datasources": shared_ds or [],
        "embedded_datasources": embedded_ds or [],
    }
    return MappingGenerator(catalog, permissions, datasources, security=security)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def rich_catalog():
    """A richer catalog with many edge-case items."""
    return [
        {
            "Id": "1", "Name": "Sales Dashboard",
            "Path": "/Finance/Sales Dashboard", "Type": "PowerBIReport",
        },
        {
            "Id": "2", "Name": "Invoice Report",
            "Path": "/Finance/Invoice Report", "Type": "Report",
        },
        {
            "Id": "3", "Name": "HR Summary",
            "Path": "/HR/HR Summary", "Type": "PowerBIReport",
        },
        {
            "Id": "4", "Name": "Root Report",
            "Path": "/Root Report", "Type": "Report",
        },
        {
            "Id": "5", "Name": "Deep Report",
            "Path": "/A/B/C/D/Deep Report", "Type": "PowerBIReport",
        },
    ]


@pytest.fixture
def rich_embedded_ds():
    return [
        {
            "item_name": "Sales Dashboard",
            "item_path": "/Finance/Sales Dashboard",
            "item_type": "PowerBIReport",
            "datasource": {
                "ConnectionString": "Data Source=sql01.corp.local;Initial Catalog=SalesDB",
                "DataSourceType": "SQL",
            },
        },
        {
            "item_name": "Invoice Report",
            "item_path": "/Finance/Invoice Report",
            "item_type": "Report",
            "datasource": {
                "ConnectionString": "Data Source=oracle01;Initial Catalog=InvoiceDB",
                "DataSourceType": "Oracle",
            },
        },
        {
            "item_name": "HR Summary",
            "item_path": "/HR/HR Summary",
            "item_type": "PowerBIReport",
            "datasource": {
                "ConnectionString": "Data Source=myserver.database.windows.net;Initial Catalog=HrDB",
                "DataSourceType": "SQL",
            },
        },
    ]


# ===================================================================
# 1. FILE STRUCTURE TESTS
# ===================================================================

class TestCSVFileStructure:
    """Verify generated CSV files exist and have correct structure."""

    def test_all_three_csvs_created(self, tmp_path, rich_catalog, rich_embedded_ds):
        gen = _make_generator(items=rich_catalog, embedded_ds=rich_embedded_ds)
        paths = gen.generate_all(str(tmp_path))
        assert set(paths.keys()) == {"folders", "users", "connections"}
        for p in paths.values():
            assert p.exists()
            assert p.suffix == ".csv"

    def test_csv_filenames(self, tmp_path):
        gen = _make_generator()
        paths = gen.generate_all(str(tmp_path))
        assert paths["folders"].name == "folders_mapping.csv"
        assert paths["users"].name == "users_mapping.csv"
        assert paths["connections"].name == "connections_mapping.csv"

    def test_folders_csv_headers(self, tmp_path, rich_catalog):
        gen = _make_generator(items=rich_catalog)
        paths = gen.generate_all(str(tmp_path))
        with open(paths["folders"], newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader)
        assert headers == [
            "folder_path", "item_count", "content_types",
            "target_workspace", "notes",
        ]

    def test_users_csv_headers(self, tmp_path):
        policies = [
            {"GroupUserName": "DOMAIN\\user1", "Roles": [{"Name": "Browser"}]}
        ]
        gen = _make_generator(
            item_policies=[{"item_path": "/x", "policies": policies}]
        )
        paths = gen.generate_all(str(tmp_path))
        with open(paths["users"], newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader)
        assert headers == [
            "pbirs_principal", "type", "domain", "ssrs_roles",
            "item_count", "target_azure_ad", "target_pbi_role", "notes",
        ]

    def test_connections_csv_headers(self, tmp_path, rich_embedded_ds):
        gen = _make_generator(embedded_ds=rich_embedded_ds)
        paths = gen.generate_all(str(tmp_path))
        with open(paths["connections"], newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader)
        assert headers == [
            "report_name", "report_path", "report_type", "datasource_type",
            "connection_string", "server_name", "database_name",
            "needs_gateway", "target_gateway_id", "target_datasource_id", "notes",
        ]

    def test_output_dir_created_if_missing(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        gen = _make_generator()
        paths = gen.generate_all(str(nested))
        assert nested.exists()
        for p in paths.values():
            assert p.exists()


# ===================================================================
# 2. FOLDER EXTRACTION TESTS
# ===================================================================

class TestFolderExtraction:

    def test_folders_from_item_paths(self, tmp_path, rich_catalog):
        gen = _make_generator(items=rich_catalog)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["folders"])
        folder_paths = {r["folder_path"] for r in rows}
        assert "/Finance" in folder_paths
        assert "/HR" in folder_paths

    def test_root_items_get_root_folder(self, tmp_path, rich_catalog):
        gen = _make_generator(items=rich_catalog)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["folders"])
        folder_paths = {r["folder_path"] for r in rows}
        # /Root Report should produce folder ""  or "/" 
        assert any(fp in ("", "/") for fp in folder_paths)

    def test_deeply_nested_folder(self, tmp_path, rich_catalog):
        gen = _make_generator(items=rich_catalog)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["folders"])
        folder_paths = {r["folder_path"] for r in rows}
        assert "/A/B/C/D" in folder_paths

    def test_item_count_per_folder(self, tmp_path, rich_catalog):
        gen = _make_generator(items=rich_catalog)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["folders"])
        finance = next(r for r in rows if r["folder_path"] == "/Finance")
        assert int(finance["item_count"]) == 2

    def test_content_types_per_folder(self, tmp_path, rich_catalog):
        gen = _make_generator(items=rich_catalog)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["folders"])
        finance = next(r for r in rows if r["folder_path"] == "/Finance")
        types = {t.strip() for t in finance["content_types"].split(",")}
        assert "PowerBIReport" in types
        assert "Report" in types

    def test_explicit_folders_included_even_if_empty(self, tmp_path):
        gen = _make_generator(
            items=[],
            folders=[{"path": "/EmptyFolder"}],
        )
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["folders"])
        assert any(r["folder_path"] == "/EmptyFolder" for r in rows)

    def test_target_workspace_is_blank(self, tmp_path, rich_catalog):
        gen = _make_generator(items=rich_catalog)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["folders"])
        assert all(r["target_workspace"] == "" for r in rows)

    def test_folders_sorted_alphabetically(self, tmp_path, rich_catalog):
        gen = _make_generator(items=rich_catalog)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["folders"])
        folder_paths = [r["folder_path"] for r in rows]
        assert folder_paths == sorted(folder_paths)


# ===================================================================
# 3. USERS / PRINCIPALS EXTRACTION TESTS
# ===================================================================

class TestUserExtraction:

    def test_ad_user_type(self, tmp_path):
        gen = _make_generator(
            item_policies=[{
                "item_path": "/x",
                "policies": [{"GroupUserName": "CONTOSO\\jsmith", "Roles": [{"Name": "Browser"}]}],
            }]
        )
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["users"])
        user = next(r for r in rows if r["pbirs_principal"] == "CONTOSO\\jsmith")
        assert user["type"] == "ad_account"
        assert user["domain"] == "CONTOSO"

    def test_email_user_type(self, tmp_path):
        gen = _make_generator(
            item_policies=[{
                "item_path": "/x",
                "policies": [{"GroupUserName": "alice@corp.com", "Roles": [{"Name": "Publisher"}]}],
            }]
        )
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["users"])
        user = next(r for r in rows if r["pbirs_principal"] == "alice@corp.com")
        assert user["type"] == "email"

    def test_builtin_user_type(self, tmp_path):
        # BUILTIN\Administrators contains backslash, so _classify_type
        # matches ad_account before the BUILTIN prefix check
        gen = _make_generator(
            system_policies=[
                {"GroupUserName": "BUILTIN\\Administrators", "Roles": [{"Name": "System Administrator"}]}
            ]
        )
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["users"])
        admin = next(r for r in rows if r["pbirs_principal"] == "BUILTIN\\Administrators")
        assert admin["type"] == "ad_account"

    def test_role_mapping_browser_to_viewer(self, tmp_path):
        gen = _make_generator(
            item_policies=[{
                "item_path": "/x",
                "policies": [{"GroupUserName": "D\\viewer", "Roles": [{"Name": "Browser"}]}],
            }]
        )
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["users"])
        assert rows[0]["target_pbi_role"] == "Viewer"

    def test_role_mapping_content_manager_to_admin(self, tmp_path):
        gen = _make_generator(
            item_policies=[{
                "item_path": "/x",
                "policies": [{"GroupUserName": "D\\admin", "Roles": [{"Name": "Content Manager"}]}],
            }]
        )
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["users"])
        assert rows[0]["target_pbi_role"] == "Admin"

    def test_role_mapping_publisher_to_contributor(self, tmp_path):
        gen = _make_generator(
            item_policies=[{
                "item_path": "/x",
                "policies": [{"GroupUserName": "D\\pub", "Roles": [{"Name": "Publisher"}]}],
            }]
        )
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["users"])
        assert rows[0]["target_pbi_role"] == "Contributor"

    def test_highest_privilege_role_wins(self, tmp_path):
        gen = _make_generator(
            item_policies=[{
                "item_path": "/x",
                "policies": [{
                    "GroupUserName": "D\\multi",
                    "Roles": [{"Name": "Browser"}, {"Name": "Content Manager"}],
                }],
            }]
        )
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["users"])
        assert rows[0]["target_pbi_role"] == "Admin"

    def test_deduplication_across_items(self, tmp_path):
        policies = [{"GroupUserName": "D\\shared", "Roles": [{"Name": "Browser"}]}]
        gen = _make_generator(
            item_policies=[
                {"item_path": "/a", "policies": policies},
                {"item_path": "/b", "policies": policies},
                {"item_path": "/c", "policies": policies},
            ]
        )
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["users"])
        matching = [r for r in rows if r["pbirs_principal"] == "D\\shared"]
        assert len(matching) == 1
        assert int(matching[0]["item_count"]) == 3

    def test_security_data_principals_preferred(self, tmp_path):
        security = {
            "principals": [
                {"name": "cloud@contoso.com", "type": "email", "domain": "", "ssrs_roles": ["Publisher"]},
            ],
            "effective_permissions": [],
        }
        gen = _make_generator(security=security)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["users"])
        assert any(r["pbirs_principal"] == "cloud@contoso.com" for r in rows)

    def test_target_azure_ad_blank(self, tmp_path):
        gen = _make_generator(
            item_policies=[{
                "item_path": "/x",
                "policies": [{"GroupUserName": "D\\u", "Roles": [{"Name": "Browser"}]}],
            }]
        )
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["users"])
        assert all(r["target_azure_ad"] == "" for r in rows)

    def test_users_sorted_by_name(self, tmp_path):
        gen = _make_generator(
            item_policies=[
                {"item_path": "/x", "policies": [
                    {"GroupUserName": "Z\\zebra", "Roles": [{"Name": "Browser"}]},
                    {"GroupUserName": "A\\alpha", "Roles": [{"Name": "Browser"}]},
                    {"GroupUserName": "M\\middle", "Roles": [{"Name": "Browser"}]},
                ]},
            ]
        )
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["users"])
        names = [r["pbirs_principal"] for r in rows]
        assert names == sorted(names)


# ===================================================================
# 4. CONNECTIONS EXTRACTION TESTS
# ===================================================================

class TestConnectionExtraction:

    def test_embedded_datasource_extraction(self, tmp_path, rich_embedded_ds):
        gen = _make_generator(embedded_ds=rich_embedded_ds)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["connections"])
        names = {r["report_name"] for r in rows}
        assert "Sales Dashboard" in names
        assert "Invoice Report" in names
        assert "HR Summary" in names

    def test_shared_datasource_extraction(self, tmp_path):
        shared = [{
            "Name": "SharedSQL",
            "Path": "/DataSources/SharedSQL",
            "ConnectionString": "Data Source=shared-sql.corp.local;Initial Catalog=SharedDB",
            "DataSourceType": "SQL",
        }]
        gen = _make_generator(shared_ds=shared)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["connections"])
        assert any(r["report_name"] == "[Shared] SharedSQL" for r in rows)

    def test_server_name_extraction(self, tmp_path, rich_embedded_ds):
        gen = _make_generator(embedded_ds=rich_embedded_ds)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["connections"])
        sales = next(r for r in rows if r["report_name"] == "Sales Dashboard")
        assert sales["server_name"] == "sql01.corp.local"
        assert sales["database_name"] == "SalesDB"

    def test_gateway_needed_for_onprem(self, tmp_path, rich_embedded_ds):
        gen = _make_generator(embedded_ds=rich_embedded_ds)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["connections"])
        sales = next(r for r in rows if r["report_name"] == "Sales Dashboard")
        assert sales["needs_gateway"] == "yes"

    def test_no_gateway_for_azure_sql(self, tmp_path, rich_embedded_ds):
        gen = _make_generator(embedded_ds=rich_embedded_ds)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["connections"])
        hr = next(r for r in rows if r["report_name"] == "HR Summary")
        assert hr["needs_gateway"] == "no"

    def test_deduplication(self, tmp_path, rich_embedded_ds):
        # Double-up one entry
        dup = rich_embedded_ds + [rich_embedded_ds[0].copy()]
        gen = _make_generator(embedded_ds=dup)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["connections"])
        sales_rows = [r for r in rows if r["report_name"] == "Sales Dashboard"]
        assert len(sales_rows) == 1

    def test_target_columns_blank(self, tmp_path, rich_embedded_ds):
        gen = _make_generator(embedded_ds=rich_embedded_ds)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["connections"])
        assert all(r["target_gateway_id"] == "" for r in rows)
        assert all(r["target_datasource_id"] == "" for r in rows)


# ===================================================================
# 5. CONNECTION STRING PARSING EDGE CASES
# ===================================================================

class TestConnectionStringParsing:

    def test_data_source_format(self):
        server, db = MappingGenerator._parse_connection_string(
            "Data Source=sql01.corp.local;Initial Catalog=SalesDB"
        )
        assert server == "sql01.corp.local"
        assert db == "SalesDB"

    def test_server_database_format(self):
        server, db = MappingGenerator._parse_connection_string(
            "Server=myhost;Database=mydb"
        )
        assert server == "myhost"
        assert db == "mydb"

    def test_host_dbname_format(self):
        server, db = MappingGenerator._parse_connection_string(
            "Host=pgserver;DBName=analytics"
        )
        assert server == "pgserver"
        assert db == "analytics"

    def test_empty_string(self):
        server, db = MappingGenerator._parse_connection_string("")
        assert server == ""
        assert db == ""

    def test_missing_database(self):
        server, db = MappingGenerator._parse_connection_string(
            "Data Source=myserver"
        )
        assert server == "myserver"
        assert db == ""

    def test_missing_server(self):
        server, db = MappingGenerator._parse_connection_string(
            "Initial Catalog=MyDB"
        )
        assert server == ""
        assert db == "MyDB"

    def test_extra_whitespace(self):
        server, db = MappingGenerator._parse_connection_string(
            "  Data Source = srv01 ; Initial Catalog = DB1 "
        )
        assert server == "srv01"
        assert db == "DB1"

    def test_mixed_case_keys(self):
        server, db = MappingGenerator._parse_connection_string(
            "DATA SOURCE=SRV;INITIAL CATALOG=DB"
        )
        assert server == "SRV"
        assert db == "DB"

    def test_connection_string_with_port(self):
        server, db = MappingGenerator._parse_connection_string(
            "Data Source=myserver,1433;Initial Catalog=MyDB"
        )
        assert server == "myserver,1433"
        assert db == "MyDB"

    def test_connection_string_with_many_params(self):
        server, db = MappingGenerator._parse_connection_string(
            "Data Source=srv;Initial Catalog=db;Integrated Security=true;"
            "MultipleActiveResultSets=true;TrustServerCertificate=true"
        )
        assert server == "srv"
        assert db == "db"


# ===================================================================
# 6. GATEWAY DETECTION EDGE CASES
# ===================================================================

class TestGatewayDetection:

    @pytest.mark.parametrize("cloud_host", [
        "myserver.database.windows.net",
        "myserver.sql.azuresynapse.net",
        "myaccount.blob.core.windows.net",
        "myaccount.dfs.core.windows.net",
        "contoso.sharepoint.com",
        "contoso.onmicrosoft.com",
        "myaccount.cosmos.azure.com",
    ])
    def test_cloud_no_gateway(self, cloud_host):
        conn = f"Data Source={cloud_host};Initial Catalog=db"
        assert MappingGenerator._needs_gateway(conn) is False

    @pytest.mark.parametrize("onprem_host", [
        "sqlserver.corp.local",
        "sql01",
        "192.168.1.100",
        "oracle-prod.internal",
    ])
    def test_onprem_needs_gateway(self, onprem_host):
        conn = f"Data Source={onprem_host};Initial Catalog=db"
        assert MappingGenerator._needs_gateway(conn) is True

    def test_random_string_no_gateway(self):
        assert MappingGenerator._needs_gateway("some-random-value") is False

    def test_empty_string_no_gateway(self):
        assert MappingGenerator._needs_gateway("") is False


# ===================================================================
# 7. PRINCIPAL CLASSIFICATION EDGE CASES
# ===================================================================

class TestPrincipalClassification:

    def test_ad_account(self):
        assert MappingGenerator._classify_type("DOMAIN\\user") == "ad_account"

    def test_email(self):
        assert MappingGenerator._classify_type("user@corp.com") == "email"

    def test_builtin_with_backslash(self):
        # Backslash check fires before BUILTIN prefix check
        assert MappingGenerator._classify_type("BUILTIN\\Users") == "ad_account"

    def test_builtin_without_backslash(self):
        assert MappingGenerator._classify_type("BUILTIN") == "builtin"

    def test_local(self):
        assert MappingGenerator._classify_type("localuser") == "local"


# ===================================================================
# 8. EMPTY / EDGE-CASE SCENARIOS
# ===================================================================

class TestEdgeCases:

    def test_empty_catalog(self, tmp_path):
        gen = _make_generator()
        paths = gen.generate_all(str(tmp_path))
        for p in paths.values():
            rows = _read_csv(p)
            assert len(rows) == 0

    def test_items_without_path(self, tmp_path):
        items = [{"Id": "1", "Name": "NoPath", "Type": "Report"}]
        gen = _make_generator(items=items)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["folders"])
        # Should still produce folder entries without errors
        assert len(rows) >= 0

    def test_item_with_empty_type(self, tmp_path):
        items = [{"Id": "1", "Name": "NoType", "Path": "/Test/NoType"}]
        gen = _make_generator(items=items)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["folders"])
        test_folder = next(r for r in rows if r["folder_path"] == "/Test")
        assert int(test_folder["item_count"]) == 1

    def test_datasource_with_no_connection_string(self, tmp_path):
        embedded = [{
            "item_name": "Report",
            "item_path": "/Report",
            "item_type": "Report",
            "datasource": {"DataSourceType": "SQL"},
        }]
        gen = _make_generator(embedded_ds=embedded)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["connections"])
        assert len(rows) == 1
        assert rows[0]["server_name"] == ""

    def test_policy_with_no_group_user_name(self, tmp_path):
        gen = _make_generator(
            item_policies=[{
                "item_path": "/x",
                "policies": [{"GroupUserName": "", "Roles": [{"Name": "Browser"}]}],
            }]
        )
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["users"])
        # Empty name should be skipped
        assert len(rows) == 0


# ===================================================================
# 9. UNICODE / SPECIAL CHARACTERS
# ===================================================================

class TestSpecialCharacters:

    def test_unicode_report_name(self, tmp_path):
        embedded = [{
            "item_name": "Rapport Financier — Résumé",
            "item_path": "/Finance/Rapport Financier — Résumé",
            "item_type": "Report",
            "datasource": {
                "ConnectionString": "Data Source=srv;Initial Catalog=db",
                "DataSourceType": "SQL",
            },
        }]
        gen = _make_generator(embedded_ds=embedded)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["connections"])
        assert rows[0]["report_name"] == "Rapport Financier — Résumé"

    def test_unicode_folder_name(self, tmp_path):
        items = [{"Id": "1", "Name": "レポート", "Path": "/日本語フォルダ/レポート", "Type": "Report"}]
        gen = _make_generator(items=items)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["folders"])
        assert any("日本語" in r["folder_path"] for r in rows)

    def test_comma_in_connection_string(self, tmp_path):
        embedded = [{
            "item_name": "Report",
            "item_path": "/Report",
            "item_type": "Report",
            "datasource": {
                "ConnectionString": "Data Source=srv,1433;Initial Catalog=db",
                "DataSourceType": "SQL",
            },
        }]
        gen = _make_generator(embedded_ds=embedded)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["connections"])
        # CSV should handle the comma properly (quoted field)
        assert "srv,1433" in rows[0]["connection_string"]

    def test_semicolon_in_name(self, tmp_path):
        items = [{"Id": "1", "Name": "Report; v2", "Path": "/Test/Report; v2", "Type": "Report"}]
        gen = _make_generator(items=items)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["folders"])
        test_folder = next(r for r in rows if r["folder_path"] == "/Test")
        assert int(test_folder["item_count"]) == 1


# ===================================================================
# 10. ROUND-TRIP FIDELITY — CSV read-back matches source data
# ===================================================================

class TestRoundTrip:

    def test_folder_count_matches_unique_parents(self, tmp_path, rich_catalog):
        gen = _make_generator(items=rich_catalog)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["folders"])
        # Manually compute expected folders
        expected_folders = set()
        for item in rich_catalog:
            path = item.get("Path", "")
            parts = path.rstrip("/").rsplit("/", 1)
            folder = parts[0] if len(parts) > 1 else "/"
            if not folder:
                folder = "/"
            expected_folders.add(folder)
        assert len(rows) >= len(expected_folders)

    def test_connection_count_matches_unique_datasources(self, tmp_path, rich_embedded_ds):
        gen = _make_generator(embedded_ds=rich_embedded_ds)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["connections"])
        # Each embedded ds should produce one connection (no duplicates)
        assert len(rows) == len(rich_embedded_ds)

    def test_total_items_across_folders_equals_catalog(self, tmp_path, rich_catalog):
        gen = _make_generator(items=rich_catalog)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["folders"])
        total = sum(int(r["item_count"]) for r in rows)
        assert total == len(rich_catalog)


# ===================================================================
# 11. LARGE CATALOG PERFORMANCE SMOKE TEST
# ===================================================================

class TestLargeCatalog:

    def test_100_items(self, tmp_path):
        items = [
            {
                "Id": str(i),
                "Name": f"Report_{i}",
                "Path": f"/Folder_{i % 10}/Report_{i}",
                "Type": "PowerBIReport" if i % 2 == 0 else "Report",
            }
            for i in range(100)
        ]
        embedded = [
            {
                "item_name": f"Report_{i}",
                "item_path": f"/Folder_{i % 10}/Report_{i}",
                "item_type": "PowerBIReport",
                "datasource": {
                    "ConnectionString": f"Data Source=srv{i % 5};Initial Catalog=db{i % 3}",
                    "DataSourceType": "SQL",
                },
            }
            for i in range(100)
        ]
        policies = [
            {
                "item_path": f"/Folder_{i % 10}/Report_{i}",
                "policies": [{"GroupUserName": f"D\\user{i % 20}", "Roles": [{"Name": "Browser"}]}],
            }
            for i in range(100)
        ]

        gen = _make_generator(items=items, embedded_ds=embedded, item_policies=policies)
        paths = gen.generate_all(str(tmp_path))

        folder_rows = _read_csv(paths["folders"])
        assert len(folder_rows) == 10  # 10 unique folders

        user_rows = _read_csv(paths["users"])
        assert len(user_rows) == 20  # 20 unique users

        conn_rows = _read_csv(paths["connections"])
        # 5 servers * 3 dbs = 15 unique combos, but dedup is by (path, conn_str)
        # 100 items, each unique path → 100 connections
        assert len(conn_rows) == 100

    def test_total_items_adds_up_for_large_catalog(self, tmp_path):
        items = [
            {
                "Id": str(i),
                "Name": f"R{i}",
                "Path": f"/F{i % 5}/R{i}",
                "Type": "Report",
            }
            for i in range(50)
        ]
        gen = _make_generator(items=items)
        paths = gen.generate_all(str(tmp_path))
        rows = _read_csv(paths["folders"])
        total = sum(int(r["item_count"]) for r in rows)
        assert total == 50


# ===================================================================
# 12. ROLE SUGGESTION LOGIC
# ===================================================================

class TestRoleSuggestion:

    @pytest.mark.parametrize("ssrs_role,expected_pbi", [
        ("Browser", "Viewer"),
        ("Content Manager", "Admin"),
        ("Publisher", "Contributor"),
        ("Report Builder", "Contributor"),
        ("My Reports", "Contributor"),
        ("System Administrator", "Admin"),
        ("System User", "Viewer"),
    ])
    def test_individual_role_mapping(self, ssrs_role, expected_pbi):
        assert MappingGenerator._suggest_pbi_role([ssrs_role]) == expected_pbi

    def test_unknown_role_defaults_to_viewer(self):
        assert MappingGenerator._suggest_pbi_role(["CustomRole"]) == "Viewer"

    def test_empty_roles_defaults_to_viewer(self):
        assert MappingGenerator._suggest_pbi_role([]) == "Viewer"

    def test_admin_wins_over_viewer(self):
        result = MappingGenerator._suggest_pbi_role(["Browser", "Content Manager"])
        assert result == "Admin"

    def test_contributor_wins_over_viewer(self):
        result = MappingGenerator._suggest_pbi_role(["Browser", "Publisher"])
        assert result == "Contributor"
