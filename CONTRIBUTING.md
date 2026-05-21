# 🤝 Contributing

## 🛠️ Development Setup

### Prerequisites

- **Python 3.12+**
- **Git**
- No external packages required for core development

### Setup

```bash
git clone <repo-url>
cd PBIReporttoPBIOnline
python -m venv .venv
.venv\Scripts\activate       # Windows
pip install -e ".[dev]"
```

---

## 📁 Project Structure

```
PBIReporttoPBIOnline/
├── migrate.py                      # CLI entry point
├── pbirs_export/                   # 13 modules — assessment & export
│   ├── api_client.py               # PBIRS REST API v2.0 client
│   ├── assessment.py               # 9-category readiness scoring
│   ├── catalog_extractor.py        # Catalog inventory
│   ├── content_downloader.py       # Parallel file download
│   ├── checkpoint.py               # Resume-capable checkpoint
│   ├── progress.py                 # Progress bar
│   ├── rdl_analyser.py             # RDL feature analysis
│   ├── datasource_extractor.py     # Datasource extraction
│   ├── permission_extractor.py     # SSRS permission extraction
│   ├── subscription_extractor.py   # Subscription extraction
│   ├── security_extractor.py       # Security model analysis
│   ├── mapping_generator.py        # CSV mapping templates
│   └── server_info.py              # Server metadata
├── pbi_import/                     # 18 modules — conversion, import, validation
│   ├── converter.py                # Conversion orchestrator
│   ├── rdl_modifier.py             # Strip unsupported RDL features
│   ├── subreport_resolver.py       # Dependency graph
│   ├── power_automate_generator.py # Subscription → Power Automate
│   ├── data_driven_converter.py    # Data-driven subscription conversion
│   ├── scorecard_generator.py      # KPI → Scorecard/Goals
│   ├── workspace_manager.py        # Workspace management
│   ├── report_publisher.py         # Power BI report publishing
│   ├── dataset_publisher.py        # Dataset publishing
│   ├── paginated_publisher.py      # Paginated report publishing
│   ├── gateway_mapper.py           # Gateway binding
│   ├── permission_mapper.py        # SSRS → workspace roles
│   ├── security_converter.py       # Security conversion
│   ├── subscription_migrator.py    # Subscription migration
│   ├── refresh_scheduler.py        # Refresh schedules
│   ├── validator.py                # Post-migration validation
│   ├── migration_report.py         # Migration report
│   ├── rollback.py                 # Rollback engine
│   └── deploy/                     # Auth & API clients (4 modules)
├── tests/                          # 152 tests across 20 files
└── docs/                           # 9 documentation files
```

---

## 📏 No External Dependencies

The `pbirs_export/` and `pbi_import/` packages use **only the Python standard library**.

External deps are **only** in `pbi_import/deploy/` and are optional:
- `azure-identity` — Azure AD authentication
- `requests` — HTTP with retry
- `msal` — Microsoft auth library

---

## ✅ Coding Standards

| Rule | Convention |
|------|-----------|
| **Style** | PEP 8 · max 120 chars per line |
| **Type hints** | Python 3.12+ syntax: `str \| None`, `list[dict]` |
| **Logging** | `logging.getLogger(__name__)` — no `print()` |
| **Paths** | `pathlib.Path` — no `os.path` |
| **Imports** | stdlib only in core packages |
| **Docstrings** | Every public function |
| **Tests** | Write tests before implementing features |

### Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Modules | `snake_case.py` | `content_downloader.py` |
| Classes | `PascalCase` | `CatalogExtractor` |
| Functions | `snake_case` | `extract_catalog()` |
| Constants | `UPPER_SNAKE` | `DEFAULT_WORKERS` |
| Test files | `test_module_name.py` | `test_checkpoint.py` |

---

## 🧪 Running Tests

```bash
# All tests
python -m pytest tests/ -v

# With coverage
python -m pytest tests/ -v --cov=pbirs_export --cov=pbi_import

# Single test file
python -m pytest tests/test_rdl.py -v

# Type checking
pyright
```

### Test Structure

| Test File | Module Under Test | Tests |
|-----------|-------------------|-------|
| `test_api_client.py` | `pbirs_export/api_client.py` | REST API client |
| `test_assessment.py` | `pbirs_export/assessment.py` | Readiness scoring |
| `test_catalog_extractor.py` | `pbirs_export/catalog_extractor.py` | Catalog extraction |
| `test_security_extractor.py` | `pbirs_export/security_extractor.py` | Security analysis |
| `test_mapping_generator.py` | `pbirs_export/mapping_generator.py` | CSV templates |
| `test_progress.py` | `pbirs_export/progress.py` | Progress bar |
| `test_content_downloader.py` | `pbirs_export/content_downloader.py` | Parallel download |
| `test_checkpoint.py` | `pbirs_export/checkpoint.py` | Checkpoint/resume |
| `test_rdl.py` | `pbirs_export/rdl_analyser.py` | RDL feature detection |
| `test_subreport_resolver.py` | `pbi_import/subreport_resolver.py` | Dependency graph |
| `test_power_automate_generator.py` | `pbi_import/power_automate_generator.py` | Flow generation |
| `test_data_driven_converter.py` | `pbi_import/data_driven_converter.py` | Data-driven subs |
| `test_scorecard_generator.py` | `pbi_import/scorecard_generator.py` | KPI → Scorecard |
| `test_converter.py` | `pbi_import/converter.py` | Conversion |
| `test_gateway_mapper.py` | `pbi_import/gateway_mapper.py` | Gateway binding |
| `test_permission_mapper.py` | `pbi_import/permission_mapper.py` | Role mapping |
| `test_security_converter.py` | `pbi_import/security_converter.py` | Security conversion |
| `test_report_publisher.py` | `pbi_import/report_publisher.py` | Report publishing |
| `test_validator.py` | `pbi_import/validator.py` | Validation |
| `test_migration_report.py` | `pbi_import/migration_report.py` | Report generation |

---

## 🔀 Pull Request Process

1. Create a feature branch from `main`
2. Write tests first, then implement
3. Run `pyright` and `pytest` — both must pass
4. Submit PR with description of changes
