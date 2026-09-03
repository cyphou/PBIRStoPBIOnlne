# 🔒 Permission Mapping Guide

This guide maps SSRS permissions to Power BI workspace roles and highlights security-model differences.

Reference index: [README.md](README.md)

## 🔄 SSRS Roles → PBI Online Workspace Roles

| SSRS Role | PBI Workspace Role | Notes |
|-----------|-------------------|-------|
| Browser | Viewer | Read-only access |
| Content Manager | Admin | Full workspace control |
| My Reports | Contributor | Create and edit content |
| Publisher | Contributor | Publish reports |
| Report Builder | Contributor | Create paginated reports |
| System Administrator | Admin | Mapped to workspace admin |
| System User | Viewer | Basic access |

---

## ⚠️ Key Differences

### SSRS Security Model
- **Item-level permissions** — each folder/report can have distinct role assignments
- **Inheritance** — permissions cascade from parent folders
- **Custom roles** — organizations can define custom SSRS roles
- **Windows groups** — uses Active Directory groups for assignment

### PBI Online Security Model
- **Workspace-level permissions** — all content in a workspace shares permissions
- **Row-Level Security (RLS)** — data filtering per user/role within datasets
- **App permissions** — published apps can have separate audiences
- **Azure AD groups** — uses Azure AD groups and service principals

---

## 📁 Folder-to-Workspace Access Mapping

PBIRS folder/report permissions cannot be reproduced as item-level permissions inside a single Power BI workspace. The supported automated pattern is to split PBIRS folders into separate target workspaces and apply the effective PBIRS access for each folder subtree to that workspace.

`--assess` and `--export` generate the planning CSVs for this flow:

| CSV | Purpose |
|-----|---------|
| `folders_mapping.csv` | Map each PBIRS folder path to a `target_workspace` |
| `users_mapping.csv` | Map each PBIRS principal to `target_azure_ad` |
| `folder_access_mapping.csv` | Shows the effective principals and roles per PBIRS folder; used to scope workspace permissions |

When `folder_access_mapping.csv` is present, `scripts/csv_to_pbi_online_import.py` applies permissions per target workspace instead of applying every mapped user to every workspace. It resolves the target workspace by longest matching `folder_path` from `folders_mapping.csv`, then uses `users_mapping.csv` for the Azure AD identity.

Example:

| PBIRS folder | target workspace | Effective access applied |
|--------------|------------------|--------------------------|
| `/Finance` | `Finance Reports` | Only Finance principals from `folder_access_mapping.csv` |
| `/HR` | `HR Reports` | Only HR principals from `folder_access_mapping.csv` |

---

## 🧠 Migration Considerations

1. **Granularity loss** — PBIRS item-level permissions flatten to workspace-level
2. **Multiple workspaces** — create separate workspaces for different permission groups
3. **RLS setup** — implement RLS if PBIRS used item permissions to restrict data access
4. **AD group alignment** — ensure on-prem AD groups are synced to Azure AD
5. **Custom roles** — custom SSRS roles have no automatic PBI equivalent — map manually

> [!TIP]
> The `security_extractor` module enumerates all AD groups, role compositions, and inheritance chains. Review `security_model.json` before migration.

---

## 💡 Recommendations

- Review `folder_access_mapping.csv` before importing so workspace permissions match the folder split
- Group reports by access pattern into separate PBI workspaces
- Use **PBI Apps** to publish curated views with specific audiences
- Implement **RLS** for data-level security previously handled by item permissions
- Use the `security_converter` module to generate RLS role definitions from SSRS patterns
