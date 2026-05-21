"""Tests for GatewayMapper."""

import json
import pytest
from pbi_import.gateway_mapper import GatewayMapper


class TestGatewayMapper:

    def test_bind_no_mapping(self, mock_pbi_client):
        mapper = GatewayMapper(mock_pbi_client)
        result = mapper.bind_datasets("ws-001", [{"dataset_id": "ds-001", "name": "Report"}])
        assert result["bound"][0]["status"] == "no_mapping"

    def test_bind_with_mapping(self, mock_pbi_client, tmp_path):
        mapping = {"Report": {"gateway_id": "gw-001", "datasource_ids": ["dsid-001"]}}
        mapping_file = tmp_path / "gateway.json"
        mapping_file.write_text(json.dumps(mapping))

        mapper = GatewayMapper(mock_pbi_client, str(mapping_file))
        result = mapper.bind_datasets("ws-001", [{"dataset_id": "ds-001", "name": "Report"}])
        assert result["bound"][0]["status"] == "bound"
        mock_pbi_client.bind_to_gateway.assert_called_once()

    def test_bind_dry_run(self, mock_pbi_client, tmp_path):
        mapping = {"Report": {"gateway_id": "gw-001"}}
        mapping_file = tmp_path / "gateway.json"
        mapping_file.write_text(json.dumps(mapping))

        mapper = GatewayMapper(mock_pbi_client, str(mapping_file))
        result = mapper.bind_datasets("ws-001", [{"dataset_id": "ds-001", "name": "Report"}], dry_run=True)
        assert result["bound"][0]["status"] == "dry_run"
        mock_pbi_client.bind_to_gateway.assert_not_called()

    def test_generate_mapping_template(self, mock_pbi_client, tmp_path):
        datasources = {
            "embedded_datasources": [
                {"item_name": "Sales", "datasource": {"ConnectionString": "Data Source=srv"}}
            ]
        }
        output = str(tmp_path / "template.json")
        mapper = GatewayMapper(mock_pbi_client)
        mapper.generate_mapping_template(datasources, output)

        with open(output) as f:
            template = json.load(f)
        assert "Sales" in template
