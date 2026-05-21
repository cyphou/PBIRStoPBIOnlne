"""Tests for PowerAutomateGenerator."""

import json
import pytest
from pbi_import.power_automate_generator import PowerAutomateGenerator


def _email_sub(sub_id: str = "sub-1", report: str = "/Sales/Monthly") -> dict:
    return {
        "SubscriptionID": sub_id,
        "Description": "Monthly sales email",
        "Report": report,
        "DeliveryExtension": "Report Server Email",
        "Schedule": {"RecurrencePattern": "Weekly", "StartDateTime": "2024-01-01T08:00:00"},
        "ParameterValues": [
            {"Name": "TO", "Value": "alice@contoso.com;bob@contoso.com"},
            {"Name": "RENDER_FORMAT", "Value": "PDF"},
        ],
    }


def _fileshare_sub() -> dict:
    return {
        "SubscriptionID": "sub-2",
        "Description": "Nightly export",
        "Report": "/Sales/Nightly",
        "DeliveryExtension": "Report Server FileShare",
        "Schedule": {"RecurrencePattern": "Daily", "StartDateTime": "2024-01-01T02:00:00"},
        "ParameterValues": [
            {"Name": "PATH", "Value": "\\\\server\\share\\reports"},
            {"Name": "FILENAME", "Value": "nightly_report"},
            {"Name": "RENDER_FORMAT", "Value": "EXCELOPENXML"},
        ],
    }


def _datadriven_sub() -> dict:
    return {
        "SubscriptionID": "sub-3",
        "Description": "Per-region report",
        "Report": "/Sales/Regional",
        "DeliveryExtension": "Report Server Email",
        "IsDataDriven": True,
        "DataDrivenQuery": "SELECT email, region FROM Subscriptions",
        "Schedule": {},
        "ParameterValues": [],
    }


class TestPowerAutomateGenerator:

    def test_email_flow(self):
        gen = PowerAutomateGenerator()
        results = gen.generate_flows({"subscriptions": [_email_sub()]})
        assert results["summary"]["flows_generated"] == 1
        flow = results["flows"][0]
        assert flow["display_name"].startswith("Email - ")
        assert flow["trigger"]["frequency"] == "Week"
        email_action = flow["actions"][-1]
        assert email_action["type"] == "SendEmail"
        assert "alice@contoso.com" in email_action["to"]

    def test_fileshare_flow(self):
        gen = PowerAutomateGenerator()
        results = gen.generate_flows({"subscriptions": [_fileshare_sub()]})
        flow = results["flows"][0]
        assert flow["display_name"].startswith("FileShare - ")
        sp_action = flow["actions"][-1]
        assert sp_action["type"] == "CreateFile_SharePoint"

    def test_datadriven_flow(self):
        gen = PowerAutomateGenerator()
        results = gen.generate_flows({"subscriptions": [_datadriven_sub()]})
        # Data-driven with email delivery goes through email path first;
        # verify the flow is generated
        assert results["summary"]["flows_generated"] == 1
        flow = results["flows"][0]
        assert flow["display_name"].startswith("Email - ") or flow.get("data_driven") is True

    def test_unsupported_delivery_skipped(self):
        gen = PowerAutomateGenerator()
        sub = {"SubscriptionID": "x", "DeliveryExtension": "CustomPlugin", "Report": "/r", "ParameterValues": []}
        results = gen.generate_flows({"subscriptions": [sub]})
        assert results["summary"]["skipped"] == 1
        assert results["skipped"][0]["delivery"] == "CustomPlugin"

    def test_multiple_subscriptions(self):
        gen = PowerAutomateGenerator()
        subs = [_email_sub("s1"), _fileshare_sub(), _datadriven_sub()]
        results = gen.generate_flows({"subscriptions": subs})
        assert results["summary"]["total_subscriptions"] == 3
        assert results["summary"]["flows_generated"] == 3

    def test_render_format_mapping(self):
        gen = PowerAutomateGenerator()
        results = gen.generate_flows({"subscriptions": [_fileshare_sub()]})
        export_action = results["flows"][0]["actions"][0]
        assert export_action["format"] == "XLSX"

    def test_save_flows(self, tmp_path):
        gen = PowerAutomateGenerator()
        results = gen.generate_flows({"subscriptions": [_email_sub(), _fileshare_sub()]})
        paths = gen.save_flows(results, str(tmp_path))
        assert len(paths) == 3  # 2 flows + summary
        for p in paths:
            assert p.exists()
            data = json.loads(p.read_text(encoding="utf-8"))
            assert isinstance(data, dict)

    def test_published_items_lookup(self):
        gen = PowerAutomateGenerator()
        published = {"/Sales/Monthly": {"report_id": "abc-123"}}
        results = gen.generate_flows({"subscriptions": [_email_sub()]}, published_items=published)
        export = results["flows"][0]["actions"][0]
        assert export["published_report_id"] == "abc-123"

    def test_empty_subscriptions(self):
        gen = PowerAutomateGenerator()
        results = gen.generate_flows({"subscriptions": []})
        assert results["summary"]["flows_generated"] == 0
        assert results["flows"] == []
