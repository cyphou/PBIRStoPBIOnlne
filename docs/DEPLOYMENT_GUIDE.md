# 🚀 Deployment Guide

This guide covers deploying migrated content to Power BI Online workspaces.

---

## 📋 Prerequisites

1. **Python 3.12+** installed
2. **PBIRS access** — network access to the PBIRS REST API v2.0
3. **Azure AD App Registration** with the following API permissions:
   - `Power BI Service` → `Tenant.ReadWrite.All` (application)
   - `Power BI Service` → `Dataset.ReadWrite.All` (application)
4. **Admin consent** granted for the above permissions
5. **On-premises data gateway** — if reports use on-prem data sources

---

## ⚙️ Step 1: Azure AD App Registration

1. Go to **Azure Portal → Azure Active Directory → App registrations → New registration**
2. Name: `pbirs-migration-app`
3. Redirect URI: `http://localhost` (for device code flow)
4. Under **API permissions**, add:
   - `Power BI Service` → `Tenant.ReadWrite.All` (application)
   - `Power BI Service` → `Dataset.ReadWrite.All` (application)
5. Grant admin consent
6. Create a client secret under **Certificates & secrets**
7. Note: `Tenant ID`, `Client ID`, `Client Secret`

---

## 🔐 Step 2: Configure Environment

Copy `.env.example` to `.env` and fill in:

```env
# PBIRS Source
PBIRS_SERVER_URL=https://pbirs.contoso.com/reports
PBIRS_AUTH_METHOD=basic
PBIRS_USERNAME=domain\user
PBIRS_PASSWORD=<password>

# Azure AD
AZURE_TENANT_ID=<tenant-id>
AZURE_CLIENT_ID=<client-id>
AZURE_CLIENT_SECRET=<client-secret>

# Target
PBI_WORKSPACE_NAME=Migrated Reports
```

---

## 📦 Step 3: Install

```bash
pip install -e ".[deploy]"
```

> [!NOTE]
> Core migration (assessment, export, conversion) requires **no `pip install`** — pure stdlib.
> Only the import/deploy phase needs `azure-identity`, `requests`, and `msal`.

---

## 🔍 Step 4: Run Assessment

```bash
python migrate.py --server https://pbirs.contoso.com/reports --assess --output-dir ./artifacts
```

Review `artifacts/assessment/assessment_report.html` — check GREEN/YELLOW/RED scores.

---

## 📦 Step 5: Export Content

```bash
python migrate.py --server https://pbirs.contoso.com/reports --export --output-dir ./artifacts --parallel 8
```

> [!TIP]
> Use `--parallel 8` for faster downloads. Exports are checkpoint-resumable — if interrupted, re-run the same command.

---

## 🗺️ Step 6: Configure Gateway Mapping

```bash
python scripts/generate_gateway_map.py --datasources artifacts/export/datasources.json --output gateway_mapping.json
```

Edit `gateway_mapping.json` to fill in `gateway_id` and `datasource_ids` for each report.

See [GATEWAY_MAPPING_GUIDE.md](GATEWAY_MAPPING_GUIDE.md) for details.

---

## 🚀 Step 7: Import to PBI Online

```bash
# Dry run first
python migrate.py --import --input-dir ./artifacts --workspace-id <ID> --dry-run

# Actual import
python migrate.py --import --input-dir ./artifacts --workspace-id <ID> --map-gateway gateway_mapping.json
```

---

## ✅ Step 8: Validate

```bash
python migrate.py --validate --workspace-id <ID> --output-dir ./artifacts
```

Review `artifacts/validation/migration_report.html`.

---

## 🔄 Authentication Methods

### Service Principal (Recommended for CI/CD)

Set `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET` in `.env`.

### Managed Identity (Azure-hosted runners)

Set `AZURE_USE_MANAGED_IDENTITY=true`. Uses `DefaultAzureCredential`.

### Device Code Flow (Interactive)

Omit client secret — the tool will prompt for interactive login.

---

## 🏭 CI/CD Pipeline

The project includes a CI pipeline in `.github/workflows/ci.yml`:

1. **Lint** — pyright type checking
2. **Test** — pytest on Python 3.12
3. **Validate** — artifact validation

### GitHub Secrets Required

| Secret | Description |
|--------|-------------|
| `AZURE_TENANT_ID` | Azure AD tenant GUID |
| `AZURE_CLIENT_ID` | App registration client ID |
| `AZURE_CLIENT_SECRET` | App registration client secret |
| `PBI_WORKSPACE_ID` | Target workspace GUID |
