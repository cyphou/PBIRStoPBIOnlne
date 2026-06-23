# Changelog

## v1.7.0 — Sprint 8 — Hardening & PBIRS Gap Closure

### Hardening (Sprint J) — production readiness
- **`pbi_import/tracing.py`** (new) — stdlib-only span tracer with nested parent tracking and optional OTLP/HTTP-JSON export. Every phase is wrapped in a span; early-exit modes (benchmark/sync-daemon/wave-planner) emit synthetic spans so traces are always non-empty (`--trace-out PATH`, `--otlp-endpoint URL`)
- **`pbi_import/catalog_stream.py`** (new) — lazy iterator over huge catalogs (`from_list`, `from_json`, truly streaming `from_jsonl`) with `.batched(n)`, `.filter(pred)`, `.map(fn)`, plus `write_jsonl` helper (`--stream-catalog`)
- **`pbi_import/content_hash.py`** (new) — SHA1-based idempotency store keyed by `{workspace_id, path, name}` with content-aware re-publish detection. Re-runs skip already-published items (`--skip-published`, `--reset-hash-store`)
- **`pbi_import/benchmark_harness.py`** (new) — deterministic synthetic catalog generator + min/max/mean/median timer. Three built-in phases (`stream_iter_only`, `stream_filter_powerbi`, `assessment`) run end-to-end against synthetic catalogs (`--benchmark N --benchmark-out PATH`)
- **`Dockerfile`** (hardened) — multi-stage build with non-root `pbirs` user (UID 10001, no shell, no home), pre-built `/opt/venv` from `requirements.txt`, `/artifacts` volume, healthcheck, and pinned entrypoint

### Gap closure (Sprint K) — close remaining PBIRS deltas
- **`pbi_import/mobile_extractor.py`** (new) — best-effort scaffold for deprecated PBIRS Mobile Reports. Parses `.rsmobile/.json/.xml` tile layouts, maps 8 known visual types (Gauge→gauge, Chart→chart, Indicator→kpi, …), writes `{stem}.scaffold.json` per report (`--migrate-mobile`)
- **`pbi_import/ad_group_bridge.py`** (new) — discovers Windows AD principals in PBIRS permissions, splits users vs groups via heuristics, suggests Azure AD display names + mail nicknames, writes a CSV manifest, and optionally calls Graph to provision AAD groups (`--ad-bridge`, `--ad-bridge-csv PATH`, `--ensure-aad-groups`)
- **`pbi_import/gateway_autocreate.py`** (new) — parses `.rds` connection strings (SQL/Oracle/ODBC/AS/PostgreSQL/MySQL/Snowflake/OData/Web), plans missing gateway datasources, creates them via PBI REST, and emits a `gateway_mapping.auto.json` consumable by `GatewayMapper` (`--gateway-auto --gateway-id GW`)
- **`pbi_import/dax_auto_fixer.py`** (new) — rule-based DAX rewriter (`IFERROR`→`DIVIDE`, `COUNTROWS(DISTINCT(c))`→`DISTINCTCOUNT(c)`, `IF(HASONEVALUE,…)`→`SELECTEDVALUE`, `CONTAINS`→`IN VALUES`, `EARLIER`→TODO marker). Reports per-rule statistics (`--dax-autofix`)

### CLI
- 13 new flags grouped under "Hardening (tracing / streaming / idempotency / bench)" and "Gap closure (mobile / AD / gateway / DAX)"
- New `_run_benchmark` early-exit mode
- New `_finalise_early_exit` helper guarantees `--trace-out` and `--otlp-endpoint` work for benchmark/sync-daemon/wave-planner modes
- Phase-level spans (`phase.assess`, `phase.export`, `phase.convert`, `phase.import`, `phase.validate`) automatically emitted when tracing is enabled

### Tests
- **`tests/test_sprint_jk.py`** (new) — 46 tests across 9 classes covering all 8 new modules plus CLI integration. Total suite now **513 tests passing** (+46 from 467).

---

## v1.6.0 — Sprint 7 — PBIRS Parity Closeout & Beyond

