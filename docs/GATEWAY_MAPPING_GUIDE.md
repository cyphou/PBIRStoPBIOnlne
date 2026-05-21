# 🔌 Gateway Mapping Guide

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

After running the export phase, generate a mapping template:

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
> The `mapping_generator` also outputs a `gateway_mapping.csv` with all detected datasources pre-filled.

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
