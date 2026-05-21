"""
Connection Transformer — rewrites on-prem connection strings for cloud targets.

Supports SQL Server → Azure SQL / Synapse / Fabric, Oracle → Azure Database,
and other common transformations. Rules-based with a configurable mapping file.
"""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Built-in transformation rules
_DEFAULT_RULES: list[dict] = [
    {
        "name": "SQL Server → Azure SQL",
        "match": r"Data Source=(?P<server>[^;]+);.*Initial Catalog=(?P<db>[^;]+)",
        "provider_match": r"System\.Data\.SqlClient|Microsoft\.Data\.SqlClient",
        "transform": "Server=tcp:{server}.database.windows.net,1433;Initial Catalog={db};Encrypt=True;TrustServerCertificate=False;Authentication=Active Directory Default;",
    },
    {
        "name": "Oracle → Azure Database for PostgreSQL",
        "match": r"Data Source=(?P<server>[^;]+)",
        "provider_match": r"Oracle|ODP\.NET",
        "transform": "Host={server}.postgres.database.azure.com;Port=5432;Database={db};SSL Mode=Require;",
    },
    {
        "name": "MySQL → Azure Database for MySQL",
        "match": r"Server=(?P<server>[^;]+);.*Database=(?P<db>[^;]+)",
        "provider_match": r"MySql",
        "transform": "Server={server}.mysql.database.azure.com;Port=3306;Database={db};SSL Mode=Required;",
    },
]


class ConnectionTransformer:
    """Transform on-prem connection strings to cloud equivalents."""

    def __init__(self, rules: list[dict] | None = None):
        self.rules = rules or _DEFAULT_RULES

    @classmethod
    def from_file(cls, path: str) -> "ConnectionTransformer":
        """Load transformation rules from a JSON file."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        rules = data if isinstance(data, list) else data.get("rules", [])
        logger.info("Loaded %d connection transform rules", len(rules))
        return cls(rules)

    def transform_all(
        self,
        datasources: list[dict],
        server_map: dict[str, str] | None = None,
    ) -> list[dict]:
        """Transform all datasource connection strings.

        Args:
            datasources: list of datasource dicts with ``ConnectionString`` and ``Provider``.
            server_map: ``{on_prem_server: cloud_server}`` overrides.
        """
        results: list[dict] = []
        smap = server_map or {}

        for ds in datasources:
            original = ds.get("ConnectionString", "")
            provider = ds.get("Provider", ds.get("DataSourceType", ""))
            transformed = self._transform(original, provider, smap)

            results.append({
                "name": ds.get("Name", ""),
                "original": original,
                "transformed": transformed["connection_string"],
                "rule_applied": transformed["rule"],
                "changed": transformed["changed"],
            })

        changed = sum(1 for r in results if r["changed"])
        logger.info("Connection transform: %d/%d changed", changed, len(results))
        return results

    def save_results(self, output_dir: str, results: list[dict]) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "connection_transforms.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        return path

    def _transform(
        self,
        conn_str: str,
        provider: str,
        server_map: dict[str, str],
    ) -> dict:
        """Apply the first matching rule to a connection string."""
        for rule in self.rules:
            # Check provider match
            provider_pattern = rule.get("provider_match", "")
            if provider_pattern and not re.search(provider_pattern, provider, re.IGNORECASE):
                continue

            # Check connection string match
            match = re.search(rule["match"], conn_str, re.IGNORECASE)
            if not match:
                continue

            groups = match.groupdict()
            # Apply server map overrides
            if "server" in groups and groups["server"] in server_map:
                groups["server"] = server_map[groups["server"]]

            # Fill template
            try:
                new_conn = rule["transform"].format(**groups)
                return {
                    "connection_string": new_conn,
                    "rule": rule["name"],
                    "changed": True,
                }
            except KeyError:
                continue

        return {"connection_string": conn_str, "rule": None, "changed": False}