### Parity (Sprint H) — closes the gap chart
- **`pbi_import/workspace_folder_manager.py`** (new) — recreates PBIRS folder hierarchy as PBI Online workspace folders (`--preserve-folders`)
- **`pbi_import/linked_report_handler.py`** (new) — converts PBIRS Linked Reports via three strategies: `bookmarks`, `paginated`, `skip` (`--linked-as STRATEGY`)
- **`pbi_import/audience_bucketer.py`** (new) — groups item-level security into PBI Online App audiences by ACL signature, with overflow collapsing (`--ils-as-audiences`)
- **`pbi_import/role_mapper.py`** (new) — pluggable SSRS → PBI role overrides via JSON file plus heuristic suggester (`--role-map PATH`)
- **`pbi_import/cache_plan_migrator.py`** (new) — translates PBIRS `CacheRefreshPlan` into PBI `refreshSchedule` payloads (`--migrate-cache-plans`)
- **`pbi_import/branding_migrator.py`** (new) — maps PBIRS portal branding to PBI workspace branding + report theme JSON (`--migrate-branding --brand-file PATH`)

### Beyond parity (Sprint I)
- **`pbi_import/sync_daemon.py`** (new) — long-lived poller for incremental PBIRS → PBI replay with graceful SIGINT/SIGTERM handling (`--sync-daemon --sync-poll-interval N --sync-max-iterations N`)
- **`pbi_import/wave_planner.py`** (new) — dependency-aware topological wave planner with cycle detection and chunking (`--plan-waves --wave-out PATH --wave N`)
- **`pbi_import/visual_diff_report.py`** (new) — side-by-side HTML report with embedded base64 screenshots, summary table, and per-pair diff badges (`--visual-diff-report PATH --diff-pairs PATH`)

### CLI — 13 new flags wired in `migrate.py`
- Parity group: `--preserve-folders`, `--linked-as`, `--ils-as-audiences`, `--role-map`, `--migrate-cache-plans`, `--migrate-branding`, `--brand-file`
- Beyond parity group: `--sync-daemon`, `--sync-poll-interval`, `--sync-max-iterations`, `--plan-waves`, `--wave-out`, `--wave`, `--visual-diff-report`, `--diff-pairs`
- `--sync-daemon` and `--plan-waves` are early-exit modes (no phases run)

### Tests
- **`tests/test_sprint_hi.py`** (new) — 41 tests across 10 classes covering every new module + CLI integration
- Total: 467 tests passing (was 426)

---

## v1.5.0 — Sprint 6 — Scale, Extensibility & Operational Polish

### Pre-flight & Resume (Sprint F)
- **`pbi_import/preflight.py`** (new) — `PreflightRunner` validates PBIRS connectivity, PBI Online auth, workspace access, gateway-mapping file, and folder-mapping file before any writes
- **`pbi_import/pipeline_checkpoint.py`** (new) — `PipelineCheckpoint` tracks per-phase completion in `pipeline.checkpoint.json` so interrupted `--full` runs can resume
- **`migrate.py`** — new CLI flags: `--preflight`, `--resume`, `--reset-checkpoint`, `--metrics-out`
- **`migrate.py`** — dry-run summary table after import (`_print_publish_summary`)

### Multi-Workspace & Plugins (Sprint E)
- **`migrate.py`** — `--map-folder PATH` flag wires `FolderMapper` + `MultiWorkspaceManager` to dispatch items across multiple PBI workspaces based on folder rules
- **`migrate.py`** — `--plugin NAME=PATH` flag (repeatable) loads plugin modules via `PluginManager`; `pre_<phase>` / `post_<phase>` hooks invoked around each phase
- **`migrate.py`** — `--parallelism N` flag forwards to all 3 publishers for file-level parallel import
- **`pbi_import/report_publisher.py`**, **`dataset_publisher.py`**, **`paginated_publisher.py`** — added `workers` kwarg with `ThreadPoolExecutor` for parallel `.pbix` / `.rdl` / dataset uploads

### Observability (Sprint G)
- **`migrate.py`** — `_emit_prometheus_metrics()` writes `migration_duration_seconds`, `migration_exit_code`, `migration_items_exported`, `migration_validation_passed/failed`, and assessment summary gauges in Prometheus exposition format

### Tests
- **`tests/test_sprint_efg.py`** (new) — 21 tests: pipeline checkpoint round-trip & recovery, preflight per-check scenarios, publisher parallelism, CLI flags (`--preflight`, `--resume`, `--reset-checkpoint`, `--metrics-out`, `--parallelism`, `--plugin`), multi-workspace dispatch
- Total: 426 tests passing (was 405)

---

## v1.4.0 — Sprint 5 — CLI Hardening & Production Reliability

