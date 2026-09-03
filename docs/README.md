# Documentation

Current release baseline: **v1.8.0** (see `../CHANGELOG.md` and `ROADMAP.md`).

## Guides

- [ARCHITECTURE.md](ARCHITECTURE.md) - Pipeline architecture, module map, and data flow
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Azure AD app setup, authentication, and deployment runbook
- [MIGRATION_CHECKLIST.md](MIGRATION_CHECKLIST.md) - Pre-migration, migration, and validation checklist
- [FAQ.md](FAQ.md) - Operational and troubleshooting FAQ
- [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) - Open limitations, status, and mitigations
- [ROADMAP.md](ROADMAP.md) - Implemented and planned capabilities
- [GATEWAY_MAPPING_GUIDE.md](GATEWAY_MAPPING_GUIDE.md) - Gateway mapping and binding guidance
- [PERMISSION_MAPPING_GUIDE.md](PERMISSION_MAPPING_GUIDE.md) - SSRS to Power BI permission model mapping
- [PAGINATED_REPORT_GUIDE.md](PAGINATED_REPORT_GUIDE.md) - Paginated report migration guidance
- [PBIX_UPLOAD_GUIDE.md](PBIX_UPLOAD_GUIDE.md) - PBIRS PBIX upload compatibility diagnostics
- [SECURITY_PRIVACY_CHECKLIST.md](SECURITY_PRIVACY_CHECKLIST.md) - Required privacy and secret-review checks before release

## Quick Reference

### Core CLI flows

```bash
python migrate.py --server https://pbirs.company.com/reports --preflight --use-windows-auth --verbose
python migrate.py --server https://pbirs.company.com/reports --assess --use-windows-auth
python migrate.py --server https://pbirs.company.com/reports --export --use-windows-auth --output-dir artifacts/export
python migrate.py --convert --input-dir artifacts/export --output-dir artifacts/converted
python migrate.py --import --input-dir artifacts/converted --workspace-id <WORKSPACE_ID>
python migrate.py --validate --input-dir artifacts/converted --workspace-id <WORKSPACE_ID>
```

On Windows, `--use-windows-auth` uses the current Windows logon and the Windows trusted certificate store by default. Add `--prompt-windows-credentials` when PBIRS requires alternate credentials.

### CSV-driven import orchestration

```bash
python scripts/csv_to_pbi_online_import.py \
  --converted-dir artifacts/converted \
  --csv-dir artifacts/export \
  --run-dir artifacts/csv_import_run \
  --tenant-id <TENANT_ID> \
  --client-id <CLIENT_ID> \
  --client-secret <CLIENT_SECRET> \
  --create-missing-connections
```

### Capability checks

```bash
python migrate.py --capability-report --capability-report-out artifacts/capability_report.json
```

### Semantic model merge assessment

```bash
python migrate.py --assess-semantic-merge --output-dir artifacts
```

Outputs:
- artifacts/semantic_merge_assessment.json
- artifacts/semantic_merge_assessment.html

### PBIX compatibility report

```bash
python migrate.py --pbix-compatibility-report --input-dir artifacts/converted --output-dir artifacts
```

Outputs:
- artifacts/pbix_compatibility_report.json
- artifacts/pbix_compatibility_report.html

## Project Structure

| Module | Purpose |
|--------|---------|
| `migrate.py` | Main CLI orchestrator (assess, export, convert, import, validate) |
| `pbirs_export/` | Source inventory, extraction, assessment, mapping templates |
| `pbi_import/` | Conversion, publish, binding, validation, rollout helpers |
| `scripts/` | Operational utilities (PBIX probes, state reset, CSV orchestrator) |
| `docs/` | User and operator documentation |
| `tests/` | Unit and integration test suite |
