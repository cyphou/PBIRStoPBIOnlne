# Copilot Instructions — PBIRS to PBI Online Migration

## Project Overview

This project migrates content from **Power BI Report Server (PBIRS)** to **Power BI Online**
through a 5-phase pipeline: Assessment → Export → Conversion → Import → Validation.

## Architecture

- **Entry point**: `migrate.py` — CLI with argparse, dispatches to phase runners
- **Package 1**: `pbirs_export/` — PBIRS REST API client, catalog extraction, assessment
- **Package 2**: `pbi_import/` — conversion, publishing, gateway binding, validation
- **Tests**: `tests/` — pytest, stdlib mocks, no external test dependencies

## Key Technical Decisions

- **Python 3.12+**, stdlib-only core (msal/requests are optional deploy deps)
- **No ORM** — direct REST API calls via urllib
- **PBIRS REST API v2.0** at `{server}/api/v2.0/`
- **PBI REST API** at `https://api.powerbi.com/v1.0/myorg/`
- **Fabric REST API** at `https://api.fabric.microsoft.com/v1/`

## Content Types

| PBIRS Type     | PBI Online Target        | Requirements         |
|----------------|--------------------------|----------------------|
| PowerBIReport  | Power BI Report          | Standard workspace   |
| Report (.rdl)  | Paginated Report         | Premium/PPU          |
| DataSet        | Semantic Model           | Via .pbix import     |
| Kpi            | Scorecard/Goals          | Manual               |
| MobileReport   | N/A (deprecated)         | Not migratable       |

## Development Rules

1. **Read before write** — Always read existing code before modifying
2. **Test first** — Write tests before implementing features
3. **No external deps in core** — Only stdlib for pbirs_export/ and pbi_import/ modules
4. **Type hints** — Use Python 3.12+ syntax (`str | None`, `list[dict]`)
5. **Logging** — Use `logging.getLogger(__name__)` in every module
6. **Error handling** — Catch specific exceptions, log with context

## CLI Reference

```bash
# Assessment only
python migrate.py --server https://pbirs.local/reports --assess --output-dir ./artifacts

# Full pipeline (assess → export → convert → import → validate)
python migrate.py --server https://pbirs.local/reports --full --workspace-id <ID> --output-dir ./artifacts

# Dry run an import phase (no changes pushed to PBI Online)
python migrate.py --import --input-dir ./artifacts/converted --workspace-id <ID> --dry-run

# Specific content types during export
python migrate.py --server https://pbirs.local/reports --export --content-types powerbi paginated

# Auth flags for PBI Online (service principal or pre-acquired token)
python migrate.py --full --tenant-id <TID> --client-id <CID> --client-secret <SECRET>
python migrate.py --import --pbi-token "$ACCESS_TOKEN"

# Resilience flags
python migrate.py --full --continue-on-error --event-log ./artifacts/events.jsonl

# Pre-flight check (no writes — verifies auth, workspace, mapping files)
python migrate.py --preflight --server https://pbirs.local/reports --workspace-id <ID>

# Resume an interrupted run; reset before re-running fresh
python migrate.py --full --resume --output-dir ./artifacts
python migrate.py --full --reset-checkpoint --output-dir ./artifacts

# Multi-workspace dispatch by folder rules
python migrate.py --import --map-folder ./examples/folder_map.json --input-dir ./artifacts/converted

# Parallel file-level publishing
python migrate.py --import --workspace-id <ID> --input-dir ./artifacts/converted --parallelism 4

# Plugins (pre/post phase hooks)
python migrate.py --full --plugin myplug=./plugins/my_hook.py

# Prometheus metrics export after run
python migrate.py --full --metrics-out ./artifacts/metrics.prom

# --- v1.6 parity & beyond ---

# Preserve PBIRS folder tree as workspace folders
python migrate.py --import --workspace-id <ID> --input-dir ./artifacts/converted --preserve-folders

# Convert linked reports (strategy: bookmarks | paginated | skip)
python migrate.py --convert --input-dir ./artifacts/export --output-dir ./artifacts/converted --linked-as bookmarks

# Bridge item-level security into App audiences
python migrate.py --import --workspace-id <ID> --input-dir ./artifacts/converted --ils-as-audiences

# Custom SSRS role overrides + cache plan + branding migration
python migrate.py --import --workspace-id <ID> --input-dir ./artifacts/converted \
  --role-map ./examples/role_map.json --migrate-cache-plans \
  --migrate-branding --brand-file ./artifacts/export/branding.json

# Continuous incremental sync daemon
python migrate.py --sync-daemon --server https://pbirs.local/reports \
  --sync-poll-interval 300 --output-dir ./artifacts

# Dependency-aware wave planning + execute a single wave
python migrate.py --plan-waves --output-dir ./artifacts --wave-out ./artifacts/wave_plan.json
python migrate.py --import --workspace-id <ID> --input-dir ./artifacts/converted --wave 2

# Side-by-side visual diff HTML report after validation
python migrate.py --validate --workspace-id <ID> --input-dir ./artifacts/converted \
  --visual-diff-report ./artifacts/diff.html --diff-pairs ./artifacts/diff_pairs.json

# --- v1.7 hardening & gap closure ---

# Distributed tracing (write JSON, optional OTLP HTTP export)
python migrate.py --full --workspace-id <ID> --trace-out ./artifacts/trace.json
python migrate.py --full --workspace-id <ID> --otlp-endpoint http://otel-collector:4318/v1/traces

# Streaming catalog iteration for huge tenants
python migrate.py --full --workspace-id <ID> --stream-catalog

# Idempotent re-runs (skip already-published items via content hash)
python migrate.py --import --workspace-id <ID> --input-dir ./artifacts/converted --skip-published
python migrate.py --import --workspace-id <ID> --input-dir ./artifacts/converted --reset-hash-store

# Scale benchmarking against synthetic catalogs
python migrate.py --benchmark 10000 --benchmark-out ./artifacts/bench.json

# Mobile Reports best-effort scaffold (writes *.scaffold.json per report)
python migrate.py --convert --input-dir ./artifacts/export --output-dir ./artifacts/converted --migrate-mobile

# Windows AD → Azure AD principal bridge (with optional Graph provisioning)
python migrate.py --import --workspace-id <ID> --input-dir ./artifacts/converted \
  --ad-bridge --ad-bridge-csv ./artifacts/ad_principals.csv --ensure-aad-groups

# Auto-create missing gateway datasources from .rds files
python migrate.py --import --workspace-id <ID> --input-dir ./artifacts/converted \
  --gateway-auto --gateway-id <GATEWAY_GUID>

# Rewrite common DAX compatibility issues (IFERROR→DIVIDE, etc.)
python migrate.py --convert --input-dir ./artifacts/export --output-dir ./artifacts/converted --dax-autofix
```

## Assessment Categories (9)

1. datasource_compatibility — Can the datasource work in PBI Online?
2. report_complexity — Page/visual count complexity
3. security_model — SSRS role mapping complexity
4. gateway_requirements — Does it need a gateway?
5. paginated_features — RDL feature compatibility
6. subscription_migration — Can subscriptions be migrated?
7. capacity_requirements — Does it need Premium?
8. data_model — Data model compatibility
9. custom_visuals — Custom visual availability

## Permission Mapping

- Browser → Viewer
- Content Manager → Admin
- Publisher → Contributor
- Report Builder → Contributor
- System Administrator → Admin
- System User → Viewer
