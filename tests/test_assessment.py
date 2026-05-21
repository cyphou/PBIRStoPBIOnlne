"""Tests for MigrationAssessment."""

import pytest
from pbirs_export.assessment import MigrationAssessment, GREEN, YELLOW, RED


class TestMigrationAssessment:

    def test_empty_catalog(self):
        result = MigrationAssessment().assess({"items": []})
        assert result["summary"]["total_items"] == 0
        assert result["waves"] == []

    def test_assess_powerbi_report_green(self):
        catalog = {
            "items": [{
                "Id": "1",
                "Name": "Simple Report",
                "Path": "/Reports/Simple",
                "Type": "PowerBIReport",
                "datasources": [
                    {"ConnectionString": "Data Source=myserver.database.windows.net;Initial Catalog=MyDB"}
                ],
                "policies": [],
                "subscriptions": [],
                "custom_visuals": [],
            }]
        }
        result = MigrationAssessment().assess(catalog)
        assert result["summary"]["total_items"] == 1
        assert result["summary"]["green"] == 1
        assert result["items"][0]["overall"] == GREEN

    def test_assess_paginated_report_needs_capacity(self):
        catalog = {
            "items": [{
                "Id": "2",
                "Name": "Paginated",
                "Path": "/Reports/Paginated",
                "Type": "Report",
                "datasources": [],
                "policies": [],
                "subscriptions": [],
                "rdl_features": set(),
                "custom_visuals": [],
            }]
        }
        result = MigrationAssessment().assess(catalog)
        assert result["items"][0]["scores"]["capacity_requirements"]["score"] == YELLOW

    def test_assess_file_share_subscription_red(self):
        catalog = {
            "items": [{
                "Id": "3",
                "Name": "Report With FileShare",
                "Path": "/Reports/FS",
                "Type": "Report",
                "datasources": [],
                "policies": [],
                "subscriptions": [
                    {"DeliveryExtension": "Report Server FileShare", "IsDataDriven": False}
                ],
                "rdl_features": set(),
                "custom_visuals": [],
            }]
        }
        result = MigrationAssessment().assess(catalog)
        assert result["items"][0]["scores"]["subscription_migration"]["score"] == RED

    def test_wave_planning(self, sample_assessment):
        waves = sample_assessment["waves"]
        assert len(waves) >= 1
        # Wave names should be in order
        for i, wave in enumerate(waves):
            assert wave["wave"] == i + 1

    def test_html_report_generation(self, sample_assessment, tmp_path):
        output = str(tmp_path / "report.html")
        MigrationAssessment().generate_html_report(sample_assessment, output)
        with open(output, encoding="utf-8") as f:
            html = f.read()
        assert "PBIRS" in html
        assert "Sales Dashboard" in html

    def test_mobile_report_red(self):
        catalog = {
            "items": [{
                "Id": "4",
                "Name": "Old Mobile",
                "Path": "/Mobile/Old",
                "Type": "MobileReport",
                "datasources": [],
                "policies": [],
                "subscriptions": [],
                "custom_visuals": [],
            }]
        }
        result = MigrationAssessment().assess(catalog)
        assert result["items"][0]["overall"] == RED

    def test_on_prem_datasource_needs_gateway(self):
        catalog = {
            "items": [{
                "Id": "5",
                "Name": "On-Prem Report",
                "Path": "/Reports/OnPrem",
                "Type": "PowerBIReport",
                "datasources": [
                    {"ConnectionString": "Data Source=sqlserver.corp.local;Initial Catalog=ProdDB"}
                ],
                "policies": [],
                "subscriptions": [],
                "custom_visuals": [],
            }]
        }
        result = MigrationAssessment().assess(catalog)
        assert result["items"][0]["scores"]["gateway_requirements"]["score"] == YELLOW

    def test_none_datasource_fields_no_crash(self):
        """Shared datasource references return None for ConnectionString/DataSourceType."""
        catalog = {
            "items": [{
                "Id": "6",
                "Name": "Shared DS Report",
                "Path": "/Reports/SharedDS",
                "Type": "Report",
                "datasources": [
                    {"ConnectionString": None, "DataSourceType": None, "IsReference": True}
                ],
                "policies": [],
                "subscriptions": [],
                "custom_visuals": [],
            }]
        }
        result = MigrationAssessment().assess(catalog)
        # Should not crash; datasource scored as GREEN since no detectable issues
        assert result["items"][0]["scores"]["datasource_compatibility"]["score"] == GREEN
        assert result["items"][0]["scores"]["gateway_requirements"]["score"] == GREEN
