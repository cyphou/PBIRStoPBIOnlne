"""Tests for MigrationValidator."""

import json
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

    def test_custom_visuals_warn_when_missing_in_target(self, mock_pbi_client):
        mock_pbi_client.list_reports.return_value = [{"id": "r1"}]
        mock_pbi_client.list_datasets.return_value = []
        mock_pbi_client.list_workspace_users.return_value = [{"user": "a"}, {"user": "b"}]
        mock_pbi_client.list_custom_visuals.return_value = [{"name": "otherVisual"}]

        catalog = {
            "items": [
                {"Type": "PowerBIReport", "custom_visuals": ["myFancyVisual"]},
            ]
        }

        validator = MigrationValidator(mock_pbi_client)
        result = validator.validate(catalog, "ws-001", "/tmp/converted")
        assert result["custom_visuals"]["status"] == "WARN"
        assert "Missing" in result["custom_visuals"]["message"]

    def test_binding_parity_warns_when_target_less_bound(self, mock_pbi_client, tmp_path):
        mock_pbi_client.list_reports.return_value = [{"id": "r1"}]
        mock_pbi_client.list_workspace_users.return_value = [{"user": "a"}, {"user": "b"}]
        mock_pbi_client.list_datasets.return_value = [{"id": "d1", "name": "DS1"}]
        mock_pbi_client.get_dataset_datasources.return_value = [{"gatewayId": "gw1"}]
        mock_pbi_client.get_refresh_schedule.return_value = {"enabled": True}

        baseline = {
            "connection_summary": {
                "SQL": 3,
            }
        }
        (tmp_path / "datasources.json").write_text(json.dumps(baseline), encoding="utf-8")
        catalog = {"items": [{"Type": "PowerBIReport"}]}

        validator = MigrationValidator(mock_pbi_client)
        result = validator.validate(catalog, "ws-001", str(tmp_path))
        assert result["binding_parity"]["status"] == "WARN"
        assert "Binding parity mismatch" in result["binding_parity"]["message"]
