"""
Mapping Generator — produces CSV mapping templates from extracted PBIRS data.

Generates three CSV files to help plan the migration:
  1. folders_mapping.csv  — PBIRS folders → target PBI workspace mapping
  2. users_mapping.csv    — PBIRS principals (users/groups) → Azure AD identity mapping
  3. connections_mapping.csv — PBIRS datasource connections → gateway datasource mapping

The user fills in the "target" columns, then feeds the CSVs back into the
import phase for automated workspace creation, permission assignment, and
gateway binding.
"""

import csv
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MappingGenerator:
    """Generate CSV mapping templates from PBIRS catalog and security data."""

    def __init__(
        self,
        catalog: dict,
        permissions: dict,
        datasources: dict,
        security: dict | None = None,
    ):
        self.catalog = catalog
        self.permissions = permissions
        self.datasources = datasources
        self.security = security or {}

    def generate_all(self, output_dir: str) -> dict[str, Path]:
        """Generate all three mapping CSVs.

        Returns a dict of {mapping_name: file_path}.
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        paths = {
            "folders": self._generate_folders_csv(out),
            "users": self._generate_users_csv(out),
            "connections": self._generate_connections_csv(out),
        }

        logger.info(
            "Generated mapping CSVs: %s",
            ", ".join(f"{k}={v.name}" for k, v in paths.items()),
        )
        return paths

    # ------------------------------------------------------------------
    # 1. Folders mapping
    # ------------------------------------------------------------------

    def _generate_folders_csv(self, output_dir: Path) -> Path:
        """Generate folders_mapping.csv.

        Columns:
            folder_path          — PBIRS folder path (e.g. /Finance/Reports)
            item_count           — number of items in this folder
            content_types        — comma-separated content types in folder
            target_workspace     — (TO FILL) PBI Online workspace name
            notes                — (TO FILL) any migration notes
        """
        items = self.catalog.get("items", [])

        # Collect folder info
        folder_data: dict[str, dict[str, Any]] = {}
        for item in items:
            path = item.get("Path", "")
            # Derive folder from item path
            parts = path.rstrip("/").rsplit("/", 1)
            folder = parts[0] if len(parts) > 1 else "/"
            if not folder:
                folder = "/"

            if folder not in folder_data:
                folder_data[folder] = {"count": 0, "types": set()}
            folder_data[folder]["count"] += 1
            folder_data[folder]["types"].add(item.get("Type", "Unknown"))

        # Also include explicit folders from catalog
        for folder in self.catalog.get("folders", []):
            folder_path = folder.get("path", "")
            if folder_path and folder_path not in folder_data:
                folder_data[folder_path] = {"count": 0, "types": set()}

        csv_path = output_dir / "folders_mapping.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "folder_path",
                "item_count",
                "content_types",
                "target_workspace",
                "notes",
            ])
            for folder_path in sorted(folder_data):
                info = folder_data[folder_path]
                writer.writerow([
                    folder_path,
                    info["count"],
                    ", ".join(sorted(info["types"])),
                    "",  # target_workspace — user fills this in
                    "",  # notes
                ])

        logger.info("Folders mapping: %d folders → %s", len(folder_data), csv_path)
        return csv_path

    # ------------------------------------------------------------------
    # 2. Users / principals mapping
    # ------------------------------------------------------------------

    def _generate_users_csv(self, output_dir: Path) -> Path:
        """Generate users_mapping.csv.

        Columns:
            pbirs_principal      — DOMAIN\\user or email as seen in PBIRS
            type                 — ad_account / email / builtin / local
            domain               — AD domain (if applicable)
            ssrs_roles           — comma-separated SSRS roles held
            item_count           — number of items this principal has access to
            target_azure_ad      — (TO FILL) Azure AD UPN or group email
            target_pbi_role      — (pre-filled suggestion) PBI workspace role
            notes                — (TO FILL)
        """
        # Collect unique principals from permissions and security data
        principals = self._collect_principals()

        csv_path = output_dir / "users_mapping.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "pbirs_principal",
                "type",
                "domain",
                "ssrs_roles",
                "item_count",
                "target_azure_ad",
                "target_pbi_role",
                "notes",
            ])
            for p in sorted(principals, key=lambda x: x["name"]):
                suggested_role = self._suggest_pbi_role(p.get("ssrs_roles", []))
                writer.writerow([
                    p["name"],
                    p.get("type", "unknown"),
                    p.get("domain", ""),
                    ", ".join(p.get("ssrs_roles", [])),
                    p.get("item_count", 0),
                    "",  # target_azure_ad — user fills this in
                    suggested_role,
                    "",  # notes
                ])

        logger.info("Users mapping: %d principals → %s", len(principals), csv_path)
        return csv_path

    def _collect_principals(self) -> list[dict]:
        """Collect unique principals from permissions and security data."""
        seen: dict[str, dict[str, Any]] = {}

        # From security extractor (preferred — richer data)
        for p in self.security.get("principals", []):
            name = p.get("name", "")
            if name:
                seen[name] = {
                    "name": name,
                    "type": p.get("type", "unknown"),
                    "domain": p.get("domain", ""),
                    "ssrs_roles": p.get("ssrs_roles", []),
                    "item_count": 0,
                }

        # From permission extractor (fallback)
        for item_policy in self.permissions.get("item_policies", []):
            for policy in item_policy.get("policies", []):
                name = policy.get("GroupUserName", "")
                if not name:
                    continue
                if name not in seen:
                    seen[name] = {
                        "name": name,
                        "type": self._classify_type(name),
                        "domain": name.split("\\")[0] if "\\" in name else "",
                        "ssrs_roles": [],
                        "item_count": 0,
                    }
                for role in policy.get("Roles", []):
                    role_name = role.get("Name", "")
                    if role_name and role_name not in seen[name]["ssrs_roles"]:
                        seen[name]["ssrs_roles"].append(role_name)
                seen[name]["item_count"] += 1

        # From system policies
        for policy in self.permissions.get("system_policies", []):
            name = policy.get("GroupUserName", "")
            if name and name not in seen:
                seen[name] = {
                    "name": name,
                    "type": self._classify_type(name),
                    "domain": name.split("\\")[0] if "\\" in name else "",
                    "ssrs_roles": [],
                    "item_count": 0,
                }
                for role in policy.get("Roles", []):
                    role_name = role.get("Name", "")
                    if role_name:
                        seen[name]["ssrs_roles"].append(role_name)

        # Count items per principal from effective permissions
        for entry in self.security.get("effective_permissions", []):
            name = entry.get("principal", "")
            if name in seen:
                seen[name]["item_count"] += 1

        return list(seen.values())

    # ------------------------------------------------------------------
    # 3. Connections / datasource mapping
    # ------------------------------------------------------------------

    def _generate_connections_csv(self, output_dir: Path) -> Path:
        """Generate connections_mapping.csv.

        Columns:
            report_name          — report that uses this connection
            report_path          — full PBIRS path
            report_type          — PowerBIReport / Report
            datasource_type      — SQL / Oracle / ODBC etc.
            connection_string    — original connection string
            server_name          — extracted server/host name
            database_name        — extracted database/catalog name
            needs_gateway        — yes/no
            target_gateway_id    — (TO FILL) PBI Online gateway ID
            target_datasource_id — (TO FILL) gateway datasource ID
            notes                — (TO FILL)
        """
        rows: list[dict[str, str]] = []

        # Embedded datasources (per-report)
        for entry in self.datasources.get("embedded_datasources", []):
            ds = entry.get("datasource", {})
            conn_str = ds.get("ConnectionString", "")
            ds_type = ds.get("DataSourceType", "")
            server, database = self._parse_connection_string(conn_str)
            needs_gw = self._needs_gateway(conn_str)

            rows.append({
                "report_name": entry.get("item_name", ""),
                "report_path": entry.get("item_path", ""),
                "report_type": entry.get("item_type", ""),
                "datasource_type": ds_type,
                "connection_string": conn_str,
                "server_name": server,
                "database_name": database,
                "needs_gateway": "yes" if needs_gw else "no",
            })

        # Shared datasources
        for ds in self.datasources.get("shared_datasources", []):
            conn_str = ds.get("ConnectionString", "")
            ds_type = ds.get("DataSourceType", ds.get("Type", ""))
            server, database = self._parse_connection_string(conn_str)
            needs_gw = self._needs_gateway(conn_str)

            rows.append({
                "report_name": f"[Shared] {ds.get('Name', '')}",
                "report_path": ds.get("Path", ""),
                "report_type": "DataSource",
                "datasource_type": ds_type,
                "connection_string": conn_str,
                "server_name": server,
                "database_name": database,
                "needs_gateway": "yes" if needs_gw else "no",
            })

        # Deduplicate by (report_path, connection_string)
        unique_rows = self._deduplicate_connections(rows)

        csv_path = output_dir / "connections_mapping.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "report_name",
                "report_path",
                "report_type",
                "datasource_type",
                "connection_string",
                "server_name",
                "database_name",
                "needs_gateway",
                "target_gateway_id",
                "target_datasource_id",
                "notes",
            ])
            for row in unique_rows:
                writer.writerow([
                    row["report_name"],
                    row["report_path"],
                    row["report_type"],
                    row["datasource_type"],
                    row["connection_string"],
                    row["server_name"],
                    row["database_name"],
                    row["needs_gateway"],
                    "",  # target_gateway_id
                    "",  # target_datasource_id
                    "",  # notes
                ])

        logger.info("Connections mapping: %d connections → %s", len(unique_rows), csv_path)
        return csv_path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_type(name: str) -> str:
        """Classify a principal name into a type."""
        if "\\" in name:
            return "ad_account"
        if "@" in name:
            return "email"
        if name.startswith("BUILTIN"):
            return "builtin"
        return "local"

    ROLE_MAP: dict[str, str] = {
        "Browser": "Viewer",
        "Content Manager": "Admin",
        "My Reports": "Contributor",
        "Publisher": "Contributor",
        "Report Builder": "Contributor",
        "System Administrator": "Admin",
        "System User": "Viewer",
    }

    @classmethod
    def _suggest_pbi_role(cls, ssrs_roles: list[str]) -> str:
        """Suggest the highest-privilege PBI role from SSRS roles."""
        priority = ["Admin", "Member", "Contributor", "Viewer"]
        mapped = {cls.ROLE_MAP.get(r, "Viewer") for r in ssrs_roles}
        for role in priority:
            if role in mapped:
                return role
        return "Viewer"

    CLOUD_MARKERS = (
        ".database.windows.net",
        ".sql.azuresynapse.net",
        ".blob.core.windows.net",
        ".dfs.core.windows.net",
        ".sharepoint.com",
        ".onmicrosoft.com",
        ".cosmos.azure.com",
        ".table.core.windows.net",
        ".queue.core.windows.net",
    )

    @classmethod
    def _needs_gateway(cls, conn_str: str | None) -> bool:
        """Determine if a connection string requires an on-premises gateway."""
        if not conn_str:
            return False
        lower = conn_str.lower()
        # Cloud sources don't need a gateway
        if any(marker in lower for marker in cls.CLOUD_MARKERS):
            return False
        # If it has a server/host reference, likely on-prem
        if any(kw in lower for kw in ("data source=", "server=", "host=")):
            return True
        return False

    @staticmethod
    def _parse_connection_string(conn_str: str | None) -> tuple[str, str]:
        """Extract server and database from a connection string.

        Handles common formats:
          Data Source=server;Initial Catalog=db
          Server=server;Database=db
          Host=server;Database=db
        """
        if not conn_str:
            return "", ""

        server = ""
        database = ""

        parts = conn_str.split(";")
        for part in parts:
            kv = part.strip().split("=", 1)
            if len(kv) != 2:
                continue
            key = kv[0].strip().lower()
            value = kv[1].strip()

            if key in ("data source", "server", "host", "addr", "address"):
                server = value
            elif key in ("initial catalog", "database", "dbname", "db"):
                database = value

        return server, database

    @staticmethod
    def _deduplicate_connections(rows: list[dict[str, str]]) -> list[dict[str, str]]:
        """Remove duplicate connections (same report + same connection string)."""
        seen: set[tuple[str, str]] = set()
        unique: list[dict[str, str]] = []
        for row in rows:
            key = (row["report_path"], row["connection_string"])
            if key not in seen:
                seen.add(key)
                unique.append(row)
        return unique
