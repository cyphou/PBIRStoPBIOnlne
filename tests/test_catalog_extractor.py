"""Tests for CatalogExtractor."""

import pytest
from unittest.mock import MagicMock
from pbirs_export.catalog_extractor import CatalogExtractor


class TestCatalogExtractor:

    def test_extract_empty(self, mock_pbirs_client):
        mock_pbirs_client.list_catalog_items.return_value = []
        extractor = CatalogExtractor(mock_pbirs_client)
        result = extractor.extract_catalog()
        assert result["total_count"] == 0

    def test_extract_with_items(self, mock_pbirs_client):
        mock_pbirs_client.list_catalog_items.return_value = [
            {"Id": "1", "Name": "Report A", "Path": "/Folder/Report A", "Type": "PowerBIReport"},
            {"Id": "2", "Name": "KPI B", "Path": "/KPIs/KPI B", "Type": "Kpi"},
        ]
        mock_pbirs_client.get_powerbi_report_datasources.return_value = []
        mock_pbirs_client.get_item_policies.return_value = []
        mock_pbirs_client.list_subscriptions.return_value = []
        mock_pbirs_client.list_cache_refresh_plans.return_value = []

        extractor = CatalogExtractor(mock_pbirs_client)
        result = extractor.extract_catalog()
        assert result["total_count"] == 2

    def test_extract_preserves_policy_inheritance(self, mock_pbirs_client):
        mock_pbirs_client.list_catalog_items.return_value = [
            {"Id": "1", "Name": "Report A", "Path": "/Folder/Report A", "Type": "PowerBIReport"},
        ]
        mock_pbirs_client.get_powerbi_report_datasources.return_value = []
        mock_pbirs_client.get_item_policy_details.return_value = {
            "policies": [
                {"GroupUserName": "DOMAIN\\Readers", "Roles": [{"Name": "Browser"}]},
            ],
            "inherit_parent_policy": True,
        }
        mock_pbirs_client.list_subscriptions.return_value = []
        mock_pbirs_client.list_cache_refresh_plans.return_value = []

        result = CatalogExtractor(mock_pbirs_client).extract_catalog()

        assert result["items"][0]["inherit_parent_policy"] is True

    def test_filter_content_types(self, mock_pbirs_client):
        mock_pbirs_client.list_catalog_items.return_value = [
            {"Id": "1", "Name": "Report", "Path": "/Report", "Type": "PowerBIReport"},
            {"Id": "2", "Name": "KPI", "Path": "/KPI", "Type": "Kpi"},
        ]
        mock_pbirs_client.get_powerbi_report_datasources.return_value = []
        mock_pbirs_client.get_item_policies.return_value = []
        mock_pbirs_client.list_subscriptions.return_value = []
        mock_pbirs_client.list_cache_refresh_plans.return_value = []

        extractor = CatalogExtractor(mock_pbirs_client)
        result = extractor.extract_catalog(content_types=["powerbi"])
        assert result["total_count"] == 1
        assert result["items"][0]["Name"] == "Report"

    def test_include_pattern(self, mock_pbirs_client):
        mock_pbirs_client.list_catalog_items.return_value = [
            {"Id": "1", "Name": "Sales Report", "Path": "/Sales Report", "Type": "PowerBIReport"},
            {"Id": "2", "Name": "HR Report", "Path": "/HR Report", "Type": "PowerBIReport"},
        ]
        mock_pbirs_client.get_powerbi_report_datasources.return_value = []
        mock_pbirs_client.get_item_policies.return_value = []
        mock_pbirs_client.list_subscriptions.return_value = []
        mock_pbirs_client.list_cache_refresh_plans.return_value = []

        extractor = CatalogExtractor(mock_pbirs_client)
        result = extractor.extract_catalog(include_pattern="Sales")
        assert result["total_count"] == 1

    def test_enriches_in_sequential_batches_and_lists_subscriptions_once(self, mock_pbirs_client):
        mock_pbirs_client.list_catalog_items.return_value = [
            {"Id": str(i), "Name": f"Report {i}", "Path": f"/Report {i}", "Type": "Kpi"}
            for i in range(31)
        ]
        mock_pbirs_client.list_subscriptions.return_value = []
        mock_pbirs_client.list_cache_refresh_plans.return_value = []

        result = CatalogExtractor(mock_pbirs_client).extract_catalog(batch_size=15)

        assert result["total_count"] == 31
        mock_pbirs_client.list_subscriptions.assert_called_once_with()

    def test_rejects_invalid_batch_size(self, mock_pbirs_client):
        with pytest.raises(ValueError, match="batch_size"):
            CatalogExtractor(mock_pbirs_client).extract_catalog(batch_size=0)

    def test_extracts_rdl_connection_when_api_metadata_is_empty(self, mock_pbirs_client):
        mock_pbirs_client.list_catalog_items.return_value = [
            {"Id": "rdl-1", "Name": "Finance", "Path": "/Finance/Finance", "Type": "Report"},
        ]
        mock_pbirs_client.get_report_datasources.return_value = []
        mock_pbirs_client.download_report.return_value = b"""<?xml version='1.0'?>
        <Report xmlns='http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition'>
          <DataSources>
            <DataSource Name='FinanceDS'>
              <DataSourceReference>/DataSources/FinanceSQL</DataSourceReference>
            </DataSource>
          </DataSources>
        </Report>"""
        mock_pbirs_client.list_datasources.return_value = [{
            "Name": "FinanceSQL",
            "Path": "/DataSources/FinanceSQL",
            "DataSourceType": "SQL",
            "ConnectionString": "Data Source=sql01;Initial Catalog=Finance,Archive",
        }]
        mock_pbirs_client.list_subscriptions.return_value = []
        mock_pbirs_client.list_cache_refresh_plans.return_value = []

        result = CatalogExtractor(mock_pbirs_client).extract_catalog()

        datasource = result["items"][0]["datasources"][0]
        assert datasource["DataSourceType"] == "SQL"
        assert datasource["ConnectionString"] == "Data Source=sql01;Initial Catalog=Finance,Archive"

    def test_merges_rdl_connection_when_api_metadata_is_incomplete(self, mock_pbirs_client):
        mock_pbirs_client.list_catalog_items.return_value = [
            {"Id": "rdl-2", "Name": "Finance", "Path": "/Finance/Finance", "Type": "Report"},
        ]
        mock_pbirs_client.get_report_datasources.return_value = [{
            "Name": "FinanceDS",
            "ConnectionString": "",
            "DataSourceType": "",
        }]
        mock_pbirs_client.download_report.return_value = b"""<Report xmlns='http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition'>
          <DataSources><DataSource Name='FinanceDS'><ConnectionProperties>
          <DataProvider>SQL</DataProvider><ConnectString>Data Source=sql01;Initial Catalog=Finance</ConnectString>
          </ConnectionProperties></DataSource></DataSources></Report>"""
        mock_pbirs_client.list_subscriptions.return_value = []
        mock_pbirs_client.list_cache_refresh_plans.return_value = []

        result = CatalogExtractor(mock_pbirs_client).extract_catalog()

        datasource = result["items"][0]["datasources"][0]
        assert datasource["DataSourceType"] == "SQL"
        assert datasource["ConnectionString"] == "Data Source=sql01;Initial Catalog=Finance"
