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
pbirs-migrate --server https://pbirs.local/reports --phase assessment --output ./artifacts

# Full pipeline
pbirs-migrate --server https://pbirs.local/reports --phase all --output ./artifacts

# Dry run
pbirs-migrate --server https://pbirs.local/reports --phase import --dry-run

# Specific content types
pbirs-migrate --server https://pbirs.local/reports --content-types powerbi paginated
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
