# ❓ FAQ — PBIRS to PBI Online Migration

## General

### Does this tool modify anything on the PBIRS server?

No. The tool only **reads** from PBIRS via the REST API v2.0. No changes are made to the source server.

### Can I run this multiple times?

Yes. The import phase uses "CreateOrOverwrite" mode — re-running updates existing reports. Exports are checkpoint-resumable.

### What Python version is required?

**Python 3.12+**. No external packages needed for core migration (assessment, export, conversion).

### Do I need to install external packages?

Only for the **import/deploy phase**: `azure-identity`, `requests`, `msal`. The core engine runs entirely on Python's standard library.

---

## Assessment

### What does GREEN/YELLOW/RED mean?

- 🟢 **GREEN** — Ready to migrate as-is
- 🟡 **YELLOW** — Minor adjustments needed (gateway config, Premium capacity)
- 🔴 **RED** — Significant rework required (unsupported features, deprecated content)

### How are migration waves determined?

Wave 1 = GREEN items (quick wins). Wave 2 = YELLOW items (minor adjustments). Wave 3 = RED items (rework needed).

### What are the 9 assessment categories?

1. Datasource compatibility
2. Report complexity
3. Security model
4. Gateway requirements
5. Paginated features
6. Subscription migration
7. Capacity requirements
8. Data model
9. Custom visuals

---

## Content Types

### Can Mobile Reports be migrated?

Not directly to a native PBI Online artifact. Mobile Reports are still deprecated, but the tool can now generate a **best-effort scaffold** (`*.scaffold.json`) from mobile layouts via `--migrate-mobile` to accelerate manual rebuild.

### Do paginated reports require Premium?

Yes. Paginated reports (.rdl) require **Power BI Premium** or **Premium Per User (PPU)** capacity.

### What about KPIs?

PBIRS KPIs are converted to PBI **Scorecard/Goals API payloads** via the `ScorecardGenerator`. The generated JSON can be imported via the Goals API.

### What happens to custom VB.NET code in paginated reports?

The `rdl_modifier` automatically **strips custom code, assemblies, and classes** from RDL files (with backup). Review `rdl_analysis.json` to see what was detected and removed.

---

## Subscriptions

### Can file-share subscriptions be migrated?

Not directly — PBI Online only supports email delivery. The tool auto-generates **Power Automate flow definitions** as SharePoint alternatives.

### What about data-driven subscriptions?

The `data_driven_converter` generates **conversion plans** with query source hints and CSV templates. The actual Power Automate flows must be finalized manually since data-driven subscriptions require direct database access (not available via PBIRS REST API).

---

## Gateway

### Do I always need a gateway?

Only for **on-premises data sources**. Cloud data sources (Azure SQL, Azure Analysis Services, etc.) connect directly.

### How do I know which reports need a gateway?

The assessment report includes a `gateway_requirements` score for each item. The `mapping_generator` also produces a `gateway_mapping.csv` template.

---

## Permissions

### Will my SSRS permissions transfer automatically?

The tool maps SSRS roles to PBI workspace roles:
- Browser → Viewer
- Content Manager → Admin
- Publisher → Contributor
- Report Builder → Contributor
- System Administrator → Admin
- System User → Viewer

However, PBI Online uses **workspace-level** permissions — item-level granularity is lost.

### What about Windows AD groups?

On-prem AD groups still need an Azure AD target, but the migration now includes an **AD bridge workflow**:
- `ADGroupBridge` discovers principals and emits a CSV manifest (`--ad-bridge`, `--ad-bridge-csv`)
- Optional Azure AD provisioning can be executed when Graph access is available (`--ensure-aad-groups`)

---

## Subreports

### How are subreport dependencies handled?

The `subreport_resolver` builds a **dependency graph** and computes a safe import order using topological sort. Circular dependencies are detected and reported.

### What if there are circular subreport references?

Circular references are flagged in the resolution output. These reports must be refactored to break the cycle before importing.

---

## Troubleshooting

### Import fails with 429 (Too Many Requests)

The PBI REST API has rate limits. The tool respects `retry-after` headers automatically. If imports are slow, reduce `--parallel` to lower concurrency.

### Export was interrupted — do I have to start over?

No. Exports use **checkpoint/resume**. Re-run the same export command and it picks up where it left off.

### Report renders differently in PBI Online

Check for:
- Custom visuals not available in AppSource
- Data model differences after gateway rebinding
- RDL features that were stripped by `rdl_modifier`

### How do I see what the PBIRS REST API can access?

The tool uses PBIRS REST API v2.0 at `{server}/api/v2.0/`. Coverage: ~90% of content metadata. Data-driven subscription queries and some security inheritance details require direct database access (not available via API).
