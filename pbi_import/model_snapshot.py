"""Semantic model snapshot loader.

Loads explicit model artifacts when they are available (for example a pre-
extracted ``model_snapshot.json`` / TMDL-export JSON) and normalizes them for
downstream BPA analysis.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ModelSnapshotLoader:
    """Find and normalize semantic-model snapshots."""

    CANDIDATE_FILENAMES = (
        "model_snapshot.json",
        "semantic_model.json",
        "model.json",
        "tmdl.json",
    )

    def load(self, source_path: str) -> dict[str, Any]:
        """Load the best available model snapshot from a file or directory.

        If no explicit snapshot is available, returns a neutral placeholder
        describing the missing model artifact so callers can clearly report
        fallback BPA behavior.
        """
        path = Path(source_path)
        candidate = self._resolve_candidate(path)
        if candidate is None:
            return {
                "available": False,
                "source": str(path),
                "model_type": "unknown",
                "message": "No explicit model snapshot found",
                "tables": [],
                "measures": [],
                "columns": [],
                "relationships": [],
                "roles": [],
                "calculation_groups": [],
                "annotations": [],
            }

        with candidate.open(encoding="utf-8") as f:
            payload = json.load(f)

        return self._normalise(payload, candidate)

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

        return None

    @staticmethod
    def _normalise(payload: Any, candidate: Path) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {
                "available": False,
                "source": str(candidate),
                "model_type": "unknown",
                "message": "Model snapshot payload was not a JSON object",
                "tables": [],
                "measures": [],
                "columns": [],
                "relationships": [],
                "roles": [],
                "calculation_groups": [],
                "annotations": [],
            }

        tables = payload.get("tables", [])
        measures = payload.get("measures", [])
        columns = payload.get("columns", [])
        relationships = payload.get("relationships", [])
        roles = payload.get("roles", [])
        calculation_groups = payload.get("calculation_groups", [])
        annotations = payload.get("annotations", [])

        return {
            "available": True,
            "source": str(candidate),
            "model_type": payload.get("model_type") or payload.get("type") or "semantic_model",
            "name": payload.get("name") or candidate.stem,
            "description": payload.get("description", ""),
            "tables": tables if isinstance(tables, list) else [],
            "measures": measures if isinstance(measures, list) else [],
            "columns": columns if isinstance(columns, list) else [],
            "relationships": relationships if isinstance(relationships, list) else [],
            "roles": roles if isinstance(roles, list) else [],
            "calculation_groups": calculation_groups if isinstance(calculation_groups, list) else [],
            "annotations": annotations if isinstance(annotations, list) else [],
            "raw_keys": sorted(payload.keys()),
        }
