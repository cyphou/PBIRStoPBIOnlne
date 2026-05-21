"""
Data Validator — row count and checksum validation between source and target.

Validates data integrity by comparing row counts, column schemas, and
sample checksums between PBIRS datasets and PBI Online semantic models.
"""

import hashlib
import json
import logging
from typing import Any
from pathlib import Path

logger = logging.getLogger(__name__)


class DataValidator:
    """Validate data consistency between source and target environments."""

    def __init__(self, source_client: Any | None = None, target_client: Any | None = None):
        self.source = source_client
        self.target = target_client

    def validate_row_counts(
        self,
        source_counts: dict[str, int],
        target_counts: dict[str, int],
    ) -> dict:
        """Compare row counts between source and target tables.

        Args:
            source_counts: ``{table_name: row_count}`` from source.
            target_counts: ``{table_name: row_count}`` from target.
        """
        all_tables = set(source_counts.keys()) | set(target_counts.keys())
        results: list[dict] = []

        for table in sorted(all_tables):
            src = source_counts.get(table)
            tgt = target_counts.get(table)

            if src is None:
                status = "missing_in_source"
            elif tgt is None:
                status = "missing_in_target"
            elif src == tgt:
                status = "match"
            else:
                status = "mismatch"

            results.append({
                "table": table,
                "source_rows": src,
                "target_rows": tgt,
                "difference": (tgt or 0) - (src or 0) if src is not None and tgt is not None else None,
                "status": status,
            })

        matched = sum(1 for r in results if r["status"] == "match")
        return {
            "results": results,
            "summary": {
                "total_tables": len(results),
                "matched": matched,
                "mismatched": sum(1 for r in results if r["status"] == "mismatch"),
                "missing_in_source": sum(1 for r in results if r["status"] == "missing_in_source"),
                "missing_in_target": sum(1 for r in results if r["status"] == "missing_in_target"),
                "pass_rate": round(matched / max(len(results), 1) * 100, 1),
            },
        }

    def validate_schema(
        self,
        source_schema: dict[str, list[dict]],
        target_schema: dict[str, list[dict]],
    ) -> dict:
        """Compare column schemas between source and target.

        Args:
            source_schema: ``{table: [{name, type}]}``.
            target_schema: ``{table: [{name, type}]}``.
        """
        all_tables = set(source_schema.keys()) | set(target_schema.keys())
        results: list[dict] = []

        for table in sorted(all_tables):
            src_cols = {c["name"]: c.get("type", "") for c in source_schema.get(table, [])}
            tgt_cols = {c["name"]: c.get("type", "") for c in target_schema.get(table, [])}

            missing_cols = set(src_cols.keys()) - set(tgt_cols.keys())
            extra_cols = set(tgt_cols.keys()) - set(src_cols.keys())
            type_mismatches: list[dict] = []

            for col in set(src_cols.keys()) & set(tgt_cols.keys()):
                if src_cols[col] != tgt_cols[col]:
                    type_mismatches.append({
                        "column": col,
                        "source_type": src_cols[col],
                        "target_type": tgt_cols[col],
                    })

            results.append({
                "table": table,
                "status": "match" if not missing_cols and not extra_cols and not type_mismatches else "mismatch",
                "missing_columns": sorted(missing_cols),
                "extra_columns": sorted(extra_cols),
                "type_mismatches": type_mismatches,
            })

        matched = sum(1 for r in results if r["status"] == "match")
        return {
            "results": results,
            "summary": {
                "total_tables": len(results),
                "matched": matched,
                "mismatched": len(results) - matched,
            },
        }

    def validate_checksums(
        self,
        source_data: dict[str, list[list]],
        target_data: dict[str, list[list]],
    ) -> dict:
        """Compare data checksums for sample rows.

        Args:
            source_data: ``{table: [[row_values]]}``.
            target_data: ``{table: [[row_values]]}``.
        """
        results: list[dict] = []

        for table in sorted(set(source_data.keys()) | set(target_data.keys())):
            src_hash = self._hash_rows(source_data.get(table, []))
            tgt_hash = self._hash_rows(target_data.get(table, []))

            results.append({
                "table": table,
                "source_hash": src_hash,
                "target_hash": tgt_hash,
                "status": "match" if src_hash == tgt_hash else "mismatch",
            })

        return {
            "results": results,
            "summary": {
                "total": len(results),
                "matched": sum(1 for r in results if r["status"] == "match"),
            },
        }

    def save(self, output_dir: str, report: dict, name: str = "data_validation") -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{name}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        return path

    @staticmethod
    def _hash_rows(rows: list[list]) -> str:
        h = hashlib.sha256()
        for row in rows:
            h.update(json.dumps(row, sort_keys=True, default=str).encode())
        return h.hexdigest()
