"""Semantic model snapshot loader.

Loads explicit model artifacts when they are available (for example a pre-
extracted ``model_snapshot.json`` / TMDL-export JSON) and normalizes them for
downstream BPA analysis.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import zipfile


class ModelSnapshotLoader:
    """Find and normalize semantic-model snapshots."""

    CANDIDATE_FILENAMES = (
        "model_snapshot.json",
        "semantic_model.json",
        "model.json",
        "tmdl.json",
    )

    @staticmethod
    def _empty_snapshot(source: str, message: str, model_type: str = "unknown") -> dict[str, Any]:
        return {
            "available": False,
            "source": source,
            "model_type": model_type,
            "message": message,
            "tables": [],
            "measures": [],
            "columns": [],
            "relationships": [],
            "roles": [],
            "calculation_groups": [],
            "annotations": [],
        }

    def load(self, source_path: str) -> dict[str, Any]:
        """Load the best available model snapshot from a file or directory.

        If no explicit snapshot is available, returns a neutral placeholder
        describing the missing model artifact so callers can clearly report
        fallback BPA behavior.
        """
        path = Path(source_path)

        if path.is_file() and path.suffix.lower() == ".pbix":
            return self._load_pbix_snapshot(path)

        candidate = self._resolve_candidate(path)
        if candidate is None:
            return self._empty_snapshot(str(path), "No explicit model snapshot found")

        if candidate.suffix.lower() == ".pbix":
            return self._load_pbix_snapshot(candidate)

        with candidate.open(encoding="utf-8") as f:
            payload = json.load(f)

        return self._normalise(payload, candidate)

    def _load_pbix_snapshot(self, pbix_path: Path) -> dict[str, Any]:
        if not pbix_path.exists():
            return self._empty_snapshot(str(pbix_path), "PBIX file does not exist", model_type="pbix")

        try:
            with zipfile.ZipFile(pbix_path, "r") as archive:
                if "DataModelSchema" not in archive.namelist():
                    return self._empty_snapshot(
                        str(pbix_path),
                        "PBIX does not contain DataModelSchema",
                        model_type="pbix",
                    )

                raw = archive.read("DataModelSchema")
                payload = json.loads(raw.decode("utf-8", errors="replace"))

        except (zipfile.BadZipFile, OSError, json.JSONDecodeError) as exc:
            return self._empty_snapshot(
                str(pbix_path),
                f"Failed to read DataModelSchema: {exc}",
                model_type="pbix",
            )

        normalised = self._normalise(payload, pbix_path)
        normalised["model_type"] = "pbix_datamodelschema"
        normalised["description"] = "Extracted from PBIX DataModelSchema"
        return normalised

    def _resolve_candidate(self, path: Path) -> Path | None:
        if path.is_file() and path.suffix.lower() == ".json":
            return path

        if path.is_file():
            return None

        for name in self.CANDIDATE_FILENAMES:
            direct = path / name
            if direct.exists():
                return direct

        for child in path.rglob("*"):
            if child.is_file() and child.name in self.CANDIDATE_FILENAMES:
                return child

        pbix_dir = path / "powerbi"
        if pbix_dir.exists():
            pbix_files = sorted(pbix_dir.glob("*.pbix"))
            if pbix_files:
                return pbix_files[0]

        pbix_any = sorted(path.rglob("*.pbix"))
        if pbix_any:
            return pbix_any[0]

        return None

    @staticmethod
    def _normalise(payload: Any, candidate: Path) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return ModelSnapshotLoader._empty_snapshot(
                str(candidate),
                "Model snapshot payload was not a JSON object",
            )

        root = payload
        database = root.get("database") if isinstance(root.get("database"), dict) else None
        if database is not None:
            root = database

        model = root.get("model") if isinstance(root.get("model"), dict) else root

        tables_src = model.get("tables", []) if isinstance(model, dict) and isinstance(model.get("tables", []), list) else []
        tables: list[dict[str, Any]] = []
        measures: list[dict[str, Any]] = []
        columns: list[dict[str, Any]] = []
        calculation_groups: list[dict[str, Any]] = []

        for table in tables_src:
            if not isinstance(table, dict):
                continue

            table_name = str(table.get("name") or "")
            if table_name:
                tables.append({"name": table_name})

            for col in table.get("columns", []) if isinstance(table.get("columns", []), list) else []:
                if not isinstance(col, dict):
                    continue
                columns.append(
                    {
                        "table": table_name,
                        "name": col.get("name", ""),
                        "dataType": col.get("dataType"),
                        "isHidden": col.get("isHidden", False),
                    }
                )

            for measure in table.get("measures", []) if isinstance(table.get("measures", []), list) else []:
                if not isinstance(measure, dict):
                    continue
                measures.append(
                    {
                        "table": table_name,
                        "name": measure.get("name", ""),
                        "expression": measure.get("expression", ""),
                        "formatString": measure.get("formatString"),
                    }
                )

            if isinstance(table.get("calculationGroup"), dict):
                calculation_groups.append(
                    {
                        "table": table_name,
                        "name": table_name,
                        "calculationGroup": table.get("calculationGroup"),
                    }
                )

        top_level_tables = root.get("tables", []) if isinstance(root, dict) and isinstance(root.get("tables", []), list) else []
        if not tables and top_level_tables and top_level_tables is not tables_src:
            for t in top_level_tables:
                if isinstance(t, dict) and isinstance(t.get("name"), str):
                    tables.append({"name": t.get("name")})

        top_level_measures = root.get("measures", []) if isinstance(root, dict) and isinstance(root.get("measures", []), list) else []
        if not measures and top_level_measures:
            measures = [m for m in top_level_measures if isinstance(m, dict)]

        top_level_columns = root.get("columns", []) if isinstance(root, dict) and isinstance(root.get("columns", []), list) else []
        if not columns and top_level_columns:
            columns = [c for c in top_level_columns if isinstance(c, dict)]

        relationships = model.get("relationships", []) if isinstance(model, dict) and isinstance(model.get("relationships", []), list) else []
        if not relationships and isinstance(root, dict) and isinstance(root.get("relationships", []), list):
            relationships = root.get("relationships", [])

        roles = model.get("roles", []) if isinstance(model, dict) and isinstance(model.get("roles", []), list) else []
        if not roles and isinstance(root, dict) and isinstance(root.get("roles", []), list):
            roles = root.get("roles", [])

        annotations = model.get("annotations", []) if isinstance(model, dict) and isinstance(model.get("annotations", []), list) else []
        if not annotations and isinstance(root, dict) and isinstance(root.get("annotations", []), list):
            annotations = root.get("annotations", [])

        calc_groups_raw = root.get("calculation_groups", []) if isinstance(root, dict) and isinstance(root.get("calculation_groups", []), list) else []
        if calc_groups_raw:
            calculation_groups.extend([c for c in calc_groups_raw if isinstance(c, dict)])

        if database is not None:
            inferred_type = "xmla_tabular_json"
        elif candidate.name.lower().startswith("tmdl"):
            inferred_type = "tmdl_json"
        elif isinstance(root, dict) and "model" in root:
            inferred_type = "tabular_model_json"
        else:
            inferred_type = "semantic_model"

        return {
            "available": True,
            "source": str(candidate),
            "model_type": root.get("model_type") if isinstance(root, dict) and root.get("model_type") else payload.get("model_type") or payload.get("type") or inferred_type,
            "name": (root.get("name") if isinstance(root, dict) else None) or payload.get("name") or candidate.stem,
            "description": (root.get("description") if isinstance(root, dict) else None) or payload.get("description", ""),
            "tables": tables,
            "measures": measures,
            "columns": columns,
            "relationships": relationships if isinstance(relationships, list) else [],
            "roles": roles if isinstance(roles, list) else [],
            "calculation_groups": calculation_groups,
            "annotations": annotations if isinstance(annotations, list) else [],
            "raw_keys": sorted(payload.keys()),
        }
