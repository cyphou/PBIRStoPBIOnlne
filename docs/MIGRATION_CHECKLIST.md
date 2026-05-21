# ✅ Migration Checklist

## 📋 Pre-Migration

- [ ] **Run assessment** — `python migrate.py --server URL --assess`
- [ ] **Review HTML report** — check GREEN/YELLOW/RED scores per item
- [ ] **Identify Premium/PPU needs** — paginated reports require Premium capacity
- [ ] **Analyze RDL features** — review `rdl_analysis.json` for custom code/assemblies
- [ ] **Set up data gateway** — install and configure on-premises data gateway
- [ ] **Register Azure AD app** — service principal with PBI API permissions
- [ ] **Create target workspace** — or let the tool create it during import
- [ ] **Prepare gateway mapping** — `python scripts/generate_gateway_map.py`
- [ ] **Review permission mapping** — check SSRS roles → PBI workspace role mapping
- [ ] **Review subreport dependencies** — check for circular references
- [ ] **Notify stakeholders** — inform report consumers of migration timeline

---

## 🚀 Migration Execution

### Wave 1 — Quick Wins (🟢 GREEN items)
- [ ] Export GREEN items from PBIRS
- [ ] Convert exported content (auto-strips unsupported RDL features)
- [ ] Import Power BI reports to workspace
- [ ] Bind datasets to gateway
- [ ] Configure refresh schedules
- [ ] Assign workspace permissions
- [ ] Validate published reports

### Wave 2 — Minor Adjustments (🟡 YELLOW items)
- [ ] Resolve gateway binding issues
- [ ] Assign Premium capacity for paginated reports
- [ ] Resolve subreport dependencies (use `subreport_resolver` import order)
- [ ] Map custom SSRS roles manually
- [ ] Import and validate

### Wave 3 — Rework Required (🔴 RED items)
- [ ] Strip custom VB.NET code from paginated reports (auto via `rdl_modifier`)
- [ ] Remove custom assemblies from paginated reports
- [ ] Replace file-share subscriptions with Power Automate flows (auto-generated stubs)
- [ ] Convert data-driven subscriptions (review conversion plans + CSV templates)
- [ ] Replace deprecated Mobile Reports with Power BI reports
- [ ] Convert KPIs to Scorecards/Goals (auto-generated payloads)

---

## ✅ Post-Migration

- [ ] **Run validation** — `python migrate.py --validate --workspace-id <ID>`
- [ ] **Review migration report** — check `migration_report.html` for PASS/WARN/FAIL
- [ ] **Test report rendering** — spot-check key reports in PBI Online
- [ ] **Verify data refresh** — ensure scheduled refreshes run successfully
- [ ] **Validate permissions** — confirm users have appropriate access
- [ ] **Test subscriptions** — verify email subscriptions deliver correctly
- [ ] **Deploy Power Automate flows** — import generated flow definitions
- [ ] **Update bookmarks/links** — redirect users from PBIRS URLs to PBI Online
- [ ] **Monitor** — watch for failed refreshes or access issues for 2 weeks
- [ ] **Decommission PBIRS** — retire on-prem server after validation period

---

## ↩️ Rollback Plan

- [ ] Keep PBIRS running during validation period (minimum 2 weeks)
- [ ] Use rollback engine to delete published content if needed
- [ ] Document all manual changes for rollback reference
- [ ] Maintain gateway mapping backup for re-import
