# ⚠️ Known Limitations

This guide tracks migration limitations, implementation status, and available mitigation paths.

Reference index: [README.md](README.md)

> **Last updated:** v1.8.0 — Semantic BPA model-intelligence + export role attachment propagation.

---

## Content Types

| Area | Limitation | Status |
|------|-----------|--------|
| **Mobile Reports** | Deprecated in PBIRS — no PBI Online equivalent | ✅ IMPROVED (v1.7) — `MobileReportExtractor` emits best-effort `*.scaffold.json` mapping known tile types (Gauge/Chart/Indicator/Map/Navigator/DataGrid/Image/Text) to PBI visuals (`--migrate-mobile`) |
| **KPIs** | No direct PBI equivalent | ✅ IMPROVED (v1.3) — `ScorecardGenerator` converts to Scorecard/Goals API payloads |
| **Linked Reports** | Treated as paginated reports | ✅ IMPROVED (v1.6) — `LinkedReportHandler` emits bookmark or paginated-override payloads (`--linked-as`) |

## Paginated Reports

| Area | Limitation | Status |
|------|-----------|--------|
| **Custom Code (VB.NET)** | Not supported in PBI Online | ✅ IMPROVED (v1.2) — `rdl_modifier` auto-strips with backup |
| **Custom Assemblies** | Not supported in PBI Online | ✅ IMPROVED (v1.2) — `rdl_modifier` auto-strips |
| **Custom Classes** | Not supported in PBI Online | ✅ IMPROVED (v1.2) — `rdl_modifier` auto-strips |
| **Subreport Dependencies** | Complex dependency chains | ✅ IMPROVED (v1.2) — `subreport_resolver` computes safe import order |
| **Circular Subreport Refs** | Circular dependencies can break one-pass paginated import order | ✅ IMPROVED (v1.8) — `SubreportResolver` now emits cycle groups + bootstrap order with automatic retry-pass mitigation used by `PaginatedPublisher` |

## Subscriptions

| Area | Limitation | Status |
|------|-----------|--------|
| **File-Share Delivery** | No file-share delivery in PBI Online | ✅ IMPROVED (v1.3) — Power Automate flow stubs auto-generated |
| **Data-Driven Subscriptions** | Requires direct DB access for query-based recipients | ✅ IMPROVED (v1.3) — conversion plans + CSV templates generated |
| **Data-Driven Query Extraction** | PBIRS REST API does not expose subscription queries | ✅ IMPROVED (v6.2) — optional ReportServer DB bridge enriches conversion plans (`--allow-db-query-bridge`) |

## Permissions

| Area | Limitation | Status |
|------|-----------|--------|
| **Item-Level Security** | PBI Online uses workspace-level permissions | ✅ IMPROVED (v1.6) — `AudienceBucketer` collapses ACL signatures into App audiences (`--ils-as-audiences`) |
| **Custom SSRS Roles** | No automatic mapping for custom roles | ✅ IMPROVED (v1.6) — `--role-map PATH` plus heuristic suggester |
| **Windows AD Groups** | Must be synced to Azure AD | ✅ IMPROVED (v1.7) — `ADGroupBridge` discovers AD principals, splits users/groups, emits a CSV manifest, and (with Graph client) provisions AAD groups (`--ad-bridge --ensure-aad-groups`) |

## Structure

| Area | Limitation | Status |
|------|-----------|--------|
| **Folders** | PBI Online workspaces are flat | ✅ IMPROVED (v1.6) — `WorkspaceFolderManager` recreates the tree via Fabric folders (`--preserve-folders`) |
| **Shared Datasources (.rds)** | Become gateway connections | ✅ IMPROVED (v1.7) — `GatewayAutoCreator` parses `.rds` (SQL/Oracle/ODBC/AS/PG/MySQL/Snowflake/OData/Web), creates missing gateway datasources via PBI REST, emits `gateway_mapping.auto.json` (`--gateway-auto --gateway-id`) |
| **Cache Refresh Plans** | No direct equivalent in PBI Online | ✅ IMPROVED (v1.6) — `CachePlanMigrator` emits `refreshSchedule` payloads (`--migrate-cache-plans`) |
| **Folder portal branding** | Logos / themes not migrated | ✅ IMPROVED (v1.6) — `BrandingMigrator` writes workspace branding + report theme (`--migrate-branding`) |

## API Limitations

| Area | Limitation | Status |
|------|-----------|--------|
| **PBI REST API Import Size** | .pbix files > 1 GB require enhanced import API | ✅ IMPROVED (v6.2) — chunked upload path implemented via temporary upload location (`LargeFileHandler` + `ReportPublisher` strategy routing) |
| **PBIRS PBIX upload acceptance** | Some PBIX files (especially `ConnectionType=pbiServiceLive`) open in Desktop RS but are rejected by PBIRS upload with HTTP 422 | ✅ IMPROVED (v1.8) — compatibility checks now auto-detect service-live risk and `ReportPublisher` skips incompatible PBIX files before upload with explicit diagnostics |
| **Concurrent Imports** | PBI Online has throttling limits | ✅ IMPROVED (v1.1) — parallel downloads respect rate limits |
| **Rate Limiting** | PBI REST API enforces rate limits | ✅ Handled — retry-after headers respected |
| **PBIRS API Coverage** | ~90% of metadata available via REST API | ✅ IMPROVED (v6.2) — optional DB bridges for data-driven queries and security inheritance (`--allow-db-query-bridge`, `--security-db-assist`) |

## Export

| Area | Limitation | Status |
|------|-----------|--------|
| **Large PBIRS Catalogs** | Exports can be slow for 1000+ items | ✅ IMPROVED (v1.1) — parallel downloads + checkpoint/resume |
| **Network Interruptions** | Exports can fail mid-download | ✅ IMPROVED (v1.1) — checkpoint manager enables resume |

## Semantic Model Intelligence

| Area | Limitation | Status |
|------|-----------|--------|
| **BPA scoring** | BPA quality depends on model artifact availability (`DataModelSchema`, `model_snapshot.json`, TMDL/XMLA JSON) | ✅ IMPROVED (v6.5) — semantic BPA now reads PBIX DataModelSchema and TMDL/XMLA-style snapshots, emits model-derived rule scoring and role-membership gaps; falls back to heuristic checks when no model artifact is available |
