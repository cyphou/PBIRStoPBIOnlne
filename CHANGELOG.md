# Changelog

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
