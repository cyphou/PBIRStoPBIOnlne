"""
Dataflow Gen2 Creator — generates Dataflow Gen2 definitions for Fabric.

Creates dataflow definitions that move and transform data from PBIRS
datasources into Fabric lakehouses and warehouses.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class DataflowGen2:
    """Generate Dataflow Gen2 definitions for Fabric migration."""

    def generate(
        self,
        datasources: list[dict],
        target_lakehouse: str,
        workspace_id: str,
    ) -> list[dict]:
        """Generate Dataflow Gen2 definitions for datasource migration.

        Args:
            datasources: list of datasource metadata dicts.
            target_lakehouse: destination lakehouse name.
            workspace_id: target Fabric workspace ID.
        """
        dataflows: list[dict] = []

        for ds in datasources:
            name = ds.get("Name", "")
            conn_str = ds.get("ConnectionString", "")
            ds_type = ds.get("DataSourceType", ds.get("Provider", ""))

            # Generate M (Power Query) expression
            m_expression = self._generate_m_query(name, conn_str, ds_type)

            dataflow = {
                "displayName": f"DF_{name}",
                "description": f"Migrated dataflow from PBIRS datasource: {name}",
                "workspace_id": workspace_id,
                "target_lakehouse": target_lakehouse,
                "source": {
                    "name": name,
                    "connection_string": conn_str,
                    "type": ds_type,
                },
                "mashup": {
                    "document": m_expression,
                    "queryGroups": [
                        {"id": "migration", "name": "Migration", "order": 0},
                    ],
                },
                "destination": {
                    "type": "Lakehouse",
                    "lakehouse": target_lakehouse,
                    "mode": "Replace",
                },
            }
            dataflows.append(dataflow)

        logger.info(
            "Generated %d Dataflow Gen2 definitions for workspace %s",
            len(dataflows), workspace_id,
        )
        return dataflows

    def save(self, output_dir: str, dataflows: list[dict]) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "dataflow_gen2_definitions.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dataflows, f, indent=2)
        return path

    def _generate_m_query(self, name: str, conn_str: str, ds_type: str) -> str:
        """Generate a Power Query M expression for data loading."""
        safe_name = name.replace(" ", "_").replace("-", "_")

        if "sql" in ds_type.lower() or "sqlclient" in ds_type.lower():
            return self._sql_m_query(safe_name, conn_str)
        elif "oracle" in ds_type.lower():
            return self._oracle_m_query(safe_name, conn_str)
        elif "oledb" in ds_type.lower():
            return self._oledb_m_query(safe_name, conn_str)
        else:
            return self._generic_m_query(safe_name, conn_str, ds_type)

    @staticmethod
    def _sql_m_query(name: str, conn_str: str) -> str:
        return (
            f'let\n'
            f'    Source = Sql.Database("{conn_str}"),\n'
            f'    {name} = Source{{[Name="{name}"]}}[Data]\n'
            f'in\n'
            f'    {name}'
        )

    @staticmethod
    def _oracle_m_query(name: str, conn_str: str) -> str:
        return (
            f'let\n'
            f'    Source = Oracle.Database("{conn_str}"),\n'
            f'    {name} = Source{{[Name="{name}"]}}[Data]\n'
            f'in\n'
            f'    {name}'
        )

    @staticmethod
    def _oledb_m_query(name: str, conn_str: str) -> str:
        return (
            f'let\n'
            f'    Source = OleDb.DataSource("{conn_str}"),\n'
            f'    {name} = Source{{[Name="{name}"]}}[Data]\n'
            f'in\n'
            f'    {name}'
        )

    @staticmethod
    def _generic_m_query(name: str, conn_str: str, ds_type: str) -> str:
        return (
            f'// Source type: {ds_type}\n'
            f'let\n'
            f'    Source = "{conn_str}",\n'
            f'    {name} = Source\n'
            f'in\n'
            f'    {name}'
        )
