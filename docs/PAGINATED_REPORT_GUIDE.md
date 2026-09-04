# 📄 Paginated Report Guide

This guide explains paginated report compatibility, licensing requirements, and migration steps.

Reference index: [README.md](README.md)

## Overview

Paginated reports (.rdl) from PBIRS can be published in PBI Online without mandatory capacity in all cases.
In practice:
- Pro/PPU is used for publishing to shared workspaces.
- Capacity (Fabric F64+ or Premium P1+) is required when free users consume shared content.

> [!NOTE]
> The tool detects unsupported external assemblies and file-share delivery. Embedded VB.NET code is retained because Power BI Service supports embedded report code; validate the result in the target tenant.

---

## 📋 Requirements

- **Pro or PPU** for publishing to shared workspaces
- **Capacity (Fabric F64+ or Premium P1+)** for free-user consumption scenarios
- **On-premises data gateway** if the report connects to on-prem data sources
- RDL files must not use unsupported external assemblies, shared `.rds/.rsd` dependencies, linked reports, or custom fonts.

---

## ✅ Feature Support Matrix

| Feature | Supported | Notes |
|---------|-----------|-------|
| Tables / Matrices | ✅ | Full support |
| Charts | ✅ | Full support |
| Parameters | ✅ | Full support |
| Subreports | ✅ | Must be in same workspace — use `subreport_resolver` for import order |
| Shared Datasets (.rsd) | ❌ | Not supported as SSRS shared datasets; use a Power BI semantic model or embedded datasource |
| Shared Data Sources (.rds) | ❌ | Not supported as SSRS shared datasources; use an embedded or named Power BI connection |
| Export (PDF, Excel, Word) | ✅ | Full support |
| Email Subscriptions | ✅ | Supported in Power BI Service; recreate or validate the target subscription |
| Drillthrough | ✅ | Full support |
| Embedded Images (DB) | ✅ | Supported |
| Maps | ✅ | Bing Maps integration |
| Embedded Custom Code (VB.NET) | ✅ | Supported when embedded in the report; external DLL code is not supported |
| Custom Assemblies | ❌ | Auto-stripped by `rdl_modifier` (v1.2) |
| Custom Fonts | ❌ | Not supported in Power BI Service paginated reports |
| Linked Reports | ❌ | Recreate as independent paginated reports or use another strategy |
| Document Maps | ⚠️ | Do not render in the Power BI Service viewer; may render in exports |
| File-Share Delivery | ❌ | Power Automate flow stubs auto-generated (v1.3) |
| SSRS Data-Driven Subscriptions | ❌ | Use Power BI dynamic subscriptions instead |
| Report Parts / Resources / KPIs / Mobile Reports | ❌ | Not migratable as equivalent Power BI Service items |

---

## 🚀 Migration Steps

1. **Assess** — run assessment phase; check `paginated_features` and `rdl_analysis.json`
2. **Auto-strip** — `rdl_modifier` removes external assemblies and unsupported file-share delivery references (with backup); embedded VB.NET code is preserved
3. **Resolve subreports** — `subreport_resolver` computes safe import order
4. **Export** — download .rdl files from PBIRS
5. **Import** — publish to target workspace via PBI REST API
6. **Bind datasources** — configure gateway or PBI dataset connection
7. **Test** — verify rendering, parameters, export, and subscriptions

---

## 🔧 Converting Custom Code

Embedded VB.NET code is supported in Power BI Service paginated reports. External assembly DLL references are not supported and should be replaced with embedded code, SQL, Power Query, or an Azure Function. For replacement logic:

| Original | Replacement |
|----------|-------------|
| Custom VB functions | SQL stored procedures or RDL expressions |
| Custom assembly logic | SQL views or computed columns |
| Complex formatting | RDL expression-based formatting |
| File-share delivery | Power Automate SharePoint flow (auto-generated) |

---

## 🔗 Using PBI Datasets as Data Sources

PBI Online paginated reports can connect to **PBI datasets (semantic models)** instead of direct
database connections. This eliminates the gateway requirement:

1. Publish the PBI report (.pbix) with its dataset to the workspace
2. Update the paginated report's datasource to point to the PBI dataset
3. Single source of truth for both interactive and paginated reports

> [!TIP]
> This is the recommended approach for reports that share the same data model — no gateway needed.
