import csv
import json

from pbirs_export.bpa_extractor import BPAExtractor


def _read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def test_extract_includes_principals_for_item_path():
    catalog = {
        "items": [
            {
                "Id": "1",
                "Name": "Sales",
                "Path": "/Finance/Sales",
                "Type": "PowerBIReport",
                "datasources": [{"ConnectionString": "Data Source=localhost;Initial Catalog=Sales"}],
                "policies": [{"GroupUserName": "CONTOSO\\u1", "Roles": [{"Name": "Browser"}]}],
            }
        ]
    }
    security = {
        "effective_permissions": [
            {
                "item_path": "/Finance/Sales",
                "principal": "CONTOSO\\u1",
                "ssrs_role": "Browser",
            }
        ]
    }

    payload = BPAExtractor().extract(catalog, security)
    assert payload["summary"]["total_items"] == 1
    assert payload["summary"]["items_with_attached_accounts"] == 1
    item = payload["items"][0]
    assert item["item_name"] == "Sales"
    assert item["principal_count"] == 1
    assert "CONTOSO\\u1" in item["principals"]


def test_save_json_and_csv(tmp_path):
    payload = {
        "summary": {"total_items": 1},
        "items": [
            {
                "item_name": "Sales",
                "item_path": "/Finance/Sales",
                "item_type": "PowerBIReport",
                "bpa_overall": "YELLOW",
                "red_categories": ["datasource_compatibility"],
                "yellow_categories": ["gateway_requirements"],
                "principal_count": 2,
                "principals": ["u1", "u2"],
                "notes": ["Needs gateway"],
            }
        ],
    }

    ex = BPAExtractor()
    json_path = ex.save_json(str(tmp_path), payload)
    csv_path = ex.save_csv(str(tmp_path), payload)

    with open(json_path, encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["summary"]["total_items"] == 1

    rows = _read_csv(csv_path)
    assert len(rows) == 1
    assert rows[0]["item_name"] == "Sales"
    assert rows[0]["bpa_overall"] == "YELLOW"
    assert rows[0]["principal_count"] == "2"


def test_extract_attaches_model_role_principals_and_gap_metadata():
    catalog = {
        "items": [
            {
                "Id": "1",
                "Name": "Sales",
                "Path": "/Finance/Sales",
                "Type": "PowerBIReport",
                "datasources": [{"ConnectionString": "Data Source=localhost;Initial Catalog=Sales"}],
                "policies": [{"GroupUserName": "CONTOSO\\u1", "Roles": [{"Name": "Browser"}]}],
            }
        ]
    }
    security = {"effective_permissions": []}
    model_snapshot = {
        "available": True,
        "roles": [
            {"name": "RLS_Finance", "members": ["CONTOSO\\FinanceReaders"]},
            {"name": "RLS_Empty"},
        ],
    }

    payload = BPAExtractor().extract(catalog, security, model_snapshot=model_snapshot)
    item = payload["items"][0]

    assert "CONTOSO\\FinanceReaders" in item["principals"]
    assert item["model_role_principal_count"] == 1
    assert "CONTOSO\\FinanceReaders" in item["model_role_principals"]
    assert "RLS_Empty" in item["model_roles_without_members"]
    assert payload["summary"]["model_role_principal_count"] == 1
