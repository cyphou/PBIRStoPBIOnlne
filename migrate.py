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

    output_dir = Path(args.output_dir or "artifacts")
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

    output_dir = Path(args.output_dir or "artifacts/export")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Extract catalog
    extractor = CatalogExtractor(client)
    catalog = extractor.extract_catalog(
        folder=getattr(args, "folder", None),
        content_types=getattr(args, "content_types", None),
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

    input_dir = Path(args.input_dir or "artifacts/export")
    output_dir = Path(args.output_dir or "artifacts/converted")
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
    from pbi_import.gateway_mapper import GatewayMapper
    from pbi_import.paginated_publisher import PaginatedPublisher
    from pbi_import.permission_mapper import PermissionMapper
    from pbi_import.refresh_scheduler import RefreshScheduler
    from pbi_import.report_publisher import ReportPublisher
    from pbi_import.subscription_migrator import SubscriptionMigrator
    from pbi_import.workspace_manager import WorkspaceManager

    logger.info("Phase 4: Import — deploying to PBI Online")

    input_dir = Path(args.input_dir or "artifacts/converted")
    workspace_id = getattr(args, "workspace_id", None)
    workspace_name = getattr(args, "workspace_name", None)

    if not workspace_id and not workspace_name:
        logger.error("Either --workspace-id or --workspace-name is required for import")
        return ExitCode.CONFIG_ERROR

    # Initialize workspace
    ws_manager = WorkspaceManager()
    workspace_id = ws_manager.ensure_workspace(workspace_id, workspace_name)

    # Publish datasets
    ds_publisher = DatasetPublisher(workspace_id)
    ds_results = ds_publisher.publish_all(str(input_dir), dry_run=getattr(args, "dry_run", False))

    # Publish reports
    rpt_publisher = ReportPublisher(workspace_id)
    rpt_results = rpt_publisher.publish_all(str(input_dir), dry_run=getattr(args, "dry_run", False))

    # Publish paginated reports
    pag_publisher = PaginatedPublisher(workspace_id)
    pag_results = pag_publisher.publish_all(str(input_dir), dry_run=getattr(args, "dry_run", False))

    # Map gateways
    if getattr(args, "map_gateway", None):
        gw_mapper = GatewayMapper(workspace_id)
        gw_mapper.apply_mapping(str(input_dir), args.map_gateway)

    # Map permissions
    if getattr(args, "migrate_permissions", True):
        perm_mapper = PermissionMapper(workspace_id)
        perm_mapper.apply_permissions(str(input_dir))

    # Migrate subscriptions
    if getattr(args, "migrate_subscriptions", True):
        sub_migrator = SubscriptionMigrator(workspace_id)
        sub_migrator.migrate_all(str(input_dir))

    # Set up refresh schedules
    if getattr(args, "migrate_schedules", True):
        scheduler = RefreshScheduler(workspace_id)
        scheduler.apply_schedules(str(input_dir))

    total = sum(len(r.get("success", [])) for r in [ds_results, rpt_results, pag_results])
    failed = sum(len(r.get("failed", [])) for r in [ds_results, rpt_results, pag_results])
    logger.info("Import complete: %d items deployed, %d failed", total, failed)

    return ExitCode.SUCCESS if failed == 0 else ExitCode.PARTIAL


def _run_validation(args: argparse.Namespace, logger: logging.Logger) -> int:
    """Phase 5: Validate deployed content in PBI Online."""
    from pbi_import.validator import MigrationValidator

    logger.info("Phase 5: Validation — verifying deployed content")

    workspace_id = getattr(args, "workspace_id", None)
    if not workspace_id:
        logger.error("--workspace-id is required for validation")
        return ExitCode.CONFIG_ERROR

    input_dir = Path(args.input_dir or args.output_dir or "artifacts/export")

    validator = MigrationValidator(workspace_id)
    results = validator.validate_all(str(input_dir))

    output_dir = Path(args.output_dir or "artifacts")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save validation report
    with open(output_dir / "validation_report.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)

    # Generate HTML validation report
    validator.generate_html_report(results, str(output_dir / "validation_report.html"))

    passed = results.get("passed", 0)
    failed = results.get("failed", 0)
    logger.info("Validation complete: %d passed, %d failed", passed, failed)

    return ExitCode.SUCCESS if failed == 0 else ExitCode.VALIDATION_ERROR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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

    # Phases
    phases = p.add_argument_group("Migration Phases")
    phases.add_argument("--assess", action="store_true", help="Run assessment only")
    phases.add_argument("--export", action="store_true", help="Export PBIRS content")
    phases.add_argument("--convert", action="store_true", help="Convert for PBI Online")
    phases.add_argument("--import", dest="do_import", action="store_true", help="Import to PBI Online")
    phases.add_argument("--validate", action="store_true", help="Validate deployed content")
    phases.add_argument("--full", action="store_true", help="Run all phases")

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
    behavior.add_argument("--parallel", type=int, default=4, help="Parallel operations (default: 4)")
    behavior.add_argument("--config", help="Load configuration from JSON file")
    behavior.add_argument("--skip-unsupported", action="store_true", default=True, help="Skip unsupported items")
    behavior.add_argument("--force-overwrite", action="store_true", help="Overwrite existing items")
    behavior.add_argument("--map-gateway", help="Gateway mapping JSON file")
    behavior.add_argument("--log-file", help="Log to file")
    behavior.add_argument("--migrate-permissions", action="store_true", default=True, help="Migrate permissions")
    behavior.add_argument("--migrate-subscriptions", action="store_true", default=True, help="Migrate subscriptions")
    behavior.add_argument("--migrate-schedules", action="store_true", default=True, help="Migrate refresh schedules")
    behavior.add_argument("--capacity-id", help="Premium/PPU capacity ID")

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

    phase_runners = {
        "assess": _run_assessment,
        "export": _run_export,
        "convert": _run_conversion,
        "import": _run_import,
        "validate": _run_validation,
    }

    exit_code = ExitCode.SUCCESS
    for phase in phases:
        try:
            result = phase_runners[phase](args, logger)
            if result != ExitCode.SUCCESS:
                exit_code = result
                if result == ExitCode.ERROR:
                    logger.error("Phase '%s' failed — stopping pipeline", phase)
                    break
        except KeyboardInterrupt:
            logger.warning("Interrupted by user")
            return ExitCode.INTERRUPTED
        except Exception as e:
            logger.error("Phase '%s' failed with error: %s", phase, e, exc_info=args.verbose)
            exit_code = ExitCode.ERROR
            break

    elapsed = time.time() - start_time
    logger.info("Migration finished in %.1f seconds (exit code: %d)", elapsed, exit_code)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