### CLI Orchestrator Rewrite
- **`migrate.py`** — full rewrite of `_run_import` and `_run_validation` to use real publisher / mapper / validator APIs (previously called nonexistent `apply_*` methods, would crash at runtime)
- **`migrate.py`** — new `_phase_dirs(args, phase)` helper chains `--full` subfolders (`./export`, `./converted`) so phases don't clobber each other
- **`migrate.py`** — `_run_export` now propagates `--include-pattern` / `--exclude-pattern` to the catalog extractor
- **`migrate.py`** — new CLI flags: `--tenant-id`, `--client-id`, `--client-secret`, `--pbi-token`, `--continue-on-error`, `--event-log`

### PBI Online Client Hardening
- **`pbi_import/deploy/client_factory.py`** (new) — `PbiClientFactory.from_args()` resolves auth from CLI flags or env (`PBI_ACCESS_TOKEN`, `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`)
- **`pbi_import/deploy/pbi_client.py`** — added retry loop (5 attempts) on 429/5xx with `Retry-After` header honouring and exponential backoff + jitter; added `token_provider` callable for refresh-on-demand
- **`pbi_import/deploy/auth.py`** — `get_token()` now caches with expiry tracking and refreshes within `EXPIRY_MARGIN_SECONDS = 60` of expiry; `_acquire_*_token()` return `(token, lifetime)` tuples

### Observability & Validation
- **`pbi_import/event_log.py`** (new) — thread-safe JSONL append-only event log; wired into `migrate.main()` to emit `pipeline.start/end` + `phase_start/phase_end` per phase
- **`pbi_import/validator.py`** — added `validate_all(input_dir, workspace_id)`, `_load_catalog()`, `generate_html_report()` to support the rewritten validate phase

### Build Fix
- **`pyproject.toml`** — fixed bogus `build-backend = "setuptools.backends._legacy:_Backend"` → `setuptools.build_meta` (was breaking `pip install -e .`)

### Tests
- **`tests/test_cli_smoke.py`** (new) — 7 E2E smoke tests: assess-only, import-only, validate-only, full-pipeline, `_phase_dirs` chaining, export pattern propagation, event log JSONL output
- Total: 405 tests passing (was 398)

---

## v1.3.0 — Sprint 4 — Advanced Conversions

### Power Automate Integration
- **`pbi_import/power_automate_generator.py`** — `PowerAutomateGenerator` class with `generate_flows()`, `_build_email_flow()`, `_build_fileshare_flow()`, `_build_data_driven_flow()` — converts PBIRS subscriptions to Power Automate flow definitions
- Email subscriptions → email flow definitions with recipients, subject, body
- File-share subscriptions → SharePoint flow definitions with folder/file mapping
- Data-driven subscriptions → flow stubs with query source hints
- 9 tests in `tests/test_power_automate_generator.py`

### Data-Driven Subscription Conversion
- **`pbi_import/data_driven_converter.py`** — `DataDrivenConverter` class with `convert()`, `_build_plan()`, `_build_csv_template()` — conversion plans for data-driven subscriptions
- Query-based recipient lists → Power Automate flow with DB hints
- CSV template generation for manual recipient list migration
- 8 tests in `tests/test_data_driven_converter.py`

### Scorecard/Goals Generation
- **`pbi_import/scorecard_generator.py`** — `ScorecardGenerator` class with `generate()`, `_build_scorecard()`, `_build_goal()` — converts KPI metadata to PBI Scorecard/Goals API payloads
- Value/goal/status expressions → Goals API properties
- Suggested status rules from KPI thresholds
- 12 tests in `tests/test_scorecard_generator.py`

---

## v1.2.0 — Sprint 3 — RDL Analysis & Subreport Resolution

### RDL Feature Analysis
- **`pbirs_export/rdl_analyser.py`** — `RdlAnalyser` class with `analyse()`, `detect_custom_code()`, `detect_custom_assemblies()`, `detect_subreports()`, `detect_datasources()`, `detect_parameters()` — automated RDL feature detection
- Detects custom VB.NET code, custom assemblies, subreport references
- Outputs `rdl_analysis.json` with per-report feature inventory
- 14 tests in `tests/test_rdl.py`

### RDL Modification
- **`pbi_import/rdl_modifier.py`** — `RdlModifier` class with `modify()`, `strip_custom_code()`, `strip_custom_assemblies()`, `strip_custom_classes()` — strips unsupported RDL features
- Backs up original RDL before modification
- Change tracking with modification log

