"""Tests for MigrationValidator."""

import pytest
from pbi_import.validator import MigrationValidator


class TestMigrationValidator:

    def test_validate_all_pass(self, mock_pbi_client):
        mock_pbi_client.list_reports.return_value = [{"id": "r1"}, {"id": "r2"}]
        mock_pbi_client.list_datasets.return_value = [{"id": "d1", "name": "DS1"}]
        mock_pbi_client.get_dataset_datasources.return_value = [{"gatewayId": "gw1"}]
        mock_pbi_client.get_refresh_schedule.return_value = {"enabled": True}
        mock_pbi_client.list_workspace_users.return_value = [{"user": "a"}, {"user": "b"}]

        catalog = {"items": [
            {"Type": "PowerBIReport"},
            {"Type": "Report"},
        ]}

        validator = MigrationValidator(mock_pbi_client)
        result = validator.validate(catalog, "ws-001", "/tmp/converted")
        assert result["overall"] == "PASS"

    def test_validate_missing_reports(self, mock_pbi_client):
        mock_pbi_client.list_reports.return_value = []
        mock_pbi_client.list_datasets.return_value = []
        mock_pbi_client.list_workspace_users.return_value = [{"user": "a"}]

        catalog = {"items": [{"Type": "PowerBIReport"}]}

        validator = MigrationValidator(mock_pbi_client)
        result = validator.validate(catalog, "ws-001", "/tmp/converted")
        assert result["overall"] == "FAIL"

    def test_validate_unbound_datasources(self, mock_pbi_client):
        mock_pbi_client.list_reports.return_value = [{"id": "r1"}]
        mock_pbi_client.list_datasets.return_value = [{"id": "d1", "name": "DS1"}]
        mock_pbi_client.get_dataset_datasources.return_value = [{}]  # No gateway
        mock_pbi_client.get_refresh_schedule.return_value = {"enabled": True}
        mock_pbi_client.list_workspace_users.return_value = [{"user": "a"}, {"user": "b"}]

        catalog = {"items": [{"Type": "PowerBIReport"}]}

        validator = MigrationValidator(mock_pbi_client)
        result = validator.validate(catalog, "ws-001", "/tmp/converted")
        assert result["datasource_binding"]["status"] == "WARN"
