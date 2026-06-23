"""Auto-create PBI gateway datasources from PBIRS shared datasources (.rds).

Existing ``GatewayMapper`` matches *pre-existing* datasources by mapping
file. This module goes one step further: it parses each datasource's
connection string, infers the gateway data source type, and creates the
missing datasource on the chosen gateway via REST.

Requires a ``pbi_client`` exposing:
    * ``list_gateways()``
    * ``list_gateway_datasources(gateway_id)``
    * ``create_gateway_datasource(gateway_id, payload)``
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_CONN_PARSERS = {
    "sql": re.compile(
        r"(?:server|data source)\s*=\s*(?P<server>[^;]+)\s*;.*?"
        r"(?:database|initial catalog)\s*=\s*(?P<database>[^;]+)",
        re.IGNORECASE,
    ),
    "oracle": re.compile(r"(?:data source|server)\s*=\s*(?P<server>[^;]+)", re.IGNORECASE),
    "odbc": re.compile(r"dsn\s*=\s*(?P<dsn>[^;]+)", re.IGNORECASE),
}


def _detect_kind(provider: str, conn: str) -> str:
    p = (provider or "").lower()
    if "msolap" in p or "analysis services" in p:
        return "AnalysisServices"
    if "sqlncli" in p or "sqlserver" in p or "mssql" in p or "system.data.sqlclient" in p:
        return "Sql"
    if "oracle" in p:
        return "Oracle"
    if "odbc" in p:
        return "OData"
    if "postgres" in p:
        return "PostgreSql"
    if "mysql" in p:
        return "MySql"
    if "snowflake" in p:
        return "Snowflake"
    if "http" in conn[:8].lower():
        return "Web"
    return "Sql"


def parse_rds(rds_payload: dict) -> dict[str, Any]:
    """Pull connection info out of a PBIRS shared datasource (.rds) dict."""
    provider = rds_payload.get("Extension") or rds_payload.get("Provider") or ""
    conn = rds_payload.get("ConnectString") or rds_payload.get("ConnectionString") or ""
    kind = _detect_kind(provider, conn)
    parsed: dict[str, Any] = {"kind": kind, "provider": provider, "connectionString": conn}
    parser = _CONN_PARSERS.get(kind.lower()) or _CONN_PARSERS["sql"]
    m = parser.search(conn)
    if m:
        parsed.update(m.groupdict())
    return parsed


class GatewayAutoCreator:
    """Create missing gateway datasources for every shared datasource."""

    def __init__(self, pbi_client: Any, default_gateway_id: str | None = None):
        self.client = pbi_client
        self.default_gateway_id = default_gateway_id

    def plan(
        self,
        datasources: list[dict],
        gateway_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Build the per-datasource creation plan without making any calls."""
        gw = gateway_id or self.default_gateway_id
        if not gw:
            raise ValueError("gateway_id is required")
        existing = {
            ds.get("datasourceName"): ds
            for ds in self.client.list_gateway_datasources(gw)
        }
        plans: list[dict[str, Any]] = []
        for ds in datasources:
            name = ds.get("Name") or ds.get("name") or "datasource"
            parsed = parse_rds(ds)
            already = name in existing
            plans.append({
                "name": name,
                "gateway_id": gw,
                "parsed": parsed,
                "exists": already,
                "action": "skip" if already else "create",
            })
        return plans

    def execute(
        self,
        datasources: list[dict],
        gateway_id: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Run the plan; create missing gateway datasources."""
        results: dict[str, list] = {"created": [], "skipped": [], "failed": []}
        for entry in self.plan(datasources, gateway_id=gateway_id):
            if entry["action"] == "skip":
                results["skipped"].append({"name": entry["name"], "reason": "already exists"})
                continue
            payload = self._build_payload(entry)
            if dry_run:
                results["created"].append({"name": entry["name"], "dry_run": True, "payload": payload})
                continue
            try:
                resp = self.client.create_gateway_datasource(entry["gateway_id"], payload)
                results["created"].append({"name": entry["name"], "datasource_id": resp.get("id")})
            except Exception as e:  # noqa: BLE001
                logger.warning("Gateway datasource %s failed: %s", entry["name"], e)
                results["failed"].append({"name": entry["name"], "error": str(e)})
        return results

    def write_mapping(
        self,
        results: dict[str, Any],
        path: str | Path,
        gateway_id: str | None = None,
    ) -> Path:
        """Emit a ``gateway_mapping.json`` consumable by ``GatewayMapper``."""
        gw = gateway_id or self.default_gateway_id
        mapping: dict[str, dict] = {}
        for entry in results.get("created", []):
            if entry.get("dry_run"):
                ds_id = f"pending-{entry['name']}"
            else:
                ds_id = entry.get("datasource_id") or f"pending-{entry['name']}"
            mapping[entry["name"]] = {
                "gateway_id": gw,
                "datasource_ids": [ds_id],
            }
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2)
        logger.info("Gateway mapping written: %s (%d entries)", p, len(mapping))
        return p

    def _build_payload(self, entry: dict) -> dict[str, Any]:
        parsed = entry["parsed"]
        details = {k: v for k, v in parsed.items() if k not in {"kind", "provider", "connectionString"}}
        return {
            "datasourceName": entry["name"],
            "datasourceType": parsed["kind"],
            "connectionDetails": json.dumps(details) if details else parsed["connectionString"],
            "credentialDetails": {
                "credentialType": "Windows",
                "encryptedConnection": "Encrypted",
                "encryptionAlgorithm": "None",
                "privacyLevel": "Organizational",
            },
        }
