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

## 🔜 v2.0 — Enterprise Scale
- [ ] Multi-workspace migration support (folder → workspace mapping rules)
- [ ] Tenant-to-tenant migration with service principal authentication
- [ ] Incremental/delta migration (only changed content since last run)
- [ ] Web UI dashboard for migration progress monitoring
- [ ] Enhanced import API for .pbix files > 1 GB (resumable uploads)
- [ ] Workspace app publishing with audience configuration

## 📌 v2.1 — Governance & Compliance
- [ ] Sensitivity label propagation (PBIRS → Microsoft Purview labels)
- [ ] Data classification scanning — tag datasets by sensitivity before migration
- [ ] Endorsement automation — auto-promote/certify migrated content based on assessment score
- [ ] Migration audit trail — immutable log with who/what/when for compliance reporting
- [ ] Lineage preservation — map PBIRS catalog lineage to PBI lineage view metadata

## 📌 v2.2 — Advanced Security
- [ ] Row-Level Security (RLS) auto-generation from PBIRS item-level permissions
- [ ] Object-Level Security (OLS) mapping from SSRS hidden fields/columns
- [ ] Azure AD group auto-provisioning from on-prem AD groups (Graph API)
- [ ] Service principal per-workspace isolation for multi-tenant deployments
- [ ] Permission diff report — before/after comparison of effective access per user

## 📌 v2.3 — Data Source Modernization
- [ ] Connection string transformer — auto-rewrite on-prem SQL → Azure SQL / Synapse / Fabric
- [ ] Gateway cluster auto-binding with failover preference
- [ ] DirectQuery → Import mode conversion advisor (with RU/cost estimate)
- [ ] Shared datasource consolidation — deduplicate identical connections across reports
- [ ] Parameterized datasource migration (server/database parameters preserved)

## 📌 v2.4 — Semantic Model Intelligence
- [ ] DAX measure health check — detect deprecated functions, non-optimal patterns
- [ ] Thin report / shared dataset splitting — separate reports from underlying models
- [ ] Composite model detection and migration planning
- [ ] Calculation group migration support
- [ ] Field parameter auto-creation from PBIRS report parameter patterns

## 📌 v3.0 — Fabric-Native Pipeline
- [ ] Direct publish to Fabric workspace via Fabric REST API (lakehouse, warehouse bindings)
- [ ] OneLake integration — migrate PBIRS file-share content to OneLake storage
- [ ] Fabric notebook generation for ETL pipelines replacing SSRS data-driven logic
- [ ] Dataflow Gen2 creation from shared datasource definitions
- [ ] Fabric capacity auto-scaling recommendations based on report complexity scores

## 📌 v3.1 — Multi-Source Federation
- [ ] SSRS (non-PBIRS) server support — standard SQL Server Reporting Services migration
- [ ] Tableau workbook (.twbx) ingestion as secondary source (cross-platform consolidation)
- [ ] Batch migration orchestrator — queue multiple PBIRS servers into a single pipeline
- [ ] Cross-server deduplication — detect identical reports across source servers
- [ ] Centralized migration registry (SQLite/Cosmos DB) for enterprise-wide tracking

## 📌 v3.2 — AI-Assisted Migration
- [ ] GPT-powered VB.NET custom code → DAX/M expression translator
- [ ] Natural language migration summary generation per report
- [ ] Auto-generated test cases from report metadata (expected visuals, row counts)
- [ ] Smart wave planning — AI-driven migration wave grouping by risk/dependency/priority
- [ ] Anomaly detection — flag reports whose post-migration metrics deviate from source

## 📌 v3.3 — Validation & Testing
- [ ] Visual regression testing — render source vs target reports and compare screenshots
- [ ] Data validation framework — row count / checksum / sample-row comparison per dataset
- [ ] Automated UAT report generation with sign-off workflows
- [ ] Performance benchmark suite — measure render time, refresh time pre/post migration
- [ ] Subscription delivery verification — confirm emails/exports actually arrive

## 📌 v3.4 — Operations & Observability
- [ ] Prometheus/Grafana metrics exporter (migration throughput, error rates, queue depth)
- [ ] Azure Monitor / Application Insights integration for production pipeline telemetry
- [ ] Slack / Teams notification webhooks for phase completion and failure alerts
- [ ] Cost estimator — project Premium/PPU/Fabric capacity costs based on migrated content
- [ ] Scheduled migration runs — cron/Task Scheduler for recurring incremental syncs

## 📌 v4.0 — Platform & Ecosystem
- [ ] Plugin architecture — extensible content-type handlers via entry points
- [ ] REST API server mode — expose migration pipeline as a service (FastAPI)
- [ ] VS Code extension — migrate/assess directly from the editor with inline diagnostics
- [ ] GitHub Actions / Azure DevOps pipeline templates for CI/CD-driven migration
- [ ] Multi-language SDK (Python, .NET, PowerShell) for programmatic migration control
