#!/usr/bin/env python3
"""
Power BI Report Server to Power BI Online Migration Tool.

CLI entry point for the 5-phase migration pipeline:
  1. Assessment — inventory PBIRS content, compatibility scoring
  2. Export — download reports, datasets, subscriptions from PBIRS
  3. Conversion — adapt PBIRS-specific features for PBI Online
  4. Import — deploy to PBI Online workspaces
  5. Validation — verify deployed content
"""

import argparse
import json
import logging
import os
import sys
import time
from enum import IntEnum
from pathlib import Path
from typing import Any


class ExitCode(IntEnum):
    """Process exit codes."""
    SUCCESS = 0
    PARTIAL = 1
    ERROR = 2
    CONFIG_ERROR = 3
    AUTH_ERROR = 4
    CONNECTION_ERROR = 5
    VALIDATION_ERROR = 6
    INTERRUPTED = 130


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _setup_logging(verbose: bool = False, log_file: str | None = None) -> logging.Logger:
    """Configure structured logging."""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=level, format=fmt, handlers=handlers)
    return logging.getLogger("pbirs-migrate")


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def _load_config(path: str) -> dict:
    """Load config.json with comment-key stripping."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("//")}


def _merge_config(args: argparse.Namespace, config: dict) -> argparse.Namespace:
    """Merge config file values into argparse namespace (CLI takes precedence)."""
    for key, value in config.items():
        arg_key = key.replace("-", "_")
        if hasattr(args, arg_key):
            current = getattr(args, arg_key)
            if current is None:
                setattr(args, arg_key, value)
    return args


# ---------------------------------------------------------------------------
# Phase implementations
# ---------------------------------------------------------------------------

def _run_assessment(args: argparse.Namespace, logger: logging.Logger) -> int:
    """Phase 1: Assess PBIRS content for migration readiness."""
    from pbirs_export.api_client import PBIRSClient
    from pbirs_export.assessment import MigrationAssessment
    from pbirs_export.catalog_extractor import CatalogExtractor

    logger.info("Phase 1: Assessment — inventorying PBIRS content")

    client = PBIRSClient(
        server_url=args.server,
        username=getattr(args, "username", None),
        password=getattr(args, "password", None),
        token=getattr(args, "token", None),
        use_windows_auth=getattr(args, "use_windows_auth", False),
    )

    extractor = CatalogExtractor(client)
    catalog = extractor.extract_catalog(
        folder=getattr(args, "folder", None),
        content_types=getattr(args, "content_types", None),
        include_pattern=getattr(args, "include_pattern", None),
        exclude_pattern=getattr(args, "exclude_pattern", None),
    )

    assessment = MigrationAssessment()
    report = assessment.assess(catalog)

    _, output_dir = _phase_dirs(args, "assess")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save inventory JSON
    inventory_path = output_dir / "inventory.json"
    with open(inventory_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, default=str)
    logger.info("Inventory saved to %s", inventory_path)

    # RDL feature analysis (v1.2)
    from pbirs_export.rdl_analyser import analyse_rdl_directory
    rdl_dir = output_dir / "content"
    if rdl_dir.exists():
        rdl_analysis = analyse_rdl_directory(str(rdl_dir))
        with open(output_dir / "rdl_analysis.json", "w", encoding="utf-8") as f:
            json.dump(rdl_analysis, f, indent=2, default=str)
        logger.info("RDL analysis: %d files analysed", len(rdl_analysis))

    # Save assessment report
    report_path = output_dir / "assessment_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info("Assessment report saved to %s", report_path)

    # Generate HTML report
    html_path = output_dir / "assessment_report.html"
    assessment.generate_html_report(report, str(html_path))
    logger.info("HTML report saved to %s", html_path)

    # Print summary
    _print_assessment_summary(report, logger)

    return ExitCode.SUCCESS


def _run_export(args: argparse.Namespace, logger: logging.Logger) -> int:
    """Phase 2: Export PBIRS content to local artifacts."""
    from pbirs_export.api_client import PBIRSClient
    from pbirs_export.catalog_extractor import CatalogExtractor
    from pbirs_export.content_downloader import ContentDownloader
    from pbirs_export.datasource_extractor import DatasourceExtractor
    from pbirs_export.mapping_generator import MappingGenerator
    from pbirs_export.permission_extractor import PermissionExtractor
    from pbirs_export.security_extractor import SecurityExtractor
    from pbirs_export.subscription_extractor import SubscriptionExtractor

    logger.info("Phase 2: Export — downloading PBIRS content")

    client = PBIRSClient(
        server_url=args.server,
        username=getattr(args, "username", None),
        password=getattr(args, "password", None),
        token=getattr(args, "token", None),
        use_windows_auth=getattr(args, "use_windows_auth", False),
    )

    _, output_dir = _phase_dirs(args, "export")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Extract catalog
    extractor = CatalogExtractor(client)
    catalog = extractor.extract_catalog(
        folder=getattr(args, "folder", None),
        content_types=getattr(args, "content_types", None),
        include_pattern=getattr(args, "include_pattern", None),
        exclude_pattern=getattr(args, "exclude_pattern", None),
    )

    # Download content files
    workers = getattr(args, "parallel", 4)
    downloader = ContentDownloader(client, str(output_dir), workers=workers)
    download_results = downloader.download_all(catalog, dry_run=getattr(args, "dry_run", False))

    # Extract datasource info
    ds_extractor = DatasourceExtractor(client)
    datasources = ds_extractor.extract_all(catalog)
    with open(output_dir / "datasources.json", "w", encoding="utf-8") as f:
        json.dump(datasources, f, indent=2, default=str)

    # Extract permissions
    perm_extractor = PermissionExtractor(client)
    permissions = perm_extractor.extract_all(catalog)

    # Optional DB-assisted security inheritance resolver (v6.2)
    if getattr(args, "security_db_assist", False):
        db_conn = getattr(args, "reportserver_db_conn", None) or os.getenv("REPORTSERVER_DB_CONN")
        strategy = getattr(args, "security_conflict_strategy", "prefer-api")
        if not db_conn:
            logger.warning(
                "Security DB assist requested but no connection string provided. "
                "Set --reportserver-db-conn or REPORTSERVER_DB_CONN."
            )
        else:
            from pbirs_export.security_inheritance_resolver import SecurityInheritanceResolver
            resolver = SecurityInheritanceResolver(
                connection_string=db_conn,
                conflict_strategy=strategy,
                logger_=logger,
            )
            resolved = resolver.resolve(
                permissions.get("item_policies", []),
                catalog.get("items", []),
            )
            permissions["item_policies"] = resolved.get("merged_item_policies", permissions.get("item_policies", []))
            gap_report = resolved.get("gap_report", {})
            with open(output_dir / "security_gap_report.json", "w", encoding="utf-8") as f:
                json.dump(gap_report, f, indent=2)
            logger.info(
                "Security DB assist: %d items compared, %d diffs (strategy=%s)",
                gap_report.get("total_items", 0),
                gap_report.get("diff_items_count", 0),
                strategy,
            )
            if strategy == "strict-fail-on-diff" and int(gap_report.get("diff_items_count", 0)) > 0:
                logger.error("Security inheritance diffs detected under strict strategy")
                return ExitCode.VALIDATION_ERROR

    with open(output_dir / "permissions.json", "w", encoding="utf-8") as f:
        json.dump(permissions, f, indent=2, default=str)

    # Extract subscriptions
    sub_extractor = SubscriptionExtractor(client)
    subscriptions = sub_extractor.extract_all(catalog)
    with open(output_dir / "subscriptions.json", "w", encoding="utf-8") as f:
        json.dump(subscriptions, f, indent=2, default=str)

    # Extract security model
    sec_extractor = SecurityExtractor(client)
    security = sec_extractor.extract_all(catalog)
    with open(output_dir / "security.json", "w", encoding="utf-8") as f:
        json.dump(security, f, indent=2, default=str)

    # Generate CSV mapping templates
    mapping_gen = MappingGenerator(
        catalog=catalog,
        permissions=permissions,
        datasources=datasources,
        security=security,
    )
    mapping_paths = mapping_gen.generate_all(str(output_dir))
    logger.info(
        "Mapping CSVs generated: %s",
        ", ".join(p.name for p in mapping_paths.values()),
    )

    # Save export manifest
    manifest = {
        "server": args.server,
        "export_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "items_exported": len(download_results.get("success", [])),
        "items_failed": len(download_results.get("failed", [])),
        "catalog": catalog,
        "download_results": download_results,
    }
    with open(output_dir / "export_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)

    logger.info("Export complete: %d items exported, %d failed",
                len(download_results.get("success", [])),
                len(download_results.get("failed", [])))

    return ExitCode.SUCCESS


def _run_conversion(args: argparse.Namespace, logger: logging.Logger) -> int:
    """Phase 3: Convert exported content for PBI Online compatibility."""
    from pbi_import.converter import ContentConverter
    from pbi_import.rdl_modifier import modify_rdl_directory
    from pbi_import.subreport_resolver import SubreportResolver
    from pbi_import.power_automate_generator import PowerAutomateGenerator
    from pbi_import.data_driven_converter import DataDrivenConverter
    from pbi_import.scorecard_generator import ScorecardGenerator

    logger.info("Phase 3: Conversion — adapting content for PBI Online")

    input_dir, output_dir = _phase_dirs(args, "convert")
    output_dir.mkdir(parents=True, exist_ok=True)

    # RDL modification — strip unsupported features (v1.2)
    rdl_source = input_dir / "content"
    rdl_dest = output_dir / "content"
    if rdl_source.exists():
        mod_results = modify_rdl_directory(str(rdl_source), str(rdl_dest))
        logger.info("RDL modification: %d files processed", len(mod_results))

    # Subreport dependency resolution (v1.2)
    manifest_path = input_dir / "export_manifest.json"
    if manifest_path.exists():
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        catalog = manifest.get("catalog", {})
        resolver = SubreportResolver(catalog)
        dep_result = resolver.resolve()
        with open(output_dir / "subreport_dependencies.json", "w", encoding="utf-8") as f:
            json.dump(dep_result, f, indent=2, default=str)
        logger.info("Subreport resolution: %d ordered, %d circular",
                    len(dep_result.get("ordered_paths", [])),
                    len(dep_result.get("circular", [])))

    # Base content conversion
    converter = ContentConverter(
        input_dir=str(input_dir),
        output_dir=str(output_dir),
        gateway_mapping=getattr(args, "map_gateway", None),
        skip_unsupported=getattr(args, "skip_unsupported", True),
    )

    results = converter.convert_all(dry_run=getattr(args, "dry_run", False))

    # Power Automate flow generation (v1.3)
    subs_path = input_dir / "subscriptions.json"
    if subs_path.exists():
        with open(subs_path, encoding="utf-8") as f:
            subscriptions = json.load(f)

        # Optional data-driven query bridge from ReportServer DB (v6.2)
        if getattr(args, "allow_db_query_bridge", False):
            logger.warning(
                "DB query bridge enabled by explicit consent (--allow-db-query-bridge). "
                "Extracted artifacts will be redacted in logs/reports."
            )
            db_conn = getattr(args, "reportserver_db_conn", None) or os.getenv("REPORTSERVER_DB_CONN")
            if not db_conn:
                logger.warning(
                    "DB query bridge requested but no connection string provided. "
                    "Set --reportserver-db-conn or REPORTSERVER_DB_CONN."
                )
            else:
                from pbi_import.reportserver_db_bridge import ReportServerDbBridge
                bridge = ReportServerDbBridge(connection_string=db_conn, logger_=logger)
                bridge_result = bridge.merge_into_subscriptions(subscriptions)
                subscriptions = bridge_result["subscriptions"]
                with open(output_dir / "db_query_bridge_report.json", "w", encoding="utf-8") as f:
                    json.dump(bridge_result["report"], f, indent=2)
                logger.info(
                    "DB query bridge merged %d/%d data-driven subscriptions",
                    bridge_result["report"].get("merged_count", 0),
                    bridge_result["report"].get("data_driven_total", 0),
                )

        pa_gen = PowerAutomateGenerator()
        pa_results = pa_gen.generate_flows(subscriptions)
        pa_gen.save_flows(pa_results, str(output_dir))
        logger.info("Power Automate flows: %d generated, %d skipped",
                    pa_results["summary"]["flows_generated"],
                    pa_results["summary"]["skipped"])

        # Data-driven subscription conversion (v1.3)
        dd_converter = DataDrivenConverter()
        dd_results = dd_converter.convert_all(subscriptions)
        if dd_results["summary"]["total_data_driven"] > 0:
            dd_converter.save_plans(dd_results, str(output_dir))
            logger.info("Data-driven conversions: %d plans",
                        dd_results["summary"]["total_data_driven"])

    # Scorecard/Goals from KPI metadata (v1.3)
    if manifest_path.exists():
        catalog = manifest.get("catalog", {})
        workspace_id = getattr(args, "workspace_id", "") or ""
        sc_gen = ScorecardGenerator(workspace_id=workspace_id)
        sc_result = sc_gen.generate(catalog)
        if sc_result["scorecard"]:
            sc_gen.save(sc_result, str(output_dir))
            logger.info("Scorecard generated with %d goals",
                        sc_result["summary"]["goals_generated"])

    # Linked-report handling (v1.6 — Sprint H2)
    linked_as = getattr(args, "linked_as", None)
    if linked_as and manifest_path.exists():
        from pbi_import.linked_report_handler import LinkedReportHandler
        cat = manifest.get("catalog", {})
        items = cat.get("items", cat) if isinstance(cat, dict) else cat
        if isinstance(items, list):
            handler = LinkedReportHandler(strategy=linked_as)
            lr_result = handler.convert_all(items, output_dir / "linked_reports")
            with open(output_dir / "linked_reports_summary.json", "w", encoding="utf-8") as f:
                json.dump(lr_result, f, indent=2, default=str)
            logger.info("Linked reports: %d detected, %d converted (strategy=%s)",
                        lr_result["detected"], lr_result["converted"], linked_as)

    # Mobile Reports best-effort scaffolds (v1.7 — Sprint K1)
    if getattr(args, "migrate_mobile", False) and manifest_path.exists():
        from pbi_import.mobile_extractor import MobileReportExtractor
        cat = manifest.get("catalog", {})
        items = cat.get("items", cat) if isinstance(cat, dict) else cat
        if isinstance(items, list):
            mre = MobileReportExtractor(output_dir / "mobile_scaffolds")
            scaffolds = mre.extract_all({"items": items}, str(input_dir / "content"))
            with open(output_dir / "mobile_scaffolds.json", "w", encoding="utf-8") as f:
                json.dump({"scaffolds": scaffolds, "count": len(scaffolds)}, f, indent=2)
            logger.info("Mobile Reports: %d scaffolds generated", len(scaffolds))

    # DAX auto-fix (v1.7 — Sprint K4)
    if getattr(args, "dax_autofix", False):
        measures_path = input_dir / "measures.json"
        if measures_path.exists():
            from pbi_import.dax_auto_fixer import DAXAutoFixer
            measures = json.loads(measures_path.read_text(encoding="utf-8"))
            fixer = DAXAutoFixer()
            fix_results = fixer.fix_measures(measures if isinstance(measures, list) else measures.get("measures", []))
            summary = fixer.summary(fix_results)
            with open(output_dir / "dax_autofix.json", "w", encoding="utf-8") as f:
                json.dump({
                    "summary": summary,
                    "results": [r.__dict__ for r in fix_results],
                }, f, indent=2, default=str)
            logger.info("DAX auto-fix: %d/%d measures rewritten (rules: %s)",
                        summary["changed"], summary["total_measures"],
                        ", ".join(summary["by_rule"].keys()) or "none")
        else:
            logger.warning("--dax-autofix set but no measures.json at %s", measures_path)

    # Save conversion report
    with open(output_dir / "conversion_report.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)

    logger.info("Conversion complete: %d items converted, %d skipped, %d failed",
                results.get("converted", 0),
                results.get("skipped", 0),
                results.get("failed", 0))

    return ExitCode.SUCCESS


def _run_import(args: argparse.Namespace, logger: logging.Logger) -> int:
    """Phase 4: Import converted content to PBI Online."""
    from pbi_import.dataset_publisher import DatasetPublisher
    from pbi_import.deploy.client_factory import PbiClientFactory
    from pbi_import.gateway_mapper import GatewayMapper
    from pbi_import.paginated_publisher import PaginatedPublisher
    from pbi_import.permission_mapper import PermissionMapper
    from pbi_import.refresh_scheduler import RefreshScheduler
    from pbi_import.report_publisher import ReportPublisher
    from pbi_import.subscription_migrator import SubscriptionMigrator
    from pbi_import.workspace_manager import WorkspaceManager

    logger.info("Phase 4: Import — deploying to PBI Online")

    input_dir, _ = _phase_dirs(args, "import")
    workspace_id = getattr(args, "workspace_id", None)
    workspace_name = getattr(args, "workspace_name", None)
    map_folder = getattr(args, "map_folder", None)

    if not workspace_id and not workspace_name and not map_folder:
        logger.error("One of --workspace-id, --workspace-name, or --map-folder is required for import")
        return ExitCode.CONFIG_ERROR

    dry_run = getattr(args, "dry_run", False)
    continue_on_error = getattr(args, "continue_on_error", False)
    workers = max(1, int(getattr(args, "parallelism", 1) or 1))

    # Acquire PBI Online client
    try:
        pbi_client = PbiClientFactory.from_args(args)
    except (RuntimeError, ImportError) as e:
        logger.error("Could not acquire PBI Online client: %s", e)
        return ExitCode.AUTH_ERROR

    # Apply custom role-map overrides (Sprint H4)
    if getattr(args, "role_map", None):
        try:
            from pbi_import.role_mapper import RoleMapper
            from pbi_import import permission_mapper as _pm
            rm = RoleMapper.from_file(args.role_map)
            _pm.ROLE_MAP.update({k: v for k, v in rm.mapping.items()})
            logger.info("Applied role-map overrides from %s", args.role_map)
        except (FileNotFoundError, ValueError) as e:
            logger.error("Role-map load failed: %s", e)
            return ExitCode.CONFIG_ERROR

    # Content-hash store for idempotent re-runs (Sprint J3)
    hash_store = None
    if getattr(args, "skip_published", False):
        from pbi_import.content_hash import ContentHashStore
        hash_store = ContentHashStore(str(input_dir.parent))
        logger.info("Idempotency: %s", hash_store.stats())

    # Build workspace dispatch plan (single or multi-workspace)
    workspace_targets = _resolve_workspace_targets(
        args, pbi_client, input_dir, workspace_id, workspace_name, dry_run, logger
    )
    if workspace_targets is None:
        return ExitCode.CONFIG_ERROR

    publish_results: dict[str, dict] = {"datasets": {"success": [], "failed": []},
                                        "reports":  {"success": [], "failed": []},
                                        "paginated":{"success": [], "failed": []}}

    def _run(label: str, fn) -> dict:
        try:
            return fn()
        except Exception as e:
            if not continue_on_error:
                raise
            logger.error("%s failed (continuing): %s", label, e, exc_info=args.verbose)
            return {"success": [], "failed": [{"name": label, "error": str(e)}]}

    # Wave-scope filter (Sprint I2)
    wave_filter: set[str] | None = None
    if getattr(args, "wave", None):
        wave_plan_path = Path(getattr(args, "wave_out", None) or (input_dir / "wave_plan.json"))
        if wave_plan_path.is_file():
            try:
                from pbi_import.wave_planner import WavePlanner
                plan = json.loads(wave_plan_path.read_text(encoding="utf-8"))
                wave_items = WavePlanner().get_wave(plan, int(args.wave))
                wave_filter = {str(i.get("id") or i.get("name")) for i in wave_items}
                logger.info("Wave %d selected — %d items in scope", args.wave, len(wave_filter))
            except (IndexError, json.JSONDecodeError) as e:
                logger.error("Wave selection failed: %s", e)
                return ExitCode.CONFIG_ERROR
        else:
            logger.warning("--wave specified but no wave plan at %s — proceeding without filter", wave_plan_path)

    # Pre-create workspace folder tree per target (Sprint H1)
    folder_mappings: dict[str, dict[str, str]] = {}
    if getattr(args, "preserve_folders", False):
        from pbi_import.workspace_folder_manager import WorkspaceFolderManager
        # Load catalog to learn folder paths
        manifest_path = input_dir / "export_manifest.json"
        if not manifest_path.is_file():
            manifest_path = input_dir.parent / "export" / "export_manifest.json"
        cat_items: list[dict] = []
        if manifest_path.is_file():
            try:
                m = json.loads(manifest_path.read_text(encoding="utf-8"))
                raw_cat = m.get("catalog", {})
                cat_items = raw_cat.get("items", raw_cat) if isinstance(raw_cat, dict) else raw_cat
                if not isinstance(cat_items, list):
                    cat_items = []
            except json.JSONDecodeError:
                cat_items = []
        if cat_items:
            wfm = WorkspaceFolderManager(pbi_client)
            paths = wfm.build_tree(cat_items)
            for target in workspace_targets:
                ws_id = target["workspace_id"]
                folder_mappings[ws_id] = wfm.ensure_folders(ws_id, paths, dry_run=dry_run)
                logger.info("Workspace %s: %d folders prepared", ws_id, len(folder_mappings[ws_id]))

    # Publish per target workspace
    for target in workspace_targets:
        ws_id = target["workspace_id"]
        target_dir = target.get("input_dir", str(input_dir))
        logger.info("Publishing to workspace %s (%s)", target.get("workspace_name", ws_id), ws_id)

        for kind, cls in (("datasets", DatasetPublisher),
                          ("reports", ReportPublisher),
                          ("paginated", PaginatedPublisher)):
            chunk = _run(
                f"{kind} publish ({ws_id})",
                lambda c=cls, w=ws_id, d=target_dir: c(pbi_client).publish_all(
                    d, w, dry_run=dry_run, workers=workers
                ),
            )
            publish_results[kind]["success"].extend(chunk.get("success", []))
            publish_results[kind]["failed"].extend(chunk.get("failed", []))

    # Use first workspace for legacy single-workspace operations (permissions / subscriptions)
    primary_ws = workspace_targets[0]["workspace_id"]

    # Gateway bindings
    if getattr(args, "map_gateway", None):
        gw_mapper = GatewayMapper(pbi_client, gateway_mapping_file=args.map_gateway)
        _run(
            "gateway binding",
            lambda: gw_mapper.bind_datasets(
                primary_ws,
                publish_results["reports"]["success"] + publish_results["datasets"]["success"],
                dry_run=dry_run,
            ),
        )

    # Gateway auto-create (Sprint K3) — create missing datasources on a gateway
    if getattr(args, "gateway_auto", False):
        from pbi_import.gateway_autocreate import GatewayAutoCreator
        from pbi_import.connection_mapping_csv import (
            build_online_inventory,
            write_connection_endpoint_csv,
            write_connection_mapping_csv,
        )
        from pbi_import.gateway_mapper import GatewayMapper
        gw_id = getattr(args, "gateway_id", None)
        if not gw_id:
            logger.error("--gateway-auto requires --gateway-id")
            return ExitCode.CONFIG_ERROR
        ds_path = input_dir / "datasources.json"
        if ds_path.is_file():
            datasources = _load_json(ds_path) or []
            if isinstance(datasources, dict):
                if isinstance(datasources.get("shared_datasources"), list):
                    datasources = datasources.get("shared_datasources", [])
                elif isinstance(datasources.get("datasources"), list):
                    datasources = datasources.get("datasources", [])
                else:
                    datasources = []
            if not isinstance(datasources, list):
                datasources = []
            creator = GatewayAutoCreator(pbi_client, default_gateway_id=gw_id)
            plan = creator.plan(datasources, gateway_id=gw_id)
            res = creator.execute(datasources, gateway_id=gw_id, dry_run=dry_run)
            mapping_path = input_dir / "gateway_mapping.auto.json"
            creator.write_mapping(res, mapping_path, gateway_id=gw_id)

            # Auto-bind datasets/reports using the generated mapping so the
            # connection creation path is complete in one run.
            bind_results = GatewayMapper(pbi_client, str(mapping_path)).bind_datasets(
                primary_ws,
                publish_results["reports"]["success"] + publish_results["datasets"]["success"],
                dry_run=dry_run,
            )

            connection_report = {
                "gateway_id": gw_id,
                "planned": len(plan),
                "created": len(res.get("created", [])),
                "skipped": len(res.get("skipped", [])),
                "failed": len(res.get("failed", [])),
                "bound": len(bind_results.get("bound", [])),
                "bind_failed": len(bind_results.get("failed", [])),
            }
            (input_dir / "gateway_connection_report.json").write_text(
                json.dumps({
                    "summary": connection_report,
                    "create": res,
                    "bind": bind_results,
                }, indent=2),
                encoding="utf-8",
            )

            online_gateways, online_datasources = build_online_inventory(pbi_client, gateway_id=gw_id)
            csv_path = Path(getattr(args, "connection_map_csv", "") or (input_dir / "connection_mapping.csv"))
            csv_summary = write_connection_mapping_csv(
                datasources={"shared_datasources": datasources, "embedded_datasources": []},
                output_path=csv_path,
                mapping=_load_json(mapping_path, default={}) or {},
                online_gateways=online_gateways,
                online_datasources_by_gateway=online_datasources,
            )
            endpoint_csv_path = Path(
                getattr(args, "connection_map_endpoint_csv", "")
                or (input_dir / "connection_mapping_by_endpoint.csv")
            )
            endpoint_summary = write_connection_endpoint_csv(
                datasources={"shared_datasources": datasources, "embedded_datasources": []},
                output_path=endpoint_csv_path,
                mapping=_load_json(mapping_path, default={}) or {},
                online_gateways=online_gateways,
                online_datasources_by_gateway=online_datasources,
            )

            logger.info("Gateway auto-create: created=%d skipped=%d failed=%d (mapping: %s)",
                        len(res["created"]), len(res["skipped"]), len(res["failed"]),
                        mapping_path)
            logger.info("Gateway auto-bind: bound=%d failed=%d (report: %s)",
                        len(bind_results.get("bound", [])), len(bind_results.get("failed", [])),
                        input_dir / "gateway_connection_report.json")
            logger.info("Connection mapping CSV: total=%d mapped=%d suggested=%d unmapped=%d (%s)",
                        csv_summary["total"], csv_summary["mapped"], csv_summary["suggested"],
                        csv_summary["unmapped"], csv_path)
            logger.info("Connection endpoint CSV: endpoints=%d occurrences=%d (%s)",
                        endpoint_summary["total_endpoints"], endpoint_summary["total_occurrences"],
                        endpoint_csv_path)
        else:
            logger.warning("--gateway-auto: no datasources.json at %s", ds_path)

    # Optional standalone connection mapping CSV export.
    if getattr(args, "connection_map_csv", None) and not getattr(args, "gateway_auto", False):
        from pbi_import.connection_mapping_csv import (
            build_online_inventory,
            write_connection_endpoint_csv,
            write_connection_mapping_csv,
        )

        ds_path = input_dir / "datasources.json"
        if ds_path.is_file():
            datasources = _load_json(ds_path) or {}
            mapping = _load_json(getattr(args, "map_gateway", ""), default={}) if getattr(args, "map_gateway", None) else {}
            online_gateways, online_datasources = build_online_inventory(
                pbi_client,
                gateway_id=getattr(args, "gateway_id", None),
            )
            csv_summary = write_connection_mapping_csv(
                datasources=datasources if isinstance(datasources, dict) else {"shared_datasources": [], "embedded_datasources": []},
                output_path=Path(getattr(args, "connection_map_csv")),
                mapping=mapping or {},
                online_gateways=online_gateways,
                online_datasources_by_gateway=online_datasources,
            )
            endpoint_csv_path = Path(
                getattr(args, "connection_map_endpoint_csv", "")
                or (Path(getattr(args, "connection_map_csv")).with_name("connection_mapping_by_endpoint.csv"))
            )
            endpoint_summary = write_connection_endpoint_csv(
                datasources=datasources if isinstance(datasources, dict) else {"shared_datasources": [], "embedded_datasources": []},
                output_path=endpoint_csv_path,
                mapping=mapping or {},
                online_gateways=online_gateways,
                online_datasources_by_gateway=online_datasources,
            )
            logger.info("Connection mapping CSV: total=%d mapped=%d suggested=%d unmapped=%d (%s)",
                        csv_summary["total"], csv_summary["mapped"], csv_summary["suggested"],
                        csv_summary["unmapped"], getattr(args, "connection_map_csv"))
            logger.info("Connection endpoint CSV: endpoints=%d occurrences=%d (%s)",
                        endpoint_summary["total_endpoints"], endpoint_summary["total_occurrences"],
                        endpoint_csv_path)
        else:
            logger.warning("--connection-map-csv: no datasources.json at %s", ds_path)

    # AD → AAD bridge (Sprint K2) — emit CSV manifest of principals
    if getattr(args, "ad_bridge", False):
        from pbi_import.ad_group_bridge import ADGroupBridge
        perms = _load_json(input_dir / "permissions.json") or {}
        bridge = ADGroupBridge(graph_client=getattr(pbi_client, "graph", None))
        discovered = bridge.discover(perms)
        csv_path = (
            Path(args.ad_bridge_csv) if getattr(args, "ad_bridge_csv", None)
            else input_dir / "ad_bridge.csv"
        )
        bridge.write_csv(discovered, csv_path)
        if getattr(args, "ensure_aad_groups", False):
            ensure_dry = dry_run or not getattr(pbi_client, "graph", None)
            results = bridge.ensure_aad_groups(discovered, dry_run=ensure_dry)
            bridge.write_report(discovered, results, input_dir / "ad_bridge.report.json")
            logger.info("AD bridge: %d groups + %d users; ensure_dry_run=%s",
                        len(discovered["groups"]), len(discovered["users"]), ensure_dry)
        else:
            logger.info("AD bridge CSV written → %s (%d groups, %d users)",
                        csv_path, len(discovered["groups"]), len(discovered["users"]))

    # Permissions
    if getattr(args, "migrate_permissions", True):
        permissions = _load_json(input_dir / "permissions.json")
        if permissions:
            _run(
                "permission mapping",
                lambda: PermissionMapper(pbi_client).map_permissions(
                    permissions, primary_ws, dry_run=dry_run
                ),
            )

    # Subscriptions
    if getattr(args, "migrate_subscriptions", True):
        subscriptions = _load_json(input_dir / "subscriptions.json")
        if subscriptions:
            _run(
                "subscription migration",
                lambda: SubscriptionMigrator(pbi_client).migrate_all(
                    subscriptions, publish_results, primary_ws, dry_run=dry_run
                ),
            )

    # Refresh schedules
    if getattr(args, "migrate_schedules", True):
        schedules = _load_json(input_dir / "schedules.json", default=[])
        if schedules:
            _run(
                "refresh scheduling",
                lambda: RefreshScheduler(pbi_client).configure_refreshes(
                    publish_results["datasets"]["success"], schedules, dry_run=dry_run
                ),
            )

    # PBIRS cache plans → PBI refresh schedules (Sprint H5)
    if getattr(args, "migrate_cache_plans", False):
        cache_plans = _load_json(input_dir / "cache_plans.json", default=[])
        if cache_plans:
            from pbi_import.cache_plan_migrator import CachePlanMigrator
            cpm = CachePlanMigrator()
            translated = cpm.migrate_all(cache_plans)
            (input_dir / "translated_cache_plans.json").write_text(
                json.dumps(translated, indent=2), encoding="utf-8"
            )
            logger.info("Cache plans translated: %d (skipped %d)",
                        len(translated["translated"]), translated["skipped"])

    # PBIRS folder branding → PBI workspace branding + theme (Sprint H6)
    if getattr(args, "migrate_branding", False):
        from pbi_import.branding_migrator import BrandingMigrator
        brand_path = getattr(args, "brand_file", None) or str(input_dir / "branding.json")
        brand = _load_json(brand_path)
        if brand:
            bm = BrandingMigrator()
            for target in workspace_targets:
                br_res = bm.migrate(
                    brand,
                    target["workspace_id"],
                    str(input_dir / "branding"),
                    dry_run=dry_run,
                    pbi_client=pbi_client,
                )
                logger.info("Branding for %s: %s", target["workspace_id"], br_res["status"])
        else:
            logger.warning("--migrate-branding set but no brand file found at %s", brand_path)

    # ILS → App audience bucketing (Sprint H3)
    if getattr(args, "ils_as_audiences", False):
        from pbi_import.audience_bucketer import AudienceBucketer
        from pbi_import.app_publisher import AppPublisher
        permissions = _load_json(input_dir / "permissions.json", default={})
        item_policies = permissions.get("item_policies", []) if isinstance(permissions, dict) else []
        if item_policies:
            buckets = AudienceBucketer().bucket(item_policies)
            (input_dir / "audience_plan.json").write_text(
                json.dumps(buckets, indent=2), encoding="utf-8"
            )
            logger.info("ILS bucketing: %d audiences for %d items",
                        len(buckets["audiences"]), buckets["total_items"])
            if not dry_run:
                try:
                    AppPublisher(pbi_client).publish(
                        primary_ws,
                        audiences=[{
                            "name": a["name"],
                            "users": [p["name"] for p in a["principals"]],
                        } for a in buckets["audiences"]],
                        dry_run=dry_run,
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning("App publish from audience plan failed: %s", e)

    total = sum(len(r["success"]) for r in publish_results.values())
    failed = sum(len(r["failed"]) for r in publish_results.values())
    logger.info("Import complete: %d items deployed, %d failed", total, failed)

    if hash_store is not None:
        # Record every successful publish so the next --skip-published run skips them
        for kind, r in publish_results.items():
            for entry in r.get("success", []):
                hash_store.record(entry, workspace_id=primary_ws, result={"kind": kind})
        hash_store.save()
        logger.info("Content-hash store saved: %d entries", hash_store.stats()["total"])

    if dry_run:
        _print_publish_summary(publish_results, logger)

    return ExitCode.SUCCESS if failed == 0 else ExitCode.PARTIAL


def _resolve_workspace_targets(
    args: argparse.Namespace,
    pbi_client: Any,
    input_dir: Path,
    workspace_id: str | None,
    workspace_name: str | None,
    dry_run: bool,
    logger: logging.Logger,
) -> list[dict] | None:
    """Build the list of ``{workspace_id, input_dir}`` targets for the import phase.

    Single-workspace: uses ``--workspace-id`` / ``--workspace-name`` directly.
    Multi-workspace: when ``--map-folder`` is supplied, partitions the catalog by
    folder rules and creates / resolves one workspace per partition.
    """
    map_folder = getattr(args, "map_folder", None)
    if map_folder:
        from pbi_import.multi_workspace import MultiWorkspaceManager
        from pbirs_export.folder_mapper import FolderMapper

        manifest = _load_json(input_dir / "export_manifest.json") or _load_json(input_dir.parent / "export" / "export_manifest.json")
        catalog = (manifest.get("catalog") or {}).get("items") if isinstance(manifest.get("catalog"), dict) else manifest.get("catalog", [])
        if not catalog:
            logger.error("--map-folder requires an export_manifest.json with catalog items in %s", input_dir)
            return None

        mapper = FolderMapper.from_file(map_folder)
        plan = mapper.resolve_all(catalog)
        ws_manager = MultiWorkspaceManager(pbi_client)
        ws_mapping = ws_manager.ensure_workspaces(plan, dry_run=dry_run)
        ws_manager.save_mapping(str(input_dir.parent), ws_mapping)

        targets: list[dict] = []
        for ws_name, ws_id in ws_mapping.items():
            targets.append({
                "workspace_id": ws_id,
                "workspace_name": ws_name,
                "input_dir": str(input_dir),
            })
        if not targets:
            logger.warning("Folder mapping produced 0 workspaces — falling back to --workspace-id")
        else:
            return targets

    # Single workspace path
    from pbi_import.workspace_manager import WorkspaceManager
    if workspace_id:
        return [{"workspace_id": workspace_id, "workspace_name": workspace_name or "", "input_dir": str(input_dir)}]
    workspace = WorkspaceManager(pbi_client).ensure_workspace(
        name=workspace_name, capacity_id=getattr(args, "capacity_id", None)
    )
    return [{"workspace_id": workspace["id"], "workspace_name": workspace_name or "", "input_dir": str(input_dir)}]


def _print_publish_summary(results: dict, logger: logging.Logger) -> None:
    """Print a publish summary table after a dry-run import."""
    logger.info("=" * 60)
    logger.info("DRY-RUN IMPORT SUMMARY")
    logger.info("=" * 60)
    logger.info("%-12s %8s %8s", "Type", "Planned", "Errors")
    logger.info("-" * 60)
    for kind in ("datasets", "reports", "paginated"):
        r = results.get(kind, {})
        logger.info("%-12s %8d %8d", kind, len(r.get("success", [])), len(r.get("failed", [])))
    logger.info("=" * 60)


def _run_validation(args: argparse.Namespace, logger: logging.Logger) -> int:
    """Phase 5: Validate deployed content in PBI Online."""
    from pbi_import.deploy.client_factory import PbiClientFactory
    from pbi_import.validator import MigrationValidator

    logger.info("Phase 5: Validation — verifying deployed content")

    workspace_id = getattr(args, "workspace_id", None)
    if not workspace_id:
        logger.error("--workspace-id is required for validation")
        return ExitCode.CONFIG_ERROR

    input_dir, output_dir = _phase_dirs(args, "validate")
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        pbi_client = PbiClientFactory.from_args(args)
    except (RuntimeError, ImportError) as e:
        logger.error("Could not acquire PBI Online client: %s", e)
        return ExitCode.AUTH_ERROR

    validator = MigrationValidator(pbi_client)
    results = validator.validate_all(str(input_dir), workspace_id)

    # Save validation report
    with open(output_dir / "validation_report.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)

    # Generate HTML validation report
    validator.generate_html_report(results, str(output_dir / "validation_report.html"))

    passed = results.get("passed", 0)
    failed = results.get("failed", 0)
    logger.info("Validation complete: %d passed, %d failed", passed, failed)

    # Visual diff HTML report (Sprint I3)
    diff_out = getattr(args, "visual_diff_report", None)
    if diff_out:
        from pbi_import.visual_diff_report import VisualDiffReport
        pairs_file = getattr(args, "diff_pairs", None)
        pairs: list[dict] = []
        if pairs_file and Path(pairs_file).is_file():
            try:
                pairs = json.loads(Path(pairs_file).read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                logger.warning("--diff-pairs JSON parse failed: %s", e)
        if pairs:
            VisualDiffReport().generate(pairs, diff_out)
            logger.info("Visual diff report written to %s", diff_out)
        else:
            logger.warning("--visual-diff-report set but no pairs supplied via --diff-pairs")

    return ExitCode.SUCCESS if failed == 0 else ExitCode.VALIDATION_ERROR


def _run_sync_daemon(args: argparse.Namespace, logger: logging.Logger) -> int:
    """Run as a long-lived poller that replays incremental PBIRS changes."""
    from pbirs_export.api_client import PBIRSClient
    from pbirs_export.delta_tracker import DeltaTracker
    from pbi_import.sync_daemon import SyncDaemon

    if not args.server:
        logger.error("--server is required for --sync-daemon")
        return ExitCode.CONFIG_ERROR

    root = Path(args.output_dir) if getattr(args, "output_dir", None) else Path("artifacts")
    root.mkdir(parents=True, exist_ok=True)

    client = PBIRSClient(
        server_url=args.server,
        username=getattr(args, "username", None),
        password=getattr(args, "password", None),
        token=getattr(args, "token", None),
        use_windows_auth=getattr(args, "use_windows_auth", False),
    )
    tracker = DeltaTracker(str(root / ".migration_state.db"))

    def _fetch() -> list[dict]:
        return client.get_catalog_items()

    def _replay(delta: list[dict]) -> dict:
        logger.info("Daemon would replay %d items (no-op stub)", len(delta))
        # Replay strategy: emit an event log entry and let downstream tooling drive
        # the actual re-export. Real PBIRS→PBI replay is delegated to a fresh
        # migrate.py invocation so this loop stays state-light.
        return {"replayed": len(delta)}

    daemon = SyncDaemon(
        catalog_fetcher=_fetch,
        delta_tracker=tracker,
        replay=_replay,
        poll_interval=getattr(args, "sync_poll_interval", 300.0),
        max_iterations=getattr(args, "sync_max_iterations", None),
    )
    daemon.install_signal_handlers()
    logger.info(
        "Sync daemon starting (poll=%.0fs, max_iterations=%s)",
        daemon.poll_interval, daemon.max_iterations or "∞",
    )
    iterations = daemon.run()
    logger.info("Sync daemon exited after %d iterations", len(iterations))
    return ExitCode.SUCCESS


def _run_wave_planner(args: argparse.Namespace, logger: logging.Logger) -> int:
    """Compute and write a dependency-aware migration wave plan."""
    from pbi_import.wave_planner import WavePlanner

    root = Path(args.output_dir) if getattr(args, "output_dir", None) else Path("artifacts")
    # Try several known catalog locations.
    candidates = [
        root / "export" / "export_manifest.json",
        root / "export_manifest.json",
        root / "inventory.json",
    ]
    catalog: list[dict] = []
    for cand in candidates:
        if cand.is_file():
            try:
                payload = json.loads(cand.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            raw = payload.get("catalog", payload)
            items = raw.get("items", raw) if isinstance(raw, dict) else raw
            if isinstance(items, list):
                catalog = items
                logger.info("Loaded catalog from %s (%d items)", cand, len(catalog))
                break
    if not catalog:
        logger.error("No catalog found for wave planning — run --assess or --export first")
        return ExitCode.CONFIG_ERROR

    plan = WavePlanner().plan(catalog)
    out_path = Path(getattr(args, "wave_out", None) or (root / "wave_plan.json"))
    WavePlanner().write_plan(plan, out_path)
    logger.info(
        "Wave plan: %d waves over %d items (%d cycles, %d orphans)",
        plan["wave_count"], plan["item_count"],
        len(plan["cycles"]), len(plan["orphans"]),
    )
    return ExitCode.SUCCESS


def _run_benchmark(args: argparse.Namespace, logger: logging.Logger) -> int:
    """Run a synthetic catalog benchmark (Sprint J4)."""
    from pbi_import.benchmark_harness import BenchmarkHarness, generate_synthetic_catalog
    from pbi_import.catalog_stream import CatalogStream
    from pbirs_export.assessment import MigrationAssessment

    size = int(args.benchmark)
    logger.info("Benchmark: generating synthetic catalog (%d items)", size)
    catalog = generate_synthetic_catalog(size=size)

    harness = BenchmarkHarness()

    def _iter_only(cat: dict) -> int:
        return sum(1 for _ in CatalogStream.from_list(cat["items"]))

    def _filter_powerbi(cat: dict) -> int:
        s = CatalogStream.from_list(cat["items"]).filter(lambda i: i["Type"] == "PowerBIReport")
        return sum(1 for _ in s)

    def _assess(cat: dict) -> dict:
        return MigrationAssessment().assess(cat)

    harness.run("stream_iter_only", _iter_only, catalog, repeats=3)
    harness.run("stream_filter_powerbi", _filter_powerbi, catalog, repeats=3)
    harness.run("assessment", _assess, catalog, repeats=2)

    out_path = (
        getattr(args, "benchmark_out", None)
        or str(Path(getattr(args, "output_dir", None) or "artifacts") / f"benchmark-{size}.json")
    )
    harness.write_report(out_path)

    logger.info("Benchmark complete:")
    for r in harness.results:
        logger.info("  %-22s n=%d mean=%.3fs median=%.3fs",
                    r["name"], r["catalog_size"], r["mean_seconds"], r["median_seconds"])
    return ExitCode.SUCCESS


def _run_capability_report(args: argparse.Namespace, logger: logging.Logger) -> int:
    """Print and optionally persist environment capability report, then exit."""
    from pbi_import.capability_report import generate_capability_report, render_capability_report

    report = generate_capability_report(args)
    print(render_capability_report(report))

    out_path = getattr(args, "capability_report_out", None)
    if out_path:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        logger.info("Capability report written to %s", p)

    return ExitCode.SUCCESS


def _load_json(path: Path, default: Any = None) -> Any:
    """Load JSON from ``path``, returning ``default`` (or ``{}``) if missing."""
    if not path.exists():
        return default if default is not None else {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _finalise_early_exit(args: argparse.Namespace, logger: logging.Logger, exit_code: int) -> int:
    """Write trace output / flush OTLP for early-exit modes (benchmark/wave/sync)."""
    from pbi_import.tracing import Tracer
    trace_out = getattr(args, "trace_out", None)
    otlp = getattr(args, "otlp_endpoint", None)
    if not trace_out and not otlp:
        return exit_code
    tracer = Tracer(enabled=True, otlp_endpoint=otlp)
    # Single synthetic span so the envelope isn't empty
    with tracer.span("early_exit", mode=("benchmark" if getattr(args, "benchmark", None)
                                          else "sync" if getattr(args, "sync_daemon", False)
                                          else "wave_planner"),
                     exit_code=exit_code):
        pass
    if trace_out:
        try:
            tracer.write_json(trace_out)
            logger.info("Trace report written to %s", trace_out)
        except OSError as e:
            logger.warning("Failed to write trace report: %s", e)
    if otlp:
        tracer.flush_otlp()
    return exit_code


def _emit_prometheus_metrics(out_path: str, phases: list, exit_code: int, elapsed: float, root: Path) -> None:
    """Render pipeline summary as Prometheus metrics.

    Pulls per-phase counts from artifacts (assessment, export manifest, conversion,
    validation reports) when present so the metrics reflect actual work done.
    """
    try:
        from pbi_import.metrics_exporter import MetricsExporter
        exporter = MetricsExporter()
        exporter.gauge("migration_duration_seconds", elapsed, "Pipeline elapsed time")
        exporter.gauge("migration_exit_code", float(exit_code), "Pipeline exit code")
        exporter.gauge("migration_phases_run", float(len(phases)), "Phases executed in last run")

        # Assessment summary
        assess = _load_json(root / "assessment_report.json")
        for k, v in (assess.get("summary") or {}).items():
            if isinstance(v, (int, float)):
                exporter.gauge(f"migration_assessment_{k}", float(v), "Assessment summary")

        # Export manifest
        manifest = _load_json(root / "export" / "export_manifest.json")
        if manifest:
            exporter.gauge("migration_items_exported", float(manifest.get("items_exported", 0)), "Items successfully exported")
            exporter.gauge("migration_items_export_failed", float(manifest.get("items_failed", 0)), "Items that failed export")

        # Validation
        validation = _load_json(root / "validation_report.json")
        if validation:
            exporter.gauge("migration_validation_passed", float(validation.get("passed", 0)), "Validation passed")
            exporter.gauge("migration_validation_failed", float(validation.get("failed", 0)), "Validation failed")

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(exporter.render(), encoding="utf-8")
    except Exception as e:
        logging.getLogger("pbirs-migrate").warning("Failed to write Prometheus metrics: %s", e)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _phase_dirs(args: argparse.Namespace, phase: str) -> tuple[Path, Path]:
    """Return ``(input_dir, output_dir)`` for a phase.

    When ``--full`` is set, every phase chains off a single root (``--output-dir``
    or ``artifacts/``) using fixed subfolders so phases do not clobber each
    other. Outside ``--full``, explicit ``--input-dir`` / ``--output-dir`` flags
    win, falling back to historical per-phase defaults.
    """
    root = Path(args.output_dir) if getattr(args, "output_dir", None) else Path("artifacts")

    defaults = {
        "assess":   (root,                 root),
        "export":   (root,                 root / "export"),
        "convert":  (root / "export",      root / "converted"),
        "import":   (root / "converted",   root),
        "validate": (root / "export",      root),
    }
    in_default, out_default = defaults[phase]

    is_full = getattr(args, "full", False)
    if is_full:
        return in_default, out_default

    in_dir = Path(args.input_dir) if getattr(args, "input_dir", None) else in_default
    out_dir = Path(args.output_dir) if getattr(args, "output_dir", None) else out_default
    return in_dir, out_dir


def _print_assessment_summary(report: dict, logger: logging.Logger) -> None:
    """Print assessment summary to console."""
    summary = report.get("summary", {})
    logger.info("=" * 60)
    logger.info("ASSESSMENT SUMMARY")
    logger.info("=" * 60)
    logger.info("Total items:       %d", summary.get("total_items", 0))
    logger.info("  Power BI:        %d", summary.get("powerbi_reports", 0))
    logger.info("  Paginated:       %d", summary.get("paginated_reports", 0))
    logger.info("  Datasets:        %d", summary.get("datasets", 0))
    logger.info("  KPIs:            %d", summary.get("kpis", 0))
    logger.info("  Other:           %d", summary.get("other", 0))
    logger.info("-" * 60)
    logger.info("GREEN (ready):     %d", summary.get("green", 0))
    logger.info("YELLOW (minor):    %d", summary.get("yellow", 0))
    logger.info("RED (rework):      %d", summary.get("red", 0))
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    p = argparse.ArgumentParser(
        prog="pbirs-migrate",
        description="Migrate Power BI Report Server content to Power BI Online",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  %(prog)s --server https://pbirs.company.com/reports --assess
  %(prog)s --server https://pbirs.company.com/reports --export --output-dir artifacts/export
  %(prog)s --convert --input-dir artifacts/export --output-dir artifacts/converted
  %(prog)s --import --input-dir artifacts/converted --workspace-id <ID>
  %(prog)s --validate --workspace-id <ID>
  %(prog)s --server https://pbirs.company.com/reports --full --workspace-id <ID>
""",
    )

    # Connection
    conn = p.add_argument_group("PBIRS Connection")
    conn.add_argument("--server", help="PBIRS portal URL")
    conn.add_argument("--username", help="PBIRS username")
    conn.add_argument("--password", help="PBIRS password")
    conn.add_argument("--token", help="Bearer token for PBIRS REST API")
    conn.add_argument("--use-windows-auth", action="store_true", help="Use Windows auth (NTLM/Kerberos)")

    # PBI Online auth
    auth = p.add_argument_group("PBI Online Auth")
    auth.add_argument("--tenant-id", help="Azure AD tenant ID (env: AZURE_TENANT_ID)")
    auth.add_argument("--client-id", help="Azure AD client/app ID (env: AZURE_CLIENT_ID)")
    auth.add_argument("--client-secret", help="Service-principal secret (env: AZURE_CLIENT_SECRET)")
    auth.add_argument("--pbi-token", help="Pre-acquired PBI bearer token (env: PBI_ACCESS_TOKEN)")

    # Phases
    phases = p.add_argument_group("Migration Phases")
    phases.add_argument("--assess", action="store_true", help="Run assessment only")
    phases.add_argument("--export", action="store_true", help="Export PBIRS content")
    phases.add_argument("--convert", action="store_true", help="Convert for PBI Online")
    phases.add_argument("--import", dest="do_import", action="store_true", help="Import to PBI Online")
    phases.add_argument("--validate", action="store_true", help="Validate deployed content")
    phases.add_argument("--full", action="store_true", help="Run all phases")
    phases.add_argument("--preflight", action="store_true", help="Run connectivity & config checks only (no writes)")

    # Output
    output = p.add_argument_group("Output")
    output.add_argument("--output-dir", help="Output directory (default: artifacts/)")
    output.add_argument("--input-dir", help="Input directory for convert/import")
    output.add_argument("--workspace-id", help="Target PBI Online workspace ID")
    output.add_argument("--workspace-name", help="Target workspace name")

    # Filters
    filters = p.add_argument_group("Filters")
    filters.add_argument("--folder", help="PBIRS folder path to scope migration")
    filters.add_argument("--include-pattern", help="Include items matching regex")
    filters.add_argument("--exclude-pattern", help="Exclude items matching regex")
    filters.add_argument("--content-types", nargs="+", help="Content types: powerbi paginated dataset kpi")

    # Behavior
    behavior = p.add_argument_group("Behavior")
    behavior.add_argument("--dry-run", action="store_true", help="Preview without executing")
    behavior.add_argument("--verbose", action="store_true", help="DEBUG-level logging")
    behavior.add_argument("--parallel", type=int, default=4, help="PBIRS-side parallel downloads (default: 4)")
    behavior.add_argument("--parallelism", type=int, default=1, help="PBI Online publish parallelism (default: 1)")
    behavior.add_argument("--config", help="Load configuration from JSON file")
    behavior.add_argument("--skip-unsupported", action=argparse.BooleanOptionalAction, default=True, help="Skip unsupported items")
    behavior.add_argument("--force-overwrite", action="store_true", help="Overwrite existing items")
    behavior.add_argument("--map-gateway", help="Gateway mapping JSON file")
    behavior.add_argument("--map-folder", help="Folder→workspace mapping JSON (enables multi-workspace import)")
    behavior.add_argument("--plugin", action="append", default=[], metavar="NAME=PATH",
                          help="Load plugin module (repeatable): --plugin myplug=./plugins/my.py")
    behavior.add_argument("--log-file", help="Log to file")
    behavior.add_argument("--migrate-permissions", action=argparse.BooleanOptionalAction, default=True, help="Migrate permissions")
    behavior.add_argument("--migrate-subscriptions", action=argparse.BooleanOptionalAction, default=True, help="Migrate subscriptions")
    behavior.add_argument("--migrate-schedules", action=argparse.BooleanOptionalAction, default=True, help="Migrate refresh schedules")
    behavior.add_argument("--capacity-id", help="Premium/PPU capacity ID")
    behavior.add_argument("--continue-on-error", action="store_true", help="Keep importing remaining items when one publisher step fails")
    behavior.add_argument("--event-log", help="Append per-item events as JSONL to this file")
    behavior.add_argument("--resume", action="store_true", help="Skip phases already marked complete in pipeline.checkpoint.json")
    behavior.add_argument("--reset-checkpoint", action="store_true", help="Clear pipeline checkpoint before starting")
    behavior.add_argument("--metrics-out", help="Write Prometheus metrics to this path after run")
    behavior.add_argument("--capability-report", action="store_true",
                          help="Print environment capability report and exit")
    behavior.add_argument("--capability-report-out",
                          help="Write capability report JSON to this path")

    # Parity (Sprint H)
    parity = p.add_argument_group("Parity (PBIRS feature bridge)")
    parity.add_argument("--preserve-folders", action="store_true",
                        help="Recreate PBIRS folder tree as PBI workspace folders")
    parity.add_argument("--linked-as", choices=["bookmarks", "paginated", "skip"],
                        help="Strategy for converting PBIRS Linked Reports")
    parity.add_argument("--ils-as-audiences", action="store_true",
                        help="Bucket PBIRS item-level security into App audiences")
    parity.add_argument("--role-map", help="JSON file with custom SSRS role → PBI role overrides")
    parity.add_argument("--migrate-cache-plans", action="store_true",
                        help="Translate PBIRS CacheRefreshPlans into PBI refresh schedules")
    parity.add_argument("--migrate-branding", action="store_true",
                        help="Apply PBIRS folder branding as PBI workspace branding + theme")
    parity.add_argument("--brand-file", help="Path to brand descriptor JSON (used with --migrate-branding)")

    # Beyond parity (Sprint I)
    beyond = p.add_argument_group("Beyond parity (sync / waves / diff)")
    beyond.add_argument("--sync-daemon", action="store_true",
                        help="Run as a continuous incremental sync daemon (no phases)")
    beyond.add_argument("--sync-poll-interval", type=float, default=300.0,
                        help="Seconds between sync iterations (default: 300)")
    beyond.add_argument("--sync-max-iterations", type=int,
                        help="Stop after N sync iterations (default: run until SIGINT)")
    beyond.add_argument("--plan-waves", action="store_true",
                        help="Compute a dependency-aware migration wave plan")
    beyond.add_argument("--wave-out", help="Write wave plan to this JSON path")
    beyond.add_argument("--wave", type=int, help="Execute only items in wave N (1-based)")
    beyond.add_argument("--visual-diff-report", help="Write side-by-side visual diff HTML to this path")
    beyond.add_argument("--diff-pairs", help="JSON file with [{name,before,after}, …] pairs for --visual-diff-report")

    # Hardening (Sprint J)
    hardening = p.add_argument_group("Hardening (tracing / streaming / idempotency / bench)")
    hardening.add_argument("--trace-out", help="Write all trace spans + summary to this JSON path")
    hardening.add_argument("--otlp-endpoint",
                           help="POST trace spans to this OTLP/HTTP endpoint (env: OTLP_ENDPOINT)")
    hardening.add_argument("--stream-catalog", action="store_true",
                           help="Use the streaming catalog iterator (lower memory for huge catalogs)")
    hardening.add_argument("--skip-published", action="store_true",
                           help="Skip items whose content hash matches a previous successful publish")
    hardening.add_argument("--reset-hash-store", action="store_true",
                           help="Clear publish.hashes.json before starting")
    hardening.add_argument("--benchmark", type=int, metavar="N",
                           help="Run a synthetic benchmark with N items and exit")
    hardening.add_argument("--benchmark-out",
                           help="Write benchmark report JSON (used with --benchmark)")

    # Gap closure (Sprint K)
    gaps = p.add_argument_group("Gap closure (mobile / AD / gateway / DAX)")
    gaps.add_argument("--migrate-mobile", action="store_true",
                      help="Build best-effort scaffolds for PBIRS Mobile Reports")
    gaps.add_argument("--ad-bridge", action="store_true",
                      help="Generate Windows AD → Azure AD principal manifest from permissions")
    gaps.add_argument("--ad-bridge-csv",
                      help="Path to write the AD bridge CSV (default: <output>/ad_bridge.csv)")
    gaps.add_argument("--ensure-aad-groups", action="store_true",
                      help="Call Graph API to ensure each discovered AD group exists in Azure AD")
    gaps.add_argument("--gateway-auto", action="store_true",
                      help="Auto-create missing gateway datasources from shared .rds connections")
    gaps.add_argument("--gateway-id",
                      help="Target gateway id for --gateway-auto")
    gaps.add_argument("--connection-map-csv",
                      help="Write PBIRS→PBI Online connection mapping CSV (default with --gateway-auto: <input>/connection_mapping.csv)")
    gaps.add_argument("--connection-map-endpoint-csv",
                      help="Write grouped PBIRS→PBI Online endpoint mapping CSV")
    gaps.add_argument("--dax-autofix", action="store_true",
                      help="Apply safe DAX rewrites and write a diff report during conversion")
    gaps.add_argument("--allow-db-query-bridge", action="store_true",
                      help="Opt-in: allow ReportServer DB query bridge for data-driven subscriptions")
    gaps.add_argument("--reportserver-db-conn",
                      help="ReportServer DB connection string (or env: REPORTSERVER_DB_CONN)")
    gaps.add_argument("--security-db-assist", action="store_true",
                      help="Opt-in: use ReportServer DB to resolve security inheritance edge cases")
    gaps.add_argument(
        "--security-conflict-strategy",
        choices=["prefer-api", "prefer-db", "strict-fail-on-diff"],
        default="prefer-api",
        help="Conflict strategy when API-visible permissions differ from DB-resolved effective permissions",
    )

    return p


