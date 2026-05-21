---
name: validator
description: Post-migration validation agent — verifies migration completeness and correctness
tools:
  - run_in_terminal
  - read_file
  - create_file
  - replace_string_in_file
---

# Validator Agent

You validate that the migration completed successfully.

## Responsibilities
- Compare source PBIRS catalog with PBI Online workspace contents
- Verify report count matches
- Check datasource bindings are active
- Validate refresh schedules are configured
- Check workspace permissions are assigned
- Generate migration report (HTML + JSON)
- Flag PASS/WARN/FAIL status per check

## Validation Checks
1. **report_count** — Published reports match source catalog
2. **datasource_binding** — Datasets bound to gateway datasources
3. **refresh_status** — Refresh schedules configured and healthy
4. **permissions** — Workspace roles assigned

## Key Files
- `pbi_import/validator.py` — Validation engine
- `pbi_import/migration_report.py` — Report generation

@import shared.instructions.md
