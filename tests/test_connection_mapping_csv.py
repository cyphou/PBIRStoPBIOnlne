import csv
import json

from pbi_import.connection_mapping_csv import (
    build_online_inventory,
    write_connection_endpoint_csv,
    write_connection_mapping_csv,
)


class DummyPbiClient:
    def list_gateways(self):
        return [{"id": "gw-1", "name": "Gateway A"}]

    def list_gateway_datasources(self, gateway_id):
        assert gateway_id == "gw-1"
        return [{"id": "ods-1", "datasourceName": "SalesDS"}]


def test_build_online_inventory_single_gateway():
    client = DummyPbiClient()
    gateways, by_gateway = build_online_inventory(client, gateway_id="gw-1")
    assert gateways == [{"id": "gw-1", "name": "Gateway A"}]
    assert by_gateway["gw-1"][0]["id"] == "ods-1"


def test_write_connection_mapping_csv_suggest_and_mapped(tmp_path):
    datasources = {
        "shared_datasources": [
            {
                "Name": "SalesDS",
                "Extension": "SQL",
                "ConnectString": "Server=tcp:db.local;Database=DW;",
            },
            {
                "Name": "OtherDS",
                "Extension": "SQL",
                "ConnectString": "Server=tcp:db2.local;Database=DW2;User ID=admin;Password=secret;",
            },
        ],
        "embedded_datasources": [
            {
                "item_name": "SalesDS",
                "item_path": "/Sales",
                "datasource": {
                    "Extension": "SQL",
                    "ConnectString": "Server=tcp:db.local;Database=DW;",
                },
            }
        ],
    }
    mapping = {
        "OtherDS": {
            "gateway_id": "gw-1",
            "datasource_ids": ["ods-9"],
        }
    }

    out = tmp_path / "connection_mapping.csv"
    summary = write_connection_mapping_csv(
        datasources=datasources,
        output_path=out,
        mapping=mapping,
        online_gateways=[{"id": "gw-1"}],
        online_datasources_by_gateway={
            "gw-1": [{"id": "ods-1", "datasourceName": "SalesDS"}],
        },
    )

    assert out.exists()
    assert summary == {"total": 3, "mapped": 1, "suggested": 2, "unmapped": 0}

    with out.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    by_name = {r["item_name"] + ":" + r["source_type"]: r for r in rows}
    assert by_name["OtherDS:shared"]["mapping_status"] == "mapped"
    assert by_name["SalesDS:shared"]["mapping_status"] == "suggested"
    assert by_name["SalesDS:shared"]["suggested_datasource_id"] == "ods-1"
    # Ensure sensitive values are redacted when present.
    assert "<redacted>" in by_name["OtherDS:shared"]["connection_string_preview"]

    # Field for mapped datasource ids is JSON-encoded.
    assert json.loads(by_name["OtherDS:shared"]["mapped_datasource_ids"]) == ["ods-9"]


def test_write_connection_endpoint_csv_grouped(tmp_path):
    datasources = {
        "shared_datasources": [
            {
                "Name": "SalesDS",
                "Extension": "SQL",
                "ConnectString": "Server=tcp:db.local;Database=DW;",
            },
            {
                "Name": "SalesDS_Copy",
                "Extension": "SQL",
                "ConnectString": "Server=tcp:db.local;Database=DW;",
            },
        ],
        "embedded_datasources": [],
    }
    mapping = {
        "SalesDS": {
            "gateway_id": "gw-1",
            "datasource_ids": ["ods-1"],
        }
    }

    out = tmp_path / "connection_mapping_by_endpoint.csv"
    summary = write_connection_endpoint_csv(
        datasources=datasources,
        output_path=out,
        mapping=mapping,
        online_gateways=[{"id": "gw-1"}],
        online_datasources_by_gateway={
            "gw-1": [{"id": "ods-1", "datasourceName": "SalesDS"}],
        },
    )

    assert out.exists()
    assert summary == {"total_endpoints": 1, "total_occurrences": 2}

    with out.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 1
    row = rows[0]
    assert row["server"] == "tcp:db.local"
    assert row["database"] == "DW"
    assert row["occurrences"] == "2"
    assert row["mapped_items"] == "1"