def main() -> int:
    """Main entry point."""
    # Ensure UTF-8 on Windows
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = _build_parser()
    args = parser.parse_args()

    # Load config file if provided
    if args.config:
        try:
            config = _load_config(args.config)
            args = _merge_config(args, config)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error loading config: {e}", file=sys.stderr)
            return ExitCode.CONFIG_ERROR

    logger = _setup_logging(args.verbose, getattr(args, "log_file", None))

    # Determine which phases to run
    phases = []
    if args.preflight:
        # Preflight is a one-shot check that runs before everything else and exits.
        from pbi_import.preflight import PreflightRunner
        pf = PreflightRunner(args).run()
        for c in pf.checks:
            badge = {"ok": "✓", "warn": "!", "fail": "✗", "skip": "-"}.get(c["status"], "?")
            logger.info("  [%s] %-22s %s", badge, c["name"], c["detail"])
        if not pf.ok:
            logger.error("Preflight failed — fix issues above before running migration")
            return ExitCode.CONFIG_ERROR
        logger.info("Preflight OK")
        return ExitCode.SUCCESS

    if getattr(args, "capability_report", False):
        return _finalise_early_exit(args, logger, _run_capability_report(args, logger))

    if getattr(args, "sync_daemon", False):
        return _finalise_early_exit(args, logger, _run_sync_daemon(args, logger))

    if getattr(args, "plan_waves", False):
        return _finalise_early_exit(args, logger, _run_wave_planner(args, logger))

    if getattr(args, "benchmark", None):
        return _finalise_early_exit(args, logger, _run_benchmark(args, logger))

    if args.full:
        phases = ["assess", "export", "convert", "import", "validate"]
    else:
        if args.assess:
            phases.append("assess")
        if getattr(args, "export", False):
            phases.append("export")
        if getattr(args, "convert", False):
            phases.append("convert")
        if getattr(args, "do_import", False):
            phases.append("import")
        if getattr(args, "validate", False):
            phases.append("validate")

    if not phases:
        parser.print_help()
        return ExitCode.CONFIG_ERROR

    # Validate server URL for phases that need it
    if any(p in phases for p in ("assess", "export")) and not args.server:
        logger.error("--server is required for assessment and export phases")
        return ExitCode.CONFIG_ERROR

    logger.info("Starting PBIRS → PBI Online migration (%s)", ", ".join(phases))
    start_time = time.time()

    from pbi_import.event_log import EventLog
    from pbi_import.pipeline_checkpoint import PipelineCheckpoint
    from pbi_import.tracing import Tracer
    event_log = EventLog(getattr(args, "event_log", None))
    event_log.emit("pipeline", "start", status="started", phases=phases)

    tracer = Tracer(
        enabled=bool(getattr(args, "trace_out", None) or getattr(args, "otlp_endpoint", None)),
        otlp_endpoint=getattr(args, "otlp_endpoint", None),
    )
    args._tracer = tracer  # surface to phase runners

    # Pipeline-level checkpoint for --resume
    root = Path(args.output_dir) if getattr(args, "output_dir", None) else Path("artifacts")
    checkpoint = PipelineCheckpoint(str(root))
    if getattr(args, "reset_checkpoint", False):
        checkpoint.reset()

    # Content-hash store (Sprint J3) — reset if requested
    if getattr(args, "reset_hash_store", False):
        from pbi_import.content_hash import ContentHashStore
        ContentHashStore(str(root)).reset()
        logger.info("Content-hash store reset")

    # Load plugins (--plugin NAME=PATH, repeatable)
    plugin_manager = None
    if getattr(args, "plugin", None):
        from pbi_import.plugin_manager import PluginManager
        plugin_manager = PluginManager()
        for spec in args.plugin:
            if "=" not in spec:
                logger.error("Invalid --plugin spec %r (expected NAME=PATH)", spec)
                return ExitCode.CONFIG_ERROR
            name, path = spec.split("=", 1)
            plugin_manager.register_module(name, path)

    phase_runners = {
        "assess": _run_assessment,
        "export": _run_export,
        "convert": _run_conversion,
        "import": _run_import,
        "validate": _run_validation,
    }

    exit_code = ExitCode.SUCCESS
    for phase in phases:
        if getattr(args, "resume", False) and checkpoint.is_complete(phase):
            logger.info("Phase '%s' already complete (checkpoint) — skipping", phase)
            event_log.emit(phase, "phase_skipped", status="resumed")
            continue

        if plugin_manager:
            plugin_manager.execute_hooks(f"pre_{phase if phase != 'convert' else 'conversion'}", {"args": vars(args)})

        event_log.emit(phase, "phase_start", status="started")
        try:
            with tracer.span(f"phase.{phase}"):
                result = phase_runners[phase](args, logger)
            event_log.emit(phase, "phase_end", status=ExitCode(result).name if result in ExitCode._value2member_map_ else str(result))
            checkpoint.mark_complete(phase, int(result))
            if plugin_manager:
                plugin_manager.execute_hooks(f"post_{phase if phase != 'convert' else 'conversion'}", {"args": vars(args), "result": int(result)})
            if result != ExitCode.SUCCESS:
                exit_code = result
                if result == ExitCode.ERROR:
                    logger.error("Phase '%s' failed — stopping pipeline", phase)
                    break
        except KeyboardInterrupt:
            event_log.emit(phase, "phase_end", status="interrupted")
            checkpoint.mark_failed(phase, "interrupted")
            logger.warning("Interrupted by user")
            return ExitCode.INTERRUPTED
        except Exception as e:
            event_log.emit(phase, "phase_end", status="error", error=str(e))
            checkpoint.mark_failed(phase, str(e))
            logger.error("Phase '%s' failed with error: %s", phase, e, exc_info=args.verbose)
            exit_code = ExitCode.ERROR
            break

    elapsed = time.time() - start_time
    event_log.emit("pipeline", "end", status=ExitCode(exit_code).name, elapsed_seconds=round(elapsed, 1))
    logger.info("Migration finished in %.1f seconds (exit code: %d)", elapsed, exit_code)

    # Export Prometheus metrics if requested
    if getattr(args, "metrics_out", None):
        _emit_prometheus_metrics(args.metrics_out, phases, exit_code, elapsed, root)

    # Write tracer spans + flush OTLP
    if getattr(args, "trace_out", None):
        try:
            tracer.write_json(args.trace_out)
            logger.info("Trace report written to %s", args.trace_out)
        except OSError as e:
            logger.warning("Failed to write trace report: %s", e)
    if getattr(args, "otlp_endpoint", None):
        tracer.flush_otlp()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
