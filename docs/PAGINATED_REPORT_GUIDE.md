# 📄 Paginated Report Guide

## Overview

Paginated reports (.rdl) from PBIRS require **Power BI Premium** or **Premium Per User (PPU)** capacity
in PBI Online.

> [!NOTE]
> The tool's `rdl_analyser` and `rdl_modifier` modules automatically detect and strip unsupported features — no manual RDL editing required for most reports.

---

## 📋 Requirements

- **Premium or PPU capacity** assigned to the target workspace
- **On-premises data gateway** if the report connects to on-prem data sources
- RDL files must not use unsupported features (auto-stripped by `rdl_modifier`)

---

## ✅ Feature Support Matrix

| Feature | Supported | Notes |
|---------|-----------|-------|
| Tables / Matrices | ✅ | Full support |
| Charts | ✅ | Full support |
| Parameters | ✅ | Full support |
| Subreports | ✅ | Must be in same workspace — use `subreport_resolver` for import order |
| Shared Datasets | ✅ | Must use PBI dataset as source |
| Export (PDF, Excel, Word) | ✅ | Full support |
| Email Subscriptions | ✅ | Auto-migrated |
| Drillthrough | ✅ | Full support |
| Embedded Images (DB) | ✅ | Supported |
| Maps | ✅ | Bing Maps integration |
| Custom Code (VB) | ❌ | Auto-stripped by `rdl_modifier` (v1.2) |
| Custom Assemblies | ❌ | Auto-stripped by `rdl_modifier` (v1.2) |
| Custom Classes | ❌ | Auto-stripped by `rdl_modifier` (v1.2) |
| File-Share Delivery | ❌ | Power Automate flow stubs auto-generated (v1.3) |
| Data-Driven Subscriptions | ⚠️ | Conversion plans + CSV templates generated (v1.3) |

---

## 🚀 Migration Steps

1. **Assess** — run assessment phase; check `paginated_features` and `rdl_analysis.json`
2. **Auto-strip** — `rdl_modifier` removes custom code/assemblies/classes (with backup)
3. **Resolve subreports** — `subreport_resolver` computes safe import order
4. **Export** — download .rdl files from PBIRS
5. **Import** — publish to Premium workspace via PBI REST API
6. **Bind datasources** — configure gateway or PBI dataset connection
7. **Test** — verify rendering, parameters, export, and subscriptions

---

## 🔧 Converting Custom Code

If your RDL uses custom VB.NET code, the `rdl_modifier` auto-strips it. For replacement logic:

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
