# ⚠️ Known Limitations

> **Last updated:** v1.7.0 — Hardening + Gap Closure. Most prior gaps now have explicit bridges.

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
| **Circular Subreport Refs** | Cannot resolve circular dependencies | ⚠️ Detected and reported — must refactor manually |

## Subscriptions

| Area | Limitation | Status |
|------|-----------|--------|
| **File-Share Delivery** | No file-share delivery in PBI Online | ✅ IMPROVED (v1.3) — Power Automate flow stubs auto-generated |
| **Data-Driven Subscriptions** | Requires direct DB access for query-based recipients | ✅ IMPROVED (v1.3) — conversion plans + CSV templates generated |
| **Data-Driven Query Extraction** | PBIRS REST API does not expose subscription queries | ❌ API limitation — query details require ReportServer database access |

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
| **PBI REST API Import Size** | .pbix files > 1 GB require enhanced import API | ⚠️ Not yet implemented |
| **Concurrent Imports** | PBI Online has throttling limits | ✅ IMPROVED (v1.1) — parallel downloads respect rate limits |
| **Rate Limiting** | PBI REST API enforces rate limits | ✅ Handled — retry-after headers respected |
| **PBIRS API Coverage** | ~90% of metadata available via REST API | ⚠️ Some security inheritance and data-driven sub queries require DB access |

## Export

| Area | Limitation | Status |
|------|-----------|--------|
| **Large PBIRS Catalogs** | Exports can be slow for 1000+ items | ✅ IMPROVED (v1.1) — parallel downloads + checkpoint/resume |
| **Network Interruptions** | Exports can fail mid-download | ✅ IMPROVED (v1.1) — checkpoint manager enables resume |
