"""Tests for SecurityConverter."""

import json
import pytest
from pbi_import.security_converter import SecurityConverter, ROLE_MAP


@pytest.fixture
def sample_security_data():
    """Extracted security data fixture."""
    return {
        "system_policies": [
            {"GroupUserName": "BUILTIN\\Administrators", "Roles": [{"Name": "System Administrator"}]},
        ],
        "principals": [
            {"name": "DOMAIN\\Finance", "type": "ad_account", "domain": "DOMAIN", "ssrs_roles": ["Browser"]},
            {"name": "DOMAIN\\Admins", "type": "ad_account", "domain": "DOMAIN", "ssrs_roles": ["Content Manager"]},
            {"name": "user@corp.com", "type": "email", "ssrs_roles": ["Publisher"]},
        ],
        "effective_permissions": [
            {"item_path": "/Finance/R1", "item_name": "R1", "item_type": "PowerBIReport",
             "principal": "DOMAIN\\Finance", "ssrs_role": "Browser", "source": "direct"},
            {"item_path": "/Finance/R1", "item_name": "R1", "item_type": "PowerBIReport",
             "principal": "DOMAIN\\Admins", "ssrs_role": "Content Manager", "source": "direct"},
            {"item_path": "/HR/R2", "item_name": "R2", "item_type": "PowerBIReport",
             "principal": "user@corp.com", "ssrs_role": "Publisher", "source": "direct"},
        ],
        "rls_detection": [
            {"item_id": "1", "item_name": "R1", "item_path": "/Finance/R1", "indicators": ["metadata flag"]},
        ],
        "workspace_recommendations": [
            {
                "workspace_index": 1, "suggested_name": "Workspace-1",
                "item_count": 1, "items": [{"path": "/Finance/R1", "name": "R1", "type": "PowerBIReport"}],
                "principals": ["DOMAIN\\Finance", "DOMAIN\\Admins"],
                "access_pattern": [
                    {"principal": "DOMAIN\\Finance", "role": "Browser"},
                    {"principal": "DOMAIN\\Admins", "role": "Content Manager"},
                ],
            },
            {
                "workspace_index": 2, "suggested_name": "Workspace-2",
                "item_count": 1, "items": [{"path": "/HR/R2", "name": "R2", "type": "PowerBIReport"}],
                "principals": ["user@corp.com"],
                "access_pattern": [{"principal": "user@corp.com", "role": "Publisher"}],
            },
        ],
        "inheritance_map": {},
        "summary": {},
    }


class TestSecurityConverter:

    def test_convert_basic(self, sample_security_data):
        converter = SecurityConverter(sample_security_data)
        plan = converter.convert()
        assert plan["summary"]["total_assignments"] == 3
        assert plan["dry_run"] is False

    def test_role_mapping(self, sample_security_data):
        converter = SecurityConverter(sample_security_data)
        plan = converter.convert()
        assignments = plan["role_assignments"]
        by_principal = {a["pbirs_principal"]: a for a in assignments}
        assert by_principal["DOMAIN\\Finance"]["pbi_role"] == "Viewer"
        assert by_principal["DOMAIN\\Admins"]["pbi_role"] == "Admin"
        assert by_principal["user@corp.com"]["pbi_role"] == "Contributor"

    def test_tenant_mapping(self, sample_security_data, tmp_path):
        mapping_file = tmp_path / "tenant_map.json"
        mapping_file.write_text(json.dumps({
            "DOMAIN\\Finance": "finance-team@contoso.com",
            "DOMAIN\\Admins": "report-admins@contoso.com",
            "_comment": "ignore me",
        }))
        converter = SecurityConverter(sample_security_data, str(mapping_file))
        plan = converter.convert()
        assignments = plan["role_assignments"]
        by_principal = {a["pbirs_principal"]: a for a in assignments}
        assert by_principal["DOMAIN\\Finance"]["azure_ad_identity"] == "finance-team@contoso.com"
        assert by_principal["DOMAIN\\Admins"]["azure_ad_identity"] == "report-admins@contoso.com"
        assert by_principal["user@corp.com"]["azure_ad_identity"] is None

    def test_unmapped_principals(self, sample_security_data):
        converter = SecurityConverter(sample_security_data)
        plan = converter.convert()
        unmapped = plan["unmapped_principals"]
        # All 3 principals should be unmapped (no tenant mapping provided)
        assert len(unmapped) == 3

    def test_rls_plan(self, sample_security_data):
        converter = SecurityConverter(sample_security_data)
        plan = converter.convert()
        rls = plan["rls_plan"]
        assert len(rls) == 1
        assert rls[0]["report_name"] == "R1"
        assert "Reconfigure RLS" in rls[0]["action"]

    def test_workspace_plan(self, sample_security_data):
        converter = SecurityConverter(sample_security_data)
        plan = converter.convert()
        ws_plan = plan["workspace_plan"]
        assert len(ws_plan) == 2
        assert ws_plan[0]["item_count"] == 1

    def test_workspace_plan_with_tenant_mapping(self, sample_security_data, tmp_path):
        mapping_file = tmp_path / "mapping.json"
        mapping_file.write_text(json.dumps({
            "DOMAIN\\Finance": "finance@contoso.com",
        }))
        converter = SecurityConverter(sample_security_data, str(mapping_file))
        plan = converter.convert()
        ws1 = plan["workspace_plan"][0]
        mapped = [r for r in ws1["role_assignments"] if r.get("azure_ad_identity")]
        assert len(mapped) >= 1

    def test_unmapped_roles(self, sample_security_data):
        # Add an entry with a custom role
        sample_security_data["effective_permissions"].append({
            "item_path": "/X", "item_name": "X", "item_type": "Report",
            "principal": "DOMAIN\\Custom", "ssrs_role": "CustomRole", "source": "direct",
        })
        converter = SecurityConverter(sample_security_data)
        plan = converter.convert()
        assert len(plan["unmapped_roles"]) == 1
        assert plan["unmapped_roles"][0]["ssrs_role"] == "CustomRole"

    def test_dry_run(self, sample_security_data):
        converter = SecurityConverter(sample_security_data)
        plan = converter.convert(dry_run=True)
        assert plan["dry_run"] is True

    def test_save_plan(self, sample_security_data, tmp_path):
        converter = SecurityConverter(sample_security_data)
        plan = converter.convert()
        path = converter.save_plan(str(tmp_path / "out"), plan)
        assert path.exists()
        with open(path) as f:
            loaded = json.load(f)
        assert loaded["summary"]["total_assignments"] == 3

    def test_missing_tenant_mapping_file(self, sample_security_data):
        converter = SecurityConverter(sample_security_data, "/nonexistent/mapping.json")
        plan = converter.convert()
        # Should not fail, just have no mappings
        assert plan["summary"]["unmapped_principals"] == 3
