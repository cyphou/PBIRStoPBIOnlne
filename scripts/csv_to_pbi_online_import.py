#!/usr/bin/env python3
"""Drive PBI Online import using CSV mappings produced by export.

This script consumes:
- folders_mapping.csv
- users_mapping.csv
- connections_mapping.csv

It then:
1) Creates JSON mapping files required by migrate.py
2) Optionally resolves/creates missing gateway datasource ids
3) Runs import with new workspaces (map-folder) + connection rebinding (map-gateway)
4) Applies workspace permissions from users_mapping.csv
5) Runs validation per target workspace
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pbi_import.deploy.client_factory import PbiClientFactory

LOGGER = logging.getLogger("csv-to-pbi-import")


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


def _required(path: Path, label: str) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")
    return path


def _normalize_name(name: str) -> str:
    cleaned = (name or "").strip()
    if cleaned.startswith("[Shared] "):
        return cleaned.replace("[Shared] ", "", 1).strip()
    return cleaned


def _datasource_type(kind: str) -> str:
    k = (kind or "").strip().lower()
    mapping = {
        "sql": "Sql",
        "oracle": "Oracle",
        "odbc": "OData",
        "analysisservices": "AnalysisServices",
        "analysis services": "AnalysisServices",
        "postgresql": "PostgreSql",
        "postgres": "PostgreSql",
        "mysql": "MySql",
        "snowflake": "Snowflake",
        "web": "Web",
    }
    return mapping.get(k, "Sql")


def _build_connection_payload(row: dict[str, str], datasource_name: str) -> dict[str, Any]:
    details = {
        "server": (row.get("server_name") or "").strip(),
        "database": (row.get("database_name") or "").strip(),
    }
    details = {k: v for k, v in details.items() if v}
    conn_str = (row.get("connection_string") or "").strip()

    connection_details = json.dumps(details) if details else conn_str
    return {
        "datasourceName": datasource_name,
        "datasourceType": _datasource_type(row.get("datasource_type") or ""),
        "connectionDetails": connection_details,
        "credentialDetails": {
            "credentialType": "Windows",
            "encryptedConnection": "Encrypted",
            "encryptionAlgorithm": "None",
            "privacyLevel": "Organizational",
        },
    }


def _build_folder_map_json(rows: list[dict[str, str]], out_path: Path) -> tuple[Path, list[str]]:
    rules: list[dict[str, str]] = []
    workspace_names: set[str] = set()

    for row in rows:
        folder = (row.get("folder_path") or "").strip()
        ws = (row.get("target_workspace") or "").strip()
        if not folder or not ws:
            continue
        rules.append({"folder": folder, "workspace_name": ws})
        workspace_names.add(ws)

    if not rules:
        raise ValueError("No usable rows in folders_mapping.csv (target_workspace is empty)")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rules, indent=2), encoding="utf-8")
    return out_path, sorted(workspace_names)


def _resolve_or_create_datasource_id(
    pbi_client: Any,
    gateway_id: str,
    datasource_name: str,
    row: dict[str, str],
    create_missing: bool,
    dry_run: bool,
) -> str | None:
    existing = pbi_client.list_gateway_datasources(gateway_id)
    for ds in existing:
        if (ds.get("datasourceName") or "").strip().lower() == datasource_name.lower():
            return ds.get("id")

    if not create_missing:
        return None

    if dry_run:
        return f"pending-{datasource_name}"

    payload = _build_connection_payload(row, datasource_name)
    created = pbi_client.create_gateway_datasource(gateway_id, payload)
    return created.get("id")


def _build_gateway_map_json(
    rows: list[dict[str, str]],
    out_path: Path,
    pbi_client: Any,
    create_missing: bool,
    dry_run: bool,
) -> tuple[Path, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    summary = {
        "rows_total": len(rows),
        "rows_with_gateway": 0,
        "mapped": 0,
        "missing_datasource_id": 0,
        "created_datasource": 0,
    }

    for row in rows:
        needs_gateway = (row.get("needs_gateway") or "").strip().lower() == "yes"
        if not needs_gateway:
            continue

        gateway_id = (row.get("target_gateway_id") or "").strip()
        report_name = _normalize_name(row.get("report_name") or "")
        if not gateway_id or not report_name:
            continue

        summary["rows_with_gateway"] += 1

        datasource_id = (row.get("target_datasource_id") or "").strip()
        if not datasource_id:
            ds_name = report_name
            resolved = _resolve_or_create_datasource_id(
                pbi_client=pbi_client,
                gateway_id=gateway_id,
                datasource_name=ds_name,
                row=row,
                create_missing=create_missing,
                dry_run=dry_run,
            )
            if resolved:
                datasource_id = resolved
                if str(resolved).startswith("pending-"):
                    summary["created_datasource"] += 1
                elif create_missing:
                    summary["created_datasource"] += 1
            else:
                summary["missing_datasource_id"] += 1
                continue

        mapping[report_name] = {
            "gateway_id": gateway_id,
            "datasource_ids": [datasource_id],
        }
        summary["mapped"] += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    return out_path, summary


def _parse_user_assignments(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    assigns: list[dict[str, str]] = []
    for row in rows:
        aad = (row.get("target_azure_ad") or "").strip()
        role = (row.get("target_pbi_role") or "").strip() or "Viewer"
        if not aad:
            continue
        assigns.append({"target_azure_ad": aad, "target_pbi_role": role})
    # dedupe
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, str]] = []
    for a in assigns:
        key = (a["target_azure_ad"].lower(), a["target_pbi_role"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(a)
    return deduped


def _build_migrate_auth_flags(args: argparse.Namespace) -> list[str]:
    flags: list[str] = []
    if args.pbi_token:
        flags += ["--pbi-token", args.pbi_token]
    else:
        if args.tenant_id:
            flags += ["--tenant-id", args.tenant_id]
        if args.client_id:
            flags += ["--client-id", args.client_id]
        if args.client_secret:
            flags += ["--client-secret", args.client_secret]
    return flags


def _run_cmd(cmd: list[str]) -> None:
    LOGGER.info("Running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)


def _make_factory_args(args: argparse.Namespace) -> SimpleNamespace:
    return SimpleNamespace(
        tenant_id=args.tenant_id,
        client_id=args.client_id,
        client_secret=args.client_secret,
        pbi_token=args.pbi_token,
    )


def _apply_permissions(
    pbi_client: Any,
    workspace_names: list[str],
    assignments: list[dict[str, str]],
    dry_run: bool,
) -> dict[str, Any]:
    summary = {"workspaces": len(workspace_names), "assignments": 0, "failed": 0}

    ws_by_name = {ws.get("name"): ws.get("id") for ws in pbi_client.list_workspaces()}
    for ws_name in workspace_names:
        ws_id = ws_by_name.get(ws_name)
        if not ws_id:
            LOGGER.warning("Workspace not found for permission assignment: %s", ws_name)
            summary["failed"] += 1
            continue

        for entry in assignments:
            summary["assignments"] += 1
            if dry_run:
                continue
            try:
                pbi_client.add_workspace_user(
                    workspace_id=ws_id,
                    email_or_upn=entry["target_azure_ad"],
                    role=entry["target_pbi_role"],
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning(
                    "Permission assignment failed: workspace=%s user=%s role=%s error=%s",
                    ws_name,
                    entry["target_azure_ad"],
                    entry["target_pbi_role"],
                    exc,
                )
                summary["failed"] += 1
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="CSV-driven import to Power BI Online")
    parser.add_argument("--converted-dir", default="artifacts/converted", help="Converted content directory")
    parser.add_argument("--csv-dir", default="artifacts/export", help="Directory containing mapping CSVs")
    parser.add_argument("--run-dir", default="artifacts/csv_import_run", help="Directory to store generated JSON and reports")

    parser.add_argument("--tenant-id")
    parser.add_argument("--client-id")
    parser.add_argument("--client-secret")
    parser.add_argument("--pbi-token")
    parser.add_argument("--capacity-id")

    parser.add_argument("--create-missing-connections", action="store_true",
                        help="Create missing gateway datasources when target_datasource_id is empty")
    parser.add_argument("--skip-permission-apply", action="store_true",
                        help="Do not apply users_mapping.csv assignments")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    _setup_logging(args.verbose)

    converted_dir = Path(args.converted_dir)
    csv_dir = Path(args.csv_dir)
    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    folders_csv = _required(csv_dir / "folders_mapping.csv", "folders_mapping.csv")
    users_csv = _required(csv_dir / "users_mapping.csv", "users_mapping.csv")
    connections_csv = _required(csv_dir / "connections_mapping.csv", "connections_mapping.csv")

    folder_rows = _read_csv(folders_csv)
    user_rows = _read_csv(users_csv)
    connection_rows = _read_csv(connections_csv)

    pbi_client = PbiClientFactory.from_args(_make_factory_args(args))

    map_folder_json, workspace_names = _build_folder_map_json(folder_rows, run_dir / "map_folder.json")
    map_gateway_json, gateway_summary = _build_gateway_map_json(
        connection_rows,
        run_dir / "gateway_mapping.generated.json",
        pbi_client=pbi_client,
        create_missing=args.create_missing_connections,
        dry_run=args.dry_run,
    )

    user_assignments = _parse_user_assignments(user_rows)

    auth_flags = _build_migrate_auth_flags(args)

    import_cmd = [
        sys.executable,
        "migrate.py",
        "--import",
        "--input-dir",
        str(converted_dir),
        "--map-folder",
        str(map_folder_json),
        "--map-gateway",
        str(map_gateway_json),
        "--no-migrate-permissions",
        "--no-migrate-subscriptions",
        "--no-migrate-schedules",
    ]
    if args.capacity_id:
        import_cmd += ["--capacity-id", args.capacity_id]
    if args.dry_run:
        import_cmd += ["--dry-run"]
    import_cmd += auth_flags

    _run_cmd(import_cmd)

    perm_summary = {"skipped": True}
    if not args.skip_permission_apply:
        perm_summary = _apply_permissions(
            pbi_client=pbi_client,
            workspace_names=workspace_names,
            assignments=user_assignments,
            dry_run=args.dry_run,
        )

    ws_by_name = {ws.get("name"): ws.get("id") for ws in pbi_client.list_workspaces()}
    validation: list[dict[str, str]] = []
    for ws_name in workspace_names:
        ws_id = ws_by_name.get(ws_name)
        if not ws_id:
            validation.append({"workspace": ws_name, "status": "missing_workspace"})
            continue
        out_dir = run_dir / "validation" / ws_name.replace(" ", "_")
        out_dir.mkdir(parents=True, exist_ok=True)
        validate_cmd = [
            sys.executable,
            "migrate.py",
            "--validate",
            "--input-dir",
            str(converted_dir),
            "--workspace-id",
            ws_id,
            "--output-dir",
            str(out_dir),
        ]
        if args.capacity_id:
            validate_cmd += ["--capacity-id", args.capacity_id]
        validate_cmd += auth_flags
        _run_cmd(validate_cmd)
        validation.append({"workspace": ws_name, "workspace_id": ws_id, "status": "validated", "output_dir": str(out_dir)})

    summary = {
        "csv_dir": str(csv_dir),
        "converted_dir": str(converted_dir),
        "run_dir": str(run_dir),
        "workspace_count": len(workspace_names),
        "generated_files": {
            "map_folder_json": str(map_folder_json),
            "map_gateway_json": str(map_gateway_json),
        },
        "gateway_summary": gateway_summary,
        "permission_summary": perm_summary,
        "validation": validation,
        "dry_run": args.dry_run,
    }

    summary_path = run_dir / "csv_import_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    LOGGER.info("CSV import flow completed. Summary: %s", summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
