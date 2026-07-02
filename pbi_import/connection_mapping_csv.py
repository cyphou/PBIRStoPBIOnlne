"""Generate CSV inventory for PBIRS connections and PBI Online mapping guidance."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

from pbi_import.gateway_autocreate import parse_rds

logger = logging.getLogger(__name__)


def write_connection_mapping_csv(
    datasources: dict[str, Any],
    output_path: str | Path,
    mapping: dict[str, Any] | None = None,
    online_gateways: list[dict] | None = None,
    online_datasources_by_gateway: dict[str, list[dict]] | None = None,
) -> dict[str, int]:
    """Write a CSV showing PBIRS connections and how to map them in PBI Online."""
    rows = _build_rows(
        datasources=datasources,
        mapping=mapping or {},
        online_gateways=online_gateways or [],
        online_datasources_by_gateway=online_datasources_by_gateway or {},
    )

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_fieldnames())
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "total": len(rows),
        "mapped": sum(1 for r in rows if r["mapping_status"] == "mapped"),
        "suggested": sum(1 for r in rows if r["mapping_status"] == "suggested"),
        "unmapped": sum(1 for r in rows if r["mapping_status"] == "unmapped"),
    }
    logger.info("Connection mapping CSV written: %s (rows=%d)", path, len(rows))
    return summary


def write_connection_endpoint_csv(
    datasources: dict[str, Any],
    output_path: str | Path,
    mapping: dict[str, Any] | None = None,
    online_gateways: list[dict] | None = None,
    online_datasources_by_gateway: dict[str, list[dict]] | None = None,
) -> dict[str, int]:
    """Write a grouped CSV by unique connection endpoint (kind/server/database)."""
    rows = _build_rows(
        datasources=datasources,
        mapping=mapping or {},
        online_gateways=online_gateways or [],
        online_datasources_by_gateway=online_datasources_by_gateway or {},
    )

    grouped: dict[tuple[str, str, str, str], list[dict[str, str]]] = {}
    for row in rows:
        key = (
            row.get("connection_kind", ""),
            row.get("provider", ""),
            row.get("server", ""),
            row.get("database", ""),
        )
        grouped.setdefault(key, []).append(row)

    endpoint_rows: list[dict[str, str]] = []
    for key, members in grouped.items():
        connection_kind, provider, server, database = key
        item_names = sorted({m.get("item_name", "") for m in members if m.get("item_name")})
        mapped = sum(1 for m in members if m.get("mapping_status") == "mapped")
        suggested = sum(1 for m in members if m.get("mapping_status") == "suggested")
        unmapped = sum(1 for m in members if m.get("mapping_status") == "unmapped")
        mapped_gw = sorted({m.get("mapped_gateway_id", "") for m in members if m.get("mapped_gateway_id")})
        suggested_gw = sorted({m.get("suggested_gateway_id", "") for m in members if m.get("suggested_gateway_id")})
        suggested_ds_names = sorted({m.get("suggested_datasource_name", "") for m in members if m.get("suggested_datasource_name")})
        hint = "All items mapped."
        if unmapped > 0:
            hint = "Some items unmapped. Create or map datasource for this endpoint in gateway_mapping JSON."
        elif suggested > 0:
            hint = "Suggested matches available. Confirm and map all items to reduce manual work."

        endpoint_rows.append({
            "connection_kind": connection_kind,
            "provider": provider,
            "server": server,
            "database": database,
            "occurrences": str(len(members)),
            "distinct_items": str(len(item_names)),
            "item_names": "|".join(item_names),
            "mapped_items": str(mapped),
            "suggested_items": str(suggested),
            "unmapped_items": str(unmapped),
            "mapped_gateway_ids": "|".join(mapped_gw),
            "suggested_gateway_ids": "|".join(suggested_gw),
            "suggested_datasource_names": "|".join(suggested_ds_names),
            "mapping_hint": hint,
        })

    endpoint_rows.sort(key=lambda r: (r["server"], r["database"], r["provider"], r["connection_kind"]))

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_endpoint_fieldnames())
        writer.writeheader()
        writer.writerows(endpoint_rows)

    summary = {
        "total_endpoints": len(endpoint_rows),
        "total_occurrences": len(rows),
    }
    logger.info("Connection endpoint CSV written: %s (endpoints=%d)", path, len(endpoint_rows))
    return summary


def build_online_inventory(pbi_client: Any, gateway_id: str | None = None) -> tuple[list[dict], dict[str, list[dict]]]:
    """Collect gateway and datasource inventory from PBI Online."""
    if gateway_id:
        gateways = [g for g in pbi_client.list_gateways() if g.get("id") == gateway_id]
    else:
        gateways = pbi_client.list_gateways()

    by_gateway: dict[str, list[dict]] = {}
    for gw in gateways:
        gw_id = gw.get("id", "")
        if not gw_id:
            continue
        by_gateway[gw_id] = pbi_client.list_gateway_datasources(gw_id)
    return gateways, by_gateway


def _build_rows(
    datasources: dict[str, Any],
    mapping: dict[str, Any],
    online_gateways: list[dict],
    online_datasources_by_gateway: dict[str, list[dict]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    default_gateway_id = _first_gateway_id(online_gateways)

    for ds in datasources.get("shared_datasources", []):
        name = ds.get("Name") or ds.get("name") or ""
        parsed = parse_rds(ds)
        rows.append(
            _row_for_connection(
                source_type="shared",
                item_name=name,
                item_path="",
                provider=str(ds.get("Extension") or ds.get("Provider") or ""),
                parsed=parsed,
                mapping=mapping.get(name),
                default_gateway_id=default_gateway_id,
                online_datasources_by_gateway=online_datasources_by_gateway,
            )
        )

    for ds in datasources.get("embedded_datasources", []):
        item_name = str(ds.get("item_name") or "")
        inner = ds.get("datasource", {}) or {}
        parsed = parse_rds(inner)
        rows.append(
            _row_for_connection(
                source_type="embedded",
                item_name=item_name,
                item_path=str(ds.get("item_path") or ""),
                provider=str(inner.get("DataSourceType") or inner.get("Extension") or inner.get("Provider") or ""),
                parsed=parsed,
                mapping=mapping.get(item_name),
                default_gateway_id=default_gateway_id,
                online_datasources_by_gateway=online_datasources_by_gateway,
            )
        )

    return rows


def _row_for_connection(
    source_type: str,
    item_name: str,
    item_path: str,
    provider: str,
    parsed: dict[str, Any],
    mapping: dict[str, Any] | None,
    default_gateway_id: str,
    online_datasources_by_gateway: dict[str, list[dict]],
) -> dict[str, str]:
    connection_string = str(parsed.get("connectionString") or "")
    mapped_gateway_id = ""
    mapped_datasource_ids = ""
    status = "unmapped"

    if mapping:
        mapped_gateway_id = str(mapping.get("gateway_id") or "")
        mapped_datasource_ids = _json_compact(mapping.get("datasource_ids") or [])
        status = "mapped"

    suggested_gateway_id, suggested_datasource_id, suggested_datasource_name = _find_suggestion(
        item_name,
        mapped_gateway_id or default_gateway_id,
        online_datasources_by_gateway,
    )

    if status == "unmapped" and suggested_datasource_id:
        status = "suggested"

    map_hint = _build_map_hint(
        status=status,
        item_name=item_name,
        suggested_gateway_id=suggested_gateway_id,
        suggested_datasource_id=suggested_datasource_id,
    )

    return {
        "source_type": source_type,
        "item_name": item_name,
        "item_path": item_path,
        "provider": provider,
        "connection_kind": str(parsed.get("kind") or ""),
        "server": str(parsed.get("server") or ""),
        "database": str(parsed.get("database") or ""),
        "connection_string_preview": _redact_connection_string(connection_string),
        "mapping_status": status,
        "mapped_gateway_id": mapped_gateway_id,
        "mapped_datasource_ids": mapped_datasource_ids,
        "suggested_gateway_id": suggested_gateway_id,
        "suggested_datasource_id": suggested_datasource_id,
        "suggested_datasource_name": suggested_datasource_name,
        "mapping_hint": map_hint,
    }


def _find_suggestion(
    item_name: str,
    preferred_gateway_id: str,
    online_datasources_by_gateway: dict[str, list[dict]],
) -> tuple[str, str, str]:
    if preferred_gateway_id and preferred_gateway_id in online_datasources_by_gateway:
        for ds in online_datasources_by_gateway[preferred_gateway_id]:
            ds_name = str(ds.get("datasourceName") or "")
            if ds_name.lower() == item_name.lower():
                return preferred_gateway_id, str(ds.get("id") or ""), ds_name

    for gw_id, items in online_datasources_by_gateway.items():
        for ds in items:
            ds_name = str(ds.get("datasourceName") or "")
            if ds_name.lower() == item_name.lower():
                return gw_id, str(ds.get("id") or ""), ds_name

    return "", "", ""


def _build_map_hint(status: str, item_name: str, suggested_gateway_id: str, suggested_datasource_id: str) -> str:
    if status == "mapped":
        return "Already mapped in gateway mapping JSON."
    if suggested_gateway_id and suggested_datasource_id:
        return (
            "Set gateway_mapping entry: "
            f'"{item_name}": {{"gateway_id": "{suggested_gateway_id}", '
            f'"datasource_ids": ["{suggested_datasource_id}"]}}'
        )
    return "Create datasource in PBI gateway first, then set gateway_id + datasource_ids in mapping JSON."


def _fieldnames() -> list[str]:
    return [
        "source_type",
        "item_name",
        "item_path",
        "provider",
        "connection_kind",
        "server",
        "database",
        "connection_string_preview",
        "mapping_status",
        "mapped_gateway_id",
        "mapped_datasource_ids",
        "suggested_gateway_id",
        "suggested_datasource_id",
        "suggested_datasource_name",
        "mapping_hint",
    ]


def _endpoint_fieldnames() -> list[str]:
    return [
        "connection_kind",
        "provider",
        "server",
        "database",
        "occurrences",
        "distinct_items",
        "item_names",
        "mapped_items",
        "suggested_items",
        "unmapped_items",
        "mapped_gateway_ids",
        "suggested_gateway_ids",
        "suggested_datasource_names",
        "mapping_hint",
    ]


def _json_compact(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True)


def _first_gateway_id(gateways: list[dict]) -> str:
    for gw in gateways:
        gw_id = str(gw.get("id") or "")
        if gw_id:
            return gw_id
    return ""


def _redact_connection_string(value: str) -> str:
    if not value:
        return ""
    lowered = value.lower()
    tokens = ["password=", "pwd=", "user id=", "uid="]
    if any(token in lowered for token in tokens):
        parts = []
        for part in value.split(";"):
            key = part.split("=", 1)[0].strip().lower()
            if key in {"password", "pwd", "user id", "uid"}:
                parts.append(f"{part.split('=', 1)[0]}=<redacted>")
            else:
                parts.append(part)
        return ";".join(parts)
    return value