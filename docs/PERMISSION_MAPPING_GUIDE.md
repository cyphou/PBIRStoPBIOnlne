# 🔒 Permission Mapping Guide

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

- Review the permission mapping CSV (`mapping_generator` output) before importing
- Group reports by access pattern into separate PBI workspaces
- Use **PBI Apps** to publish curated views with specific audiences
- Implement **RLS** for data-level security previously handled by item permissions
- Use the `security_converter` module to generate RLS role definitions from SSRS patterns
