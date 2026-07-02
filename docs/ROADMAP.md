# 🗺️ Roadmap

## ✅ v1.1 — Performance & Resilience
- [x] Parallel content download with configurable worker count (`--parallel N`)
- [x] Progress bar for long-running operations
- [x] Checkpoint/resume for interrupted exports

## ✅ v1.2 — RDL Analysis & Subreport Resolution
- [x] RDL feature analysis (detect custom code, assemblies, subreports, datasources, parameters)
- [x] Automatic RDL modification — strip unsupported features with backup
- [x] Subreport dependency resolution (topological sort, circular detection, orphan refs)

## ✅ v1.3 — Advanced Conversions
- [x] Power Automate flow generation for unsupported subscriptions (email, file-share, data-driven)
- [x] Data-driven subscription conversion plans with CSV templates
- [x] Scorecard/Goals creation from KPI metadata

---

## ✅ v2.0 — Enterprise Scale
- [x] Multi-workspace migration support (folder → workspace mapping rules)
- [x] Tenant-to-tenant migration with service principal authentication
- [x] Incremental/delta migration (only changed content since last run)
- [x] Web UI dashboard for migration progress monitoring
- [x] Enhanced import API for .pbix files > 1 GB (resumable uploads)
- [x] Workspace app publishing with audience configuration

## ✅ v2.1 — Governance & Compliance
- [x] Sensitivity label propagation (PBIRS → Microsoft Purview labels)
- [x] Data classification scanning — tag datasets by sensitivity before migration
- [x] Endorsement automation — auto-promote/certify migrated content based on assessment score
- [x] Migration audit trail — immutable log with who/what/when for compliance reporting
- [x] Lineage preservation — map PBIRS catalog lineage to PBI lineage view metadata

## ✅ v2.2 — Advanced Security
- [x] Row-Level Security (RLS) auto-generation from PBIRS item-level permissions
- [x] Object-Level Security (OLS) mapping from SSRS hidden fields/columns
- [x] Azure AD group auto-provisioning from on-prem AD groups (Graph API)
- [x] Permission diff report — before/after comparison of effective access per user

## ✅ v2.3 — Data Source Modernization
- [x] Connection string transformer — auto-rewrite on-prem SQL → Azure SQL / Synapse / Fabric
- [x] Gateway cluster auto-binding with failover preference
- [x] DirectQuery → Import mode conversion advisor (with RU/cost estimate)
- [x] Shared datasource consolidation — deduplicate identical connections across reports

## ✅ v2.4 — Semantic Model Intelligence
- [x] DAX measure health check — detect deprecated functions, non-optimal patterns
- [x] Thin report / shared dataset splitting — separate reports from underlying models
- [x] Composite model detection and migration planning
- [x] Calculation group migration support
- [x] Field parameter auto-creation from PBIRS report parameter patterns

## ✅ v3.0 — Fabric-Native Pipeline
- [x] Direct publish to Fabric workspace via Fabric REST API (lakehouse, warehouse bindings)
- [x] OneLake integration — migrate PBIRS file-share content to OneLake storage
- [x] Fabric notebook generation for ETL pipelines replacing SSRS data-driven logic
- [x] Dataflow Gen2 creation from shared datasource definitions
- [x] Fabric capacity auto-scaling recommendations based on report complexity scores

## ✅ v3.1 — Multi-Source Federation
- [x] SSRS (non-PBIRS) server support — standard SQL Server Reporting Services migration
- [x] Batch migration orchestrator — queue multiple PBIRS servers into a single pipeline
- [x] Cross-server deduplication — detect identical reports across source servers
- [x] Centralized migration registry (SQLite) for enterprise-wide tracking

## 📌 v3.2 — AI-Assisted Migration
- [ ] GPT-powered VB.NET custom code → DAX/M expression translator
- [ ] Natural language migration summary generation per report
- [ ] Auto-generated test cases from report metadata (expected visuals, row counts)
- [ ] Smart wave planning — AI-driven migration wave grouping by risk/dependency/priority
- [ ] Anomaly detection — flag reports whose post-migration metrics deviate from source

## ✅ v3.3 — Validation & Testing
- [x] Visual regression testing — render source vs target reports and compare screenshots
- [x] Data validation framework — row count / checksum / sample-row comparison per dataset
- [x] Automated UAT report generation with sign-off workflows
- [x] Performance benchmark suite — measure render time, refresh time pre/post migration
- [x] Subscription delivery verification — confirm emails/exports actually arrive

## ✅ v3.4 — Operations & Observability
- [x] Prometheus/Grafana metrics exporter (migration throughput, error rates, queue depth)
- [x] Azure Monitor / Application Insights integration for production pipeline telemetry
- [x] Slack / Teams notification webhooks for phase completion and failure alerts
- [x] Cost estimator — project Premium/PPU/Fabric capacity costs based on migrated content
- [x] Scheduled migration runs — cron/Task Scheduler for recurring incremental syncs

## ✅ v4.0 — Platform & Ecosystem
- [x] Plugin architecture — extensible content-type handlers via extension points
- [x] REST API server mode — expose migration pipeline as a service (stdlib http.server)
- [x] GitHub Actions / Azure DevOps pipeline templates for CI/CD-driven migration

