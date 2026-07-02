"""Tests for DB-assisted security inheritance resolver."""

from pbirs_export.security_inheritance_resolver import SecurityInheritanceResolver


def _api_item_policies() -> list[dict]:
    return [
        {
            "item_id": "1",
            "item_name": "Finance",
            "item_path": "/Finance/R1",
            "item_type": "PowerBIReport",
            "policies": [
                {"GroupUserName": "DOMAIN\\Finance", "Roles": [{"Name": "Browser"}]},
            ],
        }
    ]


def _catalog_items() -> list[dict]:
    return [
        {"Id": "1", "Name": "Finance", "Path": "/Finance/R1", "Type": "PowerBIReport"},
        {"Id": "2", "Name": "HR", "Path": "/HR/R2", "Type": "PowerBIReport"},
    ]


def test_prefer_api_strategy_keeps_api_permissions_when_conflict():
    def fetcher() -> dict[str, set[tuple[str, str]]]:
        return {
            "/Finance/R1": {("DOMAIN\\Finance", "Content Manager")},
            "/HR/R2": {("DOMAIN\\HR", "Browser")},
        }

    resolver = SecurityInheritanceResolver(
        connection_string="Server=.;Database=ReportServer;",
        conflict_strategy="prefer-api",
        db_fetcher=fetcher,
    )
    result = resolver.resolve(_api_item_policies(), _catalog_items())

    merged = {p["item_path"]: p for p in result["merged_item_policies"]}
    finance_policies = merged["/Finance/R1"]["policies"]
    assert finance_policies[0]["Roles"][0]["Name"] == "Browser"
    assert result["gap_report"]["diff_items_count"] == 2


def test_prefer_db_strategy_uses_db_permissions_when_available():
    def fetcher() -> dict[str, set[tuple[str, str]]]:
        return {
            "/Finance/R1": {("DOMAIN\\Finance", "Content Manager")},
        }

    resolver = SecurityInheritanceResolver(
        connection_string="Server=.;Database=ReportServer;",
        conflict_strategy="prefer-db",
        db_fetcher=fetcher,
    )
    result = resolver.resolve(_api_item_policies(), _catalog_items())

    merged = {p["item_path"]: p for p in result["merged_item_policies"]}
    finance_policies = merged["/Finance/R1"]["policies"]
    assert finance_policies[0]["Roles"][0]["Name"] == "Content Manager"


def test_strict_strategy_reports_conflict_and_source():
    def fetcher() -> dict[str, set[tuple[str, str]]]:
        return {
            "/Finance/R1": {("DOMAIN\\Finance", "Content Manager")},
        }

    resolver = SecurityInheritanceResolver(
        connection_string="Server=.;Database=ReportServer;",
        conflict_strategy="strict-fail-on-diff",
        db_fetcher=fetcher,
    )
    result = resolver.resolve(_api_item_policies(), _catalog_items())
    report = result["gap_report"]

    assert report["conflict_strategy"] == "strict-fail-on-diff"
    assert report["diff_items_count"] == 1
    finance = next(i for i in report["items"] if i["item_path"] == "/Finance/R1")
    assert finance["conflict"] is True
    assert finance["resolved_source"] in {"api", "db"}
