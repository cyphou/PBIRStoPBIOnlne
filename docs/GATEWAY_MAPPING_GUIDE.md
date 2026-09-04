# 🔌 Gateway Mapping Guide

This guide explains how to map and bind on-premises data sources through the Power BI gateway.

Reference index: [README.md](README.md)

## Overview

When migrating from PBIRS to PBI Online, reports that connect to **on-premises data sources**
need an **on-premises data gateway** to maintain connectivity.

> [!TIP]
> Cloud data sources (Azure SQL, Azure Analysis Services, etc.) do **not** need a gateway.

---

## 📋 Prerequisites

1. **Install On-Premises Data Gateway** — [Download](https://powerbi.microsoft.com/gateway/)
2. **Register Gateway in PBI Online** — Sign in during gateway setup
3. **Add Datasource to Gateway** — Configure connection credentials in PBI Online admin

---

## 📄 Gateway Mapping File

The tool uses a `gateway_mapping.json` file to bind reports to gateway datasources:

```json
{
  "Sales Dashboard": {
    "gateway_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "datasource_ids": ["yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"]
  },
  "Invoice Report": {
    "gateway_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "datasource_ids": ["zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz"]
  }
}
```

---

## ⚡ Auto-Generate Mapping Template

After running assessment or export, generate a mapping template:

```bash
# Generate from exported datasources
python scripts/generate_gateway_map.py \
  --datasources artifacts/export/datasources.json \
  --output gateway_mapping.json

# Or use the mapping_generator for CSV templates
python migrate.py --server URL --export  # includes mapping_generator output
```

Then fill in the `gateway_id` and `datasource_ids` fields manually.

> [!NOTE]
> The migration mapping generator outputs `connections_mapping.csv`. Its CSV writer quotes fields automatically, including connection strings containing commas. Fill the gateway and datasource **names**; the CSV import helper resolves the corresponding IDs from the Power BI APIs.

### CSV columns to fill

In `connections_mapping.csv`, review each row and fill:

| Column | What to enter |
|--------|---------------|
| `target_workspace` | Target workspace name for this report/connection |
| `target_gateway_name` | Exact gateway display name in Power BI Online |
| `target_datasource_name` | Exact datasource name under that gateway |
| `notes` | Optional operator notes |

`target_gateway_id` and `target_datasource_id` remain supported for legacy mappings, but names are preferred. The importer resolves names to IDs at runtime, avoiding stale IDs between tenants or environments.

Connection strings are written as valid CSV fields. Server and database are intentionally not duplicated into separate CSV columns; the importer uses the full connection string internally. For example, a value containing a comma is stored as:

```csv
"Data Source=sql01;Initial Catalog=Finance,Archive"
```

Do not manually split or remove the quotes. Open and save the file with a CSV-aware tool and preserve the header names.

---

## 🔍 Finding Gateway and Datasource IDs

1. Go to **PBI Online → Settings → Manage gateways**
2. Select your gateway cluster — the URL contains the gateway ID
3. Under the gateway, each datasource has its own ID

---

## 🔄 Connection Type Mapping

| PBIRS Connection Type | PBI Gateway Datasource Type |
|-----------------------|-----------------------------|
| SQL Server (on-prem) | Sql |
| Oracle | Oracle |
| ODBC | ODBC |
| OLE DB | OleDb |
| Analysis Services (on-prem) | AnalysisServices |
| SAP HANA | SapHana |
| File (CSV/Excel) | File (or migrate to cloud) |
| PostgreSQL | PostgreSql |
| MySQL | MySql |

---

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| "Gateway not reachable" | Ensure gateway service is running and has network access |
| "Invalid credentials" | Update credentials in PBI Online gateway datasource settings |
| "Datasource not found" | Verify datasource ID matches the gateway configuration |
| Report bound but refresh fails | Check firewall rules between gateway machine and data source |
