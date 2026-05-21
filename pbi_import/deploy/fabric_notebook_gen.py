"""
Fabric Notebook Generator — generates Python/PySpark notebooks for Fabric.

Creates notebook JSON definitions that automate data movement, transformation,
and validation tasks within Fabric workspaces.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class FabricNotebookGen:
    """Generate Fabric notebook definitions for migration automation."""

    def generate_data_copy_notebook(
        self,
        source_connection: str,
        target_lakehouse: str,
        tables: list[str],
        notebook_name: str = "data_copy",
    ) -> dict:
        """Generate a notebook that copies data from a SQL source to a lakehouse.

        Args:
            source_connection: JDBC/ODBC connection string for source.
            target_lakehouse: target lakehouse name.
            tables: list of table names to copy.
            notebook_name: notebook display name.
        """
        cells: list[dict] = [
            self._markdown_cell(
                f"# Data Copy: {target_lakehouse}\n\n"
                f"Auto-generated notebook to copy {len(tables)} tables "
                f"from source to Fabric Lakehouse."
            ),
            self._code_cell(
                "# Configuration\n"
                f'source_connection = "{source_connection}"\n'
                f'target_lakehouse = "{target_lakehouse}"\n'
                f"tables = {json.dumps(tables)}"
            ),
            self._code_cell(
                "# Copy tables\n"
                "for table_name in tables:\n"
                "    print(f'Copying {table_name}...')\n"
                "    df = spark.read.format('jdbc').options(\n"
                "        url=source_connection,\n"
                "        dbtable=table_name,\n"
                "    ).load()\n"
                "    \n"
                "    # Write to lakehouse as Delta table\n"
                "    df.write.format('delta').mode('overwrite').saveAsTable(\n"
                "        f'{target_lakehouse}.{table_name}'\n"
                "    )\n"
                "    print(f'  → {df.count()} rows copied')\n"
                "\n"
                "print('Data copy complete!')"
            ),
        ]

        notebook = self._build_notebook(notebook_name, cells)
        logger.info("Generated data copy notebook: %s (%d tables)", notebook_name, len(tables))
        return notebook

    def generate_validation_notebook(
        self,
        source_connection: str,
        target_lakehouse: str,
        tables: list[str],
        notebook_name: str = "data_validation",
    ) -> dict:
        """Generate a notebook that validates row counts between source and target."""
        cells: list[dict] = [
            self._markdown_cell(
                f"# Data Validation: {target_lakehouse}\n\n"
                "Validates row counts between source and Fabric Lakehouse tables."
            ),
            self._code_cell(
                "# Configuration\n"
                f'source_connection = "{source_connection}"\n'
                f'target_lakehouse = "{target_lakehouse}"\n'
                f"tables = {json.dumps(tables)}"
            ),
            self._code_cell(
                "# Validate row counts\n"
                "results = []\n"
                "for table_name in tables:\n"
                "    source_df = spark.read.format('jdbc').options(\n"
                "        url=source_connection, dbtable=table_name\n"
                "    ).load()\n"
                "    source_count = source_df.count()\n"
                "    \n"
                "    target_df = spark.table(f'{target_lakehouse}.{table_name}')\n"
                "    target_count = target_df.count()\n"
                "    \n"
                "    match = source_count == target_count\n"
                "    results.append({\n"
                "        'table': table_name,\n"
                "        'source_rows': source_count,\n"
                "        'target_rows': target_count,\n"
                "        'match': match\n"
                "    })\n"
                "    status = '✓' if match else '✗'\n"
                "    print(f'{status} {table_name}: {source_count} → {target_count}')\n"
                "\n"
                "# Summary\n"
                "passed = sum(1 for r in results if r['match'])\n"
                "print(f'\\nValidation: {passed}/{len(results)} tables match')"
            ),
        ]

        notebook = self._build_notebook(notebook_name, cells)
        logger.info("Generated validation notebook: %s", notebook_name)
        return notebook

    def save(self, output_dir: str, notebook: dict, name: str | None = None) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        fname = name or notebook.get("name", "notebook")
        path = out / f"{fname}.ipynb"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(notebook, f, indent=2)
        return path

    @staticmethod
    def _build_notebook(name: str, cells: list[dict]) -> dict:
        """Build a Jupyter/Fabric notebook structure."""
        return {
            "name": name,
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {
                "language_info": {"name": "python"},
                "kernel_info": {"name": "synapse_pyspark"},
                "trident": {"lakehouse": {}},
            },
            "cells": cells,
        }

    @staticmethod
    def _code_cell(source: str) -> dict:
        return {
            "cell_type": "code",
            "source": [source],
            "metadata": {},
            "outputs": [],
            "execution_count": None,
        }

    @staticmethod
    def _markdown_cell(source: str) -> dict:
        return {
            "cell_type": "markdown",
            "source": [source],
            "metadata": {},
        }