### Subreport Resolution
- **`pbi_import/subreport_resolver.py`** — `SubreportResolver` class with `resolve()` — dependency graph + topological sort
- Kahn's algorithm for safe import order
- Circular dependency detection and orphan reference tracking
- Returns `import_order`, `circular`, `orphan_refs`, `dependency_graph`
- 7 tests in `tests/test_subreport_resolver.py`

---

## v1.1.0 — Sprint 2 — Performance & Resilience

### Parallel Downloads
- **`pbirs_export/content_downloader.py`** — `ContentDownloader` with `download_all()` — parallel file download using `concurrent.futures.ThreadPoolExecutor`
- Configurable worker count via `--parallel N` (default: 4)
- Progress tracking integration
- 9 tests in `tests/test_content_downloader.py`

### Progress Bar
- **`pbirs_export/progress.py`** — `ProgressBar` class with `update()`, `finish()` — console progress bar for long-running operations
- 6 tests in `tests/test_progress.py`

### Checkpoint & Resume
- **`pbirs_export/checkpoint.py`** — `CheckpointManager` class with `save()`, `load()`, `mark_complete()`, `is_complete()` — atomic JSON checkpoint
- Resume interrupted exports from last completed item
- Parallel-safe with per-item tracking
- 9 tests in `tests/test_checkpoint.py`

---

## v1.0.0 — Sprint 1 — Foundation

### 5-Phase Pipeline
- **`migrate.py`** — CLI entry point with argparse, 5-phase dispatch (`_run_assessment()`, `_run_export()`, `_run_conversion()`, `_run_import()`, `_run_validation()`)
- `--full`, `--assess`, `--export`, `--convert`, `--import`, `--validate` phase flags
- `--dry-run`, `--parallel`, `--config`, filter flags

### PBIRS Extraction (8 modules)
- **`pbirs_export/api_client.py`** — `PBIRSClient` with all REST API v2.0 endpoints
- **`pbirs_export/assessment.py`** — `MigrationAssessment` with 9-category scoring
- **`pbirs_export/catalog_extractor.py`** — `CatalogExtractor` with folder/item enumeration
- **`pbirs_export/content_downloader.py`** — content file download
- **`pbirs_export/datasource_extractor.py`** — datasource connection extraction
- **`pbirs_export/permission_extractor.py`** — SSRS role and permission extraction
- **`pbirs_export/subscription_extractor.py`** — subscription and schedule extraction
- **`pbirs_export/server_info.py`** — server version and config metadata

### Security Analysis (2 modules)
- **`pbirs_export/security_extractor.py`** — AD group enumeration, inheritance analysis, role composition
- **`pbi_import/security_converter.py`** — security model conversion, RLS generation

### CSV Mapping Templates
- **`pbirs_export/mapping_generator.py`** — `MappingGenerator` with `generate_all()` — gateway, permission, datasource, workspace CSV templates

### PBI Online Deployment (10 modules)
- **`pbi_import/converter.py`** — content conversion orchestrator
- **`pbi_import/workspace_manager.py`** — workspace creation and management
- **`pbi_import/report_publisher.py`** — Power BI report publishing
- **`pbi_import/dataset_publisher.py`** — dataset/semantic model publishing
- **`pbi_import/paginated_publisher.py`** — paginated report publishing (Premium)
- **`pbi_import/gateway_mapper.py`** — gateway datasource binding
- **`pbi_import/permission_mapper.py`** — SSRS → workspace role mapping
- **`pbi_import/subscription_migrator.py`** — subscription migration
- **`pbi_import/refresh_scheduler.py`** — refresh schedule configuration
- **`pbi_import/migration_report.py`** — HTML + JSON migration report

### Validation & Rollback
- **`pbi_import/validator.py`** — post-migration validation (count, bindings, refresh, permissions)
- **`pbi_import/rollback.py`** — rollback engine for failed migrations

### Deployment Auth
- **`pbi_import/deploy/auth.py`** — Azure AD (Service Principal, Managed Identity, Device Code)
- **`pbi_import/deploy/pbi_client.py`** — PBI REST API v1.0 wrapper
- **`pbi_import/deploy/fabric_client.py`** — Fabric REST API wrapper
- **`pbi_import/deploy/config.py`** — environment configuration

### Infrastructure
- CI pipeline with GitHub Actions (lint, test, validate)
- 8 Copilot agent configurations
- Full documentation suite (9 docs)
- Example configuration files
