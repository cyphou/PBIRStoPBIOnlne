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
