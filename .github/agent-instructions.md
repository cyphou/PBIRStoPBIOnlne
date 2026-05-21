# Agent Instructions — PBIRS to PBI Online

## Quick Reference
- 5-phase pipeline: Assessment → Export → Conversion → Import → Validation
- Python 3.12+, stdlib-only core
- PBIRS REST API v2.0, PBI REST API, Fabric REST API
- Tests use pytest + unittest.mock (no external mocks)

## Hard Constraints
- Never add external dependencies to core modules
- Always use `logging.getLogger(__name__)` — never `print()` for diagnostics
- Every public function needs a docstring
- Security: escape all HTML output with `html.escape()`, validate URLs, no credential logging

## Workflow Rules
1. Read existing code before making changes
2. Run tests after every change: `python -m pytest tests/ -v`
3. Check types: `pyright`
4. Changes must include tests
5. Assessment scoring must output GREEN/YELLOW/RED — no intermediate states

## Anti-Patterns
- Don't create wrapper classes for single-method utilities
- Don't catch generic `Exception` — catch specific types
- Don't use `os.path` — use `pathlib.Path`
- Don't import from `pbi_import.deploy` in `pbirs_export` (no cross-package dependency)
