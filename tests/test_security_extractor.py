"""Tests for SecurityExtractor."""

import pytest
from unittest.mock import MagicMock
from pbirs_export.security_extractor import SecurityExtractor


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.get_system_policies.return_value = [
        {"GroupUserName": "BUILTIN\\Administrators", "Roles": [{"Name": "System Administrator"}]},
    ]
    return client


class TestSecurityExtractor:

    def test_extract_empty_catalog(self, mock_client):
        extractor = SecurityExtractor(mock_client)
        result = extractor.extract_all({"items": [], "folders": []})
        assert result["summary"]["total_principals"] == 1  # system policy principal
        assert result["summary"]["rls_report_count"] == 0

    def test_inheritance_detection(self, mock_client):
        items = [
            {
                "Id": "1", "Name": "R1", "Path": "/Finance/R1", "Type": "PowerBIReport",
                "policies": [{"GroupUserName": "DOMAIN\\Admins", "Roles": [{"Name": "Content Manager"}]}],
                "datasources": [],
            },
            {
                "Id": "2", "Name": "R2", "Path": "/Finance/R2", "Type": "PowerBIReport",
                "policies": [],
                "datasources": [],
            },
        ]
        extractor = SecurityExtractor(mock_client)
        result = extractor.extract_all({"items": items, "folders": []})
        imap = result["inheritance_map"]
        assert imap["/Finance/R1"]["breaks_inheritance"] is True
        assert imap["/Finance/R2"]["breaks_inheritance"] is False

    def test_principal_enumeration(self, mock_client):
        items = [
            {
                "Id": "1", "Name": "R1", "Path": "/R1", "Type": "PowerBIReport",
                "policies": [
                    {"GroupUserName": "DOMAIN\\Viewers", "Roles": [{"Name": "Browser"}]},
                    {"GroupUserName": "user@corp.com", "Roles": [{"Name": "Publisher"}]},
                ],
                "datasources": [],
            },
        ]
        extractor = SecurityExtractor(mock_client)
        result = extractor.extract_all({"items": items, "folders": []})
        principals = result["principals"]
        names = {p["name"] for p in principals}
        assert "DOMAIN\\Viewers" in names
        assert "user@corp.com" in names
        # AD account classification
        domain_p = next(p for p in principals if p["name"] == "DOMAIN\\Viewers")
        assert domain_p["type"] == "ad_account"
        assert domain_p["domain"] == "DOMAIN"
        # Email classification
        email_p = next(p for p in principals if p["name"] == "user@corp.com")
        assert email_p["type"] == "email"

    def test_rls_detection(self, mock_client):
        items = [
            {
                "Id": "1", "Name": "Secure Report", "Path": "/Secure Report",
                "Type": "PowerBIReport",
                "has_rls": True,
                "policies": [], "datasources": [],
            },
            {
                "Id": "2", "Name": "Normal Report", "Path": "/Normal Report",
                "Type": "PowerBIReport",
                "policies": [], "datasources": [],
            },
        ]
        extractor = SecurityExtractor(mock_client)
        result = extractor.extract_all({"items": items, "folders": []})
        assert len(result["rls_detection"]) == 1
        assert result["rls_detection"][0]["item_name"] == "Secure Report"

    def test_rls_detection_dax(self, mock_client):
        items = [
            {
                "Id": "1", "Name": "DAX RLS", "Path": "/DAX RLS",
                "Type": "PowerBIReport",
                "dax_expressions": ["FILTER(Users, Users[Email] = USERPRINCIPALNAME())"],
                "policies": [], "datasources": [],
            },
        ]
        extractor = SecurityExtractor(mock_client)
        result = extractor.extract_all({"items": items, "folders": []})
        assert len(result["rls_detection"]) == 1
        assert "DAX security function" in result["rls_detection"][0]["indicators"]

    def test_effective_permissions_direct(self, mock_client):
        items = [
            {
                "Id": "1", "Name": "R1", "Path": "/R1", "Type": "PowerBIReport",
                "policies": [
                    {"GroupUserName": "user@corp.com", "Roles": [{"Name": "Browser"}]},
                ],
                "datasources": [],
            },
        ]
        extractor = SecurityExtractor(mock_client)
        result = extractor.extract_all({"items": items, "folders": []})
        eff = result["effective_permissions"]
        assert len(eff) == 1
        assert eff[0]["source"] == "direct"
        assert eff[0]["ssrs_role"] == "Browser"

    def test_workspace_recommendations(self, mock_client):
        items = [
            {
                "Id": "1", "Name": "R1", "Path": "/Finance/R1", "Type": "PowerBIReport",
                "policies": [{"GroupUserName": "DOMAIN\\Finance", "Roles": [{"Name": "Browser"}]}],
                "datasources": [],
            },
            {
                "Id": "2", "Name": "R2", "Path": "/Finance/R2", "Type": "PowerBIReport",
                "policies": [{"GroupUserName": "DOMAIN\\Finance", "Roles": [{"Name": "Browser"}]}],
                "datasources": [],
            },
            {
                "Id": "3", "Name": "R3", "Path": "/HR/R3", "Type": "PowerBIReport",
                "policies": [{"GroupUserName": "DOMAIN\\HR", "Roles": [{"Name": "Browser"}]}],
                "datasources": [],
            },
        ]
        extractor = SecurityExtractor(mock_client)
        result = extractor.extract_all({"items": items, "folders": []})
        recs = result["workspace_recommendations"]
        # Finance items should cluster together, HR separate
        assert len(recs) == 2
        counts = sorted(r["item_count"] for r in recs)
        assert counts == [1, 2]

    def test_summary(self, mock_client):
        items = [
            {
                "Id": "1", "Name": "R1", "Path": "/R1", "Type": "PowerBIReport",
                "policies": [{"GroupUserName": "DOMAIN\\Users", "Roles": [{"Name": "Browser"}]}],
                "datasources": [],
            },
        ]
        extractor = SecurityExtractor(mock_client)
        result = extractor.extract_all({"items": items, "folders": []})
        s = result["summary"]
        assert s["total_principals"] >= 1
        assert s["items_with_custom_policies"] == 1
