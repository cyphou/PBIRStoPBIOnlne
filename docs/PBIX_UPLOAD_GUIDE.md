# Adding Power BI Reports (.pbix) to PBIRS Test Server

## Current Status

The PBIRS test server (`http://ms-len-moa/Reports`) currently has **only paginated (.rdl) reports**.
To test the full migration pipeline (including PowerBI reports), `.pbix` files must be added.

## Why Automated Upload Failed

PBIRS **rejects** `.pbix` files unless they were created with **Power BI Desktop optimized for Power BI Report Server** (PBIDesktopRS).
This is because:

- The `.pbix` DataModel (ABF binary) must match the Analysis Services version embedded in PBIRS
- Regular Power BI Desktop (Microsoft Store version) creates `.pbix` in a newer format
- Programmatically-created `.pbix` files also fail (HTTP 422)

All of the following approaches were tried and returned **422 Unprocessable Entity**:

1. REST API v2.0 — JSON with base64 Content
2. REST API v2.0 — Multipart upload
3. SOAP `CreateCatalogItem`
4. `ReportingServicesTools` PowerShell module (`Write-RsCatalogItem`)
5. .NET `WebClient` / `HttpClient`
6. Programmatic `.pbix` creation (multiple formats)
7. GitHub-sourced `.pbix` samples

## How to Fix — Manual Steps

### Step 1: Install Power BI Desktop for Report Server

1. Open the PBIRS portal: `http://ms-len-moa/Reports`
2. Click **Download** (top-right) → **Power BI Desktop**
3. If the download link is broken (known issue with Download Center page 106035), ask your PBIRS admin for the `PBIDesktopRS_x64.msi` installer

> **Note**: The installer is **not** bundled with the PBIRS server installer. It is a separate download.

### Step 2: Create Sample Reports

Using PBI Desktop RS, create 5 simple reports with embedded data:

| Report Name          | Target Folder              | Description                |
|----------------------|----------------------------|----------------------------|
| Analyse des Ventes   | /Équipe Commerciale        | Sales analysis dashboard   |
| Suivi Budgétaire     | /Département Finance       | Budget tracking report     |
| Tableau RH           | /RH - Ressources Humaines  | HR metrics dashboard       |
| Dashboard IT         | /IT Operations             | IT operations monitoring   |
| KPI Direction        | /Direction Générale        | Executive KPI dashboard    |

### Step 3: Upload to PBIRS

From PBI Desktop RS:
1. **File** → **Save As** → **Power BI Report Server**
2. Enter server URL: `http://ms-len-moa/ReportServer`
3. Navigate to the target folder and save

Or upload via the portal:
1. Go to `http://ms-len-moa/Reports`
2. Navigate to the target folder
3. Click **Upload** → select the `.pbix` file

### Step 4: Re-run Export

```bash
py migrate.py --server http://ms-len-moa/Reports --export --use-windows-auth --output-dir artifacts/export --verbose
```

The export will now capture both `.rdl` and `.pbix` reports.

## PBIRS Server Details

- **Server**: `http://ms-len-moa/Reports` (ReportServer: `http://ms-len-moa/ReportServer`)
- **Version**: 1.25.9558.32914
- **Edition**: PBIRS Evaluation
- **Authentication**: Windows/NTLM (EUROPE\pidoudet)
- **PBI Desktop RS version needed**: 2.150.1926.0 (January 2026)
