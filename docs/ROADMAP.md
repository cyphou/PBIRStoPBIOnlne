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
- [ ] Multi-workspace migration support (folder → workspace mapping)
- [ ] Tenant-to-tenant migration
- [ ] Incremental/delta migration (only changed content since last run)
- [ ] Web UI dashboard for migration progress monitoring
- [ ] Enhanced import API for .pbix files > 1 GB
- [ ] Workspace app publishing with audience configuration