## ✅ v5.0 — PBIRS Feature-Complete Parity (Sprint H)
- [x] Workspace folder hierarchy preservation (`--preserve-folders`)
- [x] Linked Report bookmarks / paginated overrides (`--linked-as`)
- [x] Item-Level Security → App audience bucketing (`--ils-as-audiences`)
- [x] Custom SSRS role overrides (`--role-map`)
- [x] CacheRefreshPlan → PBI refresh schedules (`--migrate-cache-plans`)
- [x] Folder portal branding → workspace branding + theme (`--migrate-branding`)

## ✅ v5.1 — Continuous & Stakeholder-Facing (Sprint I)
- [x] Continuous sync daemon (`--sync-daemon`)
- [x] Dependency-aware wave planner (`--plan-waves`, `--wave N`)
- [x] Side-by-side visual diff HTML report (`--visual-diff-report`)

---

## ✅ v6.0 — Hardening (Sprint J)
- [x] **Tracing** — stdlib span tracer with nested parent tracking + optional OTLP/HTTP-JSON export. Every phase + early-exit mode emits spans (`--trace-out`, `--otlp-endpoint`)
- [x] **Streaming catalogs** — lazy `CatalogStream` (list/JSON/JSONL) with `.batched`, `.filter`, `.map` for memory-bound runs at 10k+ items (`--stream-catalog`)
- [x] **Content-hash idempotency** — SHA1 store keyed by `{ws,path,name}` lets re-runs skip already-published items (`--skip-published`, `--reset-hash-store`)
- [x] **Benchmark harness** — deterministic synthetic catalog generator + min/max/mean/median timer with built-in scale-test phases (`--benchmark N --benchmark-out`)
- [x] **Hardened Docker image** — multi-stage non-root build (`pbirs` UID 10001), pre-built venv, `/artifacts` volume, healthcheck

## ✅ v6.1 — PBIRS Gap Closure (Sprint K)
- [x] **Mobile Reports scaffold** — `MobileReportExtractor` parses `.rsmobile/.json/.xml` tile layouts and emits PBI visual scaffolds (`--migrate-mobile`)
- [x] **AD → AAD bridge** — `ADGroupBridge` discovers Windows AD principals, splits users/groups, emits CSV manifest, and (with Graph client) provisions Azure AD groups (`--ad-bridge`, `--ensure-aad-groups`)
- [x] **Gateway auto-create** — `GatewayAutoCreator` parses `.rds` files, plans + creates missing gateway datasources, emits `gateway_mapping.auto.json` (`--gateway-auto --gateway-id`)
- [x] **DAX auto-fixer** — rule-based rewriter (`IFERROR→DIVIDE`, `COUNTROWS(DISTINCT)→DISTINCTCOUNT`, `IF(HASONEVALUE)→SELECTEDVALUE`, `CONTAINS→IN VALUES`, `EARLIER→TODO`) with per-rule reporting (`--dax-autofix`)

---

## 🎯 v6.2 — Limitation-Driven Stabilization (Next)

Focus: close unresolved items from `docs/KNOWN_LIMITATIONS.md` before adding net-new capabilities.

### 1) Large PBIX import path (> 1 GB)
- [x] Implement enhanced import flow for large `.pbix` files (chunked/resumable upload path where required by API)
- [x] Add automatic strategy selection (standard import vs enhanced import)
- [x] Add end-to-end tests for 3 file bands: `<500MB`, `500MB-1GB`, `>1GB`
- [x] Emit explicit diagnostics and remediation hints when tenant/workspace settings block large import

### 2) Data-driven subscription query bridge
- [x] Add optional ReportServer DB connector module for extracting data-driven subscription query text
- [x] Merge DB-extracted query metadata into conversion plans and generated CSV templates
- [x] Add secure secret handling + redaction for logged query artifacts
- [x] Add `--allow-db-query-bridge` feature flag with clear consent prompt in CLI output

### 3) Security inheritance depth
- [x] Add optional DB-assisted inheritance resolver for PBIRS item security edge cases
- [x] Emit `security_gap_report.json` listing API-visible vs DB-resolved effective permissions
- [x] Add conflict strategy flags (`prefer-api`, `prefer-db`, `strict-fail-on-diff`)

### 4) Validation hardening for semantic parity
- [x] Add custom visual availability precheck against target tenant/app catalog
- [x] Add post-import dataset binding parity checks with actionable fix suggestions
- [x] Expand visual diff report with "high-risk mismatch" scoring and top offenders summary

## 🎯 v6.3 — Default-On Reliability

Focus: make limitation workarounds safe and operational by default.

- [ ] Promote large-file and DB bridge features from opt-in to default-on when prerequisites are met
- [x] Add compatibility matrix command (`--capability-report`) to print what migration features are active for the current environment
- [ ] Add recovery playbooks in generated artifacts for partial-failure scenarios
- [ ] Add stress tests for 10k+ item catalogs with mixed large-file import workloads

### Gateway and connection hardening

- [x] Complete gateway auto-create flow by auto-binding published datasets/reports from generated mapping
- [x] Emit unified gateway connection report artifact (`gateway_connection_report.json`) with create/bind summary and details
- [x] Emit grouped endpoint mapping CSV (`connection_mapping_by_endpoint.csv`) for bulk mapping by server/database

## 🎯 v6.4 — Closure Criteria

Release closes when all are true:

- [ ] `KNOWN_LIMITATIONS.md` has no remaining ❌ entries for core migration path
- [ ] `KNOWN_LIMITATIONS.md` has no ⚠️ entries without an automated mitigation path
- [ ] Test suite includes dedicated regression coverage for each formerly open limitation
- [ ] README "Capabilities" and limitations status are fully consistent

