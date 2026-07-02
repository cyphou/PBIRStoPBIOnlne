"""Tests for ReportServerDbBridge."""

from pbi_import.reportserver_db_bridge import ReportServerDbBridge


def _subscriptions_payload():
    return {
        "subscriptions": [
            {
                "SubscriptionID": "sub-1",
                "IsDataDriven": True,
                "DeliveryExtension": "Report Server Email",
                "Report": "/Sales/Regional",
            },
            {
                "SubscriptionID": "sub-2",
                "IsDataDriven": True,
                "DeliveryExtension": "Report Server Email",
                "Report": "/Sales/Regional2",
            },
        ]
    }


def test_merge_injects_db_query_metadata():
    def fetcher(ids: list[str]) -> dict[str, str]:
        assert ids == ["sub-1", "sub-2"]
        return {"sub-1": "SELECT email FROM dbo.Recipients WHERE token='abc123'"}

    bridge = ReportServerDbBridge(
        connection_string="Server=.;Database=ReportServer;User ID=sa;Password=secret;",
        query_fetcher=fetcher,
    )

    merged = bridge.merge_into_subscriptions(_subscriptions_payload())
    payload = merged["subscriptions"]
    report = merged["report"]

    sub1 = payload["subscriptions"][0]
    sub2 = payload["subscriptions"][1]

    assert sub1["DbQueryMetadata"]["query_source"] == "reportserver_db"
    assert "Recipients" in sub1["DbQueryMetadata"]["query_text"]
    assert "token=***" in sub1["DbQueryMetadata"]["query_text_redacted"]
    assert "DbQueryMetadata" not in sub2

    assert report["merged_count"] == 1
    assert report["data_driven_total"] == 2
    assert "Password=***" in report["connection"]


def test_redaction_helpers():
    conn = "Server=tcp:x;Database=ReportServer;User ID=admin;Pwd=verysecret;"
    sql = "SELECT * FROM x WHERE email='john@contoso.com' AND api_key='abcdef'"

    assert "Pwd=***" in ReportServerDbBridge.redact_connection_string(conn)
    redacted_sql = ReportServerDbBridge.redact_text(sql)
    assert "***@***" in redacted_sql
    assert "api_key=***" in redacted_sql
