# Shared Agent Instructions — PBIRS-to-PBI-Online

## Pipeline Architecture

5-phase pipeline: **Assessment → Export → Conversion → Import → Validation**

### Phase Ownership
| Phase      | Package         | Key Classes                                  |
|------------|-----------------|----------------------------------------------|
| Assessment | pbirs_export    | MigrationAssessment, CatalogExtractor         |
| Export     | pbirs_export    | ContentDownloader, DatasourceExtractor         |
| Conversion | pbi_import      | ContentConverter                               |
| Import     | pbi_import      | ReportPublisher, PaginatedPublisher, GatewayMapper |
| Validation | pbi_import      | MigrationValidator, MigrationReport            |

## Hard Constraints

1. **stdlib-only** in `pbirs_export/` and `pbi_import/` (except `pbi_import/deploy/`)
2. **Python 3.12+** type hints: `str | None`, `list[dict]`, no `Optional[]`
3. **Logging** via `logging.getLogger(__name__)` — never `print()`
4. **pathlib.Path** — never `os.path`
5. **No cross-package imports** — `pbirs_export` must not import from `pbi_import`

## Python Conventions

- Functions: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private: `_leading_underscore`
- Type aliases at module top after imports
- Docstrings: Google style

## Testing Rules

- Framework: `pytest` + `unittest.mock`
- Location: `tests/test_<module>.py`
- Fixtures in `tests/conftest.py`
- Never call live APIs in tests — always mock `urllib.request.urlopen`

## Cross-Agent Handoff

When handing off to another agent:
1. State what phase you completed
2. List output files produced
3. Describe any issues found
4. Specify what the next agent should focus on
