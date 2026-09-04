import csv
import json

from pbirs_export.role_membership_extractor import RoleMembershipExtractor


def _read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def test_extract_builds_role_account_rows():
    permissions = {
        "system_policies": [
            {
                "GroupUserName": "CONTOSO\\Admins",
                "Roles": [{"Name": "System Administrator"}],
            }
        ],
        "item_policies": [
            {
                "item_name": "Sales",
                "item_path": "/Finance/Sales",
                "item_type": "PowerBIReport",
                "policies": [
                    {
                        "GroupUserName": "contoso.user@contoso.com",
                        "Roles": [{"Name": "RLS_Sales"}, {"Name": "OLS_Finance"}],
                    }
                ],
            }
        ],
    }
    security = {
        "effective_permissions": [
            {
                "item_path": "/Finance/Sales",
                "item_name": "Sales",
                "item_type": "PowerBIReport",
                "principal": "CONTOSO\\SalesReaders",
                "ssrs_role": "Browser",
                "source": "inherited",
            }
        ]
    }

    payload = RoleMembershipExtractor().extract(permissions, security)
    assert payload["summary"]["total_assignments"] == 2
    assert payload["summary"]["by_security_type"]["RLS"] == 1
    assert payload["summary"]["by_security_type"]["OLS"] == 1


def test_extract_excludes_ssrs_access_roles_and_paginated_reports():
    permissions = {
        "system_policies": [{
            "GroupUserName": "CONTOSO\\Admins",
            "Roles": [{"Name": "System Administrator"}],
        }],
        "item_policies": [
            {
                "item_name": "Paginated",
                "item_path": "/Reports/Paginated",
                "item_type": "Report",
                "policies": [{
                    "GroupUserName": "user@contoso.com",
                    "Roles": [{"Name": "Browser"}, {"Name": "RLS_NotForRdl"}],
                }],
            },
            {
                "item_name": "Model",
                "item_path": "/Reports/Model",
                "item_type": "PowerBIReport",
                "policies": [{
                    "GroupUserName": "user@contoso.com",
                    "Roles": [{"Name": "Browser"}, {"Name": "RLS_Sales"}],
                }],
            },
        ],
    }
    payload = RoleMembershipExtractor().extract(permissions, {"effective_permissions": []})

    assert [row["role_name"] for row in payload["rows"]] == ["RLS_Sales"]


def test_extract_deduplicates_assignments():
    permissions = {
        "system_policies": [],
        "item_policies": [
            {
                "item_name": "Sales",
                "item_path": "/Finance/Sales",
                "item_type": "PowerBIReport",
                "policies": [
                    {
                        "GroupUserName": "CONTOSO\\u1",
                        "Roles": [{"Name": "RLS_Sales"}, {"Name": "RLS_Sales"}],
                    }
                ],
            }
        ],
    }
    security = {"effective_permissions": []}

    payload = RoleMembershipExtractor().extract(permissions, security)
    assert payload["summary"]["total_assignments"] == 1


def test_save_json_and_csv(tmp_path):
    payload = {
        "rows": [
            {
                "security_type": "RLS",
                "role_name": "RLS_Sales",
                "account": "user@contoso.com",
                "account_type": "email",
                "domain": "",
                "scope": "item_policy",
                "item_path": "/Finance/Sales",
                "item_name": "Sales",
                "item_type": "PowerBIReport",
                "source": "permissions.item_policies",
            }
        ],
        "summary": {"total_assignments": 1},
    }

    ex = RoleMembershipExtractor()
    json_path = ex.save_json(str(tmp_path), payload)
    csv_path = ex.save_csv(str(tmp_path), payload)

    with open(json_path, encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["summary"]["total_assignments"] == 1

    rows = _read_csv(csv_path)
    assert len(rows) == 1
    assert rows[0]["role_name"] == "RLS_Sales"


def test_extract_includes_model_snapshot_role_principals_and_gaps():
    permissions = {"system_policies": [], "item_policies": []}
    security = {"effective_permissions": []}
    model_snapshot = {
        "available": True,
        "roles": [
            {"name": "RLS_Finance", "members": ["CONTOSO\\FinanceReaders"]},
            {"name": "OLS_Sensitive"},
        ],
    }

    payload = RoleMembershipExtractor().extract(permissions, security, model_snapshot=model_snapshot)

    rows = payload["rows"]
    model_rows = [r for r in rows if r["source"].startswith("model_snapshot.roles")]
    assert any(r["role_name"] == "RLS_Finance" and r["account"] == "CONTOSO\\FinanceReaders" for r in model_rows)
    assert any(r["role_name"] == "OLS_Sensitive" and r["source"] == "model_snapshot.roles.missing_principals" for r in model_rows)
    assert "OLS_Sensitive" in payload["summary"]["model_roles_without_members"]
