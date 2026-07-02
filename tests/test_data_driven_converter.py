"""Tests for DataDrivenConverter."""

import json
import pytest
from pbi_import.data_driven_converter import DataDrivenConverter


def _dd_sub_email():
    return {
        "SubscriptionID": "dd-1",
        "Description": "Regional report per manager",
        "Report": "/Sales/Regional",
        "DeliveryExtension": "Report Server Email",
        "IsDataDriven": True,
        "DataDrivenQuery": "SELECT email, region FROM dbo.Subscriptions",
        "ParameterValues": [
            {"Name": "TO", "Value": "", "FieldReference": "email"},
            {"Name": "Region", "Value": "", "FieldReference": "region"},
            {"Name": "RENDER_FORMAT", "Value": "PDF"},
        ],
    }


def _dd_sub_custom():
    return {
        "SubscriptionID": "dd-2",
        "Description": "Custom delivery",
        "Report": "/Reports/Custom",
        "DeliveryExtension": "CustomPlugin",
        "IsDataDriven": True,
        "DataDrivenQuery": "SELECT * FROM Recipients",
        "ParameterValues": [],
    }


class TestDataDrivenConverter:

    def test_convert_email_strategy(self):
        conv = DataDrivenConverter()
        result = conv.convert_all({"subscriptions": [_dd_sub_email()]})
        assert result["summary"]["total_data_driven"] == 1
        plan = result["plans"][0]
        assert plan["strategy"] == "power_automate"
        assert plan["report_name"] == "Regional"

    def test_custom_strategy_manual(self):
        conv = DataDrivenConverter()
        result = conv.convert_all({"subscriptions": [_dd_sub_custom()]})
        plan = result["plans"][0]
        assert plan["strategy"] == "manual"

    def test_field_mapping_extracted(self):
        conv = DataDrivenConverter()
        result = conv.convert_all({"subscriptions": [_dd_sub_email()]})
        fields = result["plans"][0]["parameter_fields"]
        field_refs = [f["field_reference"] for f in fields if f["field_reference"]]
        assert "email" in field_refs
        assert "region" in field_refs

    def test_original_query_preserved(self):
        conv = DataDrivenConverter()
        result = conv.convert_all({"subscriptions": [_dd_sub_email()]})
        assert "dbo.Subscriptions" in result["plans"][0]["original_query"]

    def test_db_query_metadata_takes_precedence(self):
        sub = _dd_sub_email()
        sub["DbQueryMetadata"] = {
            "query_text": "SELECT email FROM dbo.DbBridgeSource WHERE token='abc'",
            "query_source": "reportserver_db",
        }
        conv = DataDrivenConverter()
        result = conv.convert_all({"subscriptions": [sub]})
        plan = result["plans"][0]
        assert "DbBridgeSource" in plan["original_query"]
        assert plan["query_source"] == "reportserver_db"
        assert "token=***" in plan["query_preview_redacted"]

    def test_non_data_driven_ignored(self):
        normal_sub = {
            "SubscriptionID": "n-1",
            "DeliveryExtension": "Report Server Email",
            "Report": "/r",
            "ParameterValues": [],
        }
        conv = DataDrivenConverter()
        result = conv.convert_all({"subscriptions": [normal_sub]})
        assert result["summary"]["total_data_driven"] == 0
        assert result["plans"] == []

    def test_save_plans(self, tmp_path):
        conv = DataDrivenConverter()
        result = conv.convert_all({"subscriptions": [_dd_sub_email()]})
        paths = conv.save_plans(result, str(tmp_path))
        assert len(paths) >= 3  # plan JSON + param CSV + summary
        json_files = [p for p in paths if p.suffix == ".json"]
        csv_files = [p for p in paths if p.suffix == ".csv"]
        assert len(json_files) >= 2
        assert len(csv_files) >= 1
        csv_text = csv_files[0].read_text(encoding="utf-8")
        assert "query_source" in csv_text
        assert "query_preview_redacted" in csv_text

    def test_migration_notes(self):
        conv = DataDrivenConverter()
        result = conv.convert_all({"subscriptions": [_dd_sub_email()]})
        notes = result["plans"][0]["migration_notes"]
        assert any("Power Automate" in n for n in notes)

    def test_empty_subscriptions(self):
        conv = DataDrivenConverter()
        result = conv.convert_all({"subscriptions": []})
        assert result["summary"]["total_data_driven"] == 0
        assert result["plans"] == []
