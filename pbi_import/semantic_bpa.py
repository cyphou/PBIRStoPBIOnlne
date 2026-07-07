"""Semantic model BPA and capacity merge checks."""

from __future__ import annotations

from typing import Any

from pbi_import.composite_model_planner import CompositeModelPlanner
from pbi_import.dax_health_checker import DAXHealthChecker
from pbi_import.model_snapshot import ModelSnapshotLoader


class SemanticModelBPA:
    """Compute a lightweight BPA score for semantic-model readiness."""

    def evaluate(
        self,
        catalog: dict[str, Any],
        converted_payload: dict[str, Any] | None,
        model_source: str | None = None,
    ) -> dict[str, Any]:
        payload = converted_payload or {}
        model_snapshot = ModelSnapshotLoader().load(model_source) if model_source else {
            "available": False,
            "message": "No model source provided",
            "measures": [],
            "columns": [],
            "relationships": [],
            "roles": [],
            "calculation_groups": [],
            "annotations": [],
        }

        if not payload and not model_snapshot.get("available"):
            return {
                "status": "PASS",
                "score": 100,
                "max_score": 100,
                "message": "Semantic BPA skipped (no datasource baseline or model snapshot found)",
                "rules": [
                    {
                        "id": "baseline_present",
                        "status": "INFO",
                        "weight": 0,
                        "message": "No datasource baseline or model snapshot available; BPA treated as neutral",
                    }
                ],
            }

        shared = payload.get("shared_datasources", []) if isinstance(payload, dict) else []
        embedded = payload.get("embedded_datasources", []) if isinstance(payload, dict) else []
        summary = payload.get("connection_summary", {}) if isinstance(payload, dict) else {}

        rules: list[dict[str, Any]] = []
        rules.append(self._rule("has_connection_summary", bool(summary), 20, "Connection summary metadata is present"))
        rules.append(self._rule("has_shared_datasources", len(shared) > 0, 20, "At least one shared datasource exists"))
        if len(embedded) > 0:
            rules.append(self._rule("has_embedded_references", True, 15, "Embedded datasource references were discovered"))
        else:
            rules.append({
                "id": "has_embedded_references",
                "status": "INFO",
                "weight": 15,
                "message": "No embedded datasource references found (shared-only model is acceptable)",
            })

        legacy_count = self._count_legacy_providers(shared, embedded)
        if legacy_count == 0:
            rules.append(self._rule("legacy_provider_usage", True, 25, "No legacy datasource providers detected"))
        elif legacy_count <= 2:
            rules.append({
                "id": "legacy_provider_usage",
                "status": "WARN",
                "weight": 25,
                "message": f"{legacy_count} legacy provider reference(s) detected; review compatibility",
            })
        else:
            rules.append({
                "id": "legacy_provider_usage",
                "status": "FAIL",
                "weight": 25,
                "message": f"{legacy_count} legacy provider references detected",
            })

        raw_items = catalog.get("items", []) if isinstance(catalog, dict) else []
        items = [i for i in raw_items if isinstance(i, dict)]
        report_like_items = [i for i in items if i.get("Type") in ("PowerBIReport", "Report")]
        rules.append(self._rule("catalog_has_reports", len(report_like_items) > 0, 20, "Catalog includes report artifacts"))

        if model_snapshot.get("available"):
            rules.append({
                "id": "model_snapshot_present",
                "status": "PASS",
                "weight": 10,
                "message": f"Model snapshot available from {model_snapshot.get('source', '')}",
            })
            rules.extend(self._build_model_rules(model_snapshot))

            dax_results = DAXHealthChecker().check(model_snapshot.get("measures", []))
            dax_summary = DAXHealthChecker().summary(dax_results)
            critical = dax_summary.get("by_health", {}).get("critical", 0)
            warning = dax_summary.get("by_health", {}).get("warning", 0)
            rules.append({
                "id": "dax_measure_health",
                "status": "PASS" if critical == 0 and warning == 0 else "WARN" if critical == 0 else "FAIL",
                "weight": 25,
                "message": f"{dax_summary.get('total_measures', 0)} measure(s) inspected; {critical} critical, {warning} warning",
                "measure_summary": dax_summary,
            })

        score = self._score(rules)
        if score >= 85:
            status = "PASS"
        elif score >= 70:
            status = "WARN"
        else:
            status = "FAIL"

        return {
            "status": status,
            "score": score,
            "max_score": 100,
            "message": f"Semantic BPA score: {score}/100",
            "rules": rules,
            "model_snapshot": model_snapshot,
            "evaluation_mode": "model_based" if model_snapshot.get("available") else "heuristic",
        }

    @staticmethod
    def _build_model_rules(model_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        tables = model_snapshot.get("tables", []) if isinstance(model_snapshot.get("tables", []), list) else []
        measures = model_snapshot.get("measures", []) if isinstance(model_snapshot.get("measures", []), list) else []
        columns = model_snapshot.get("columns", []) if isinstance(model_snapshot.get("columns", []), list) else []
        relationships = model_snapshot.get("relationships", []) if isinstance(model_snapshot.get("relationships", []), list) else []
        calc_groups = model_snapshot.get("calculation_groups", []) if isinstance(model_snapshot.get("calculation_groups", []), list) else []
        annotations = model_snapshot.get("annotations", []) if isinstance(model_snapshot.get("annotations", []), list) else []
        roles = model_snapshot.get("roles", []) if isinstance(model_snapshot.get("roles", []), list) else []

        rules: list[dict[str, Any]] = [
            {
                "id": "model_tables_present",
                "status": "PASS" if len(tables) > 0 else "FAIL",
                "weight": 15,
                "message": f"Model contains {len(tables)} table(s)",
            },
            {
                "id": "model_measures_present",
                "status": "PASS" if len(measures) > 0 else "WARN",
                "weight": 15,
                "message": f"Model exposes {len(measures)} measure(s)",
            },
            {
                "id": "model_columns_present",
                "status": "PASS" if len(columns) > 0 else "WARN",
                "weight": 10,
                "message": f"Model exposes {len(columns)} column(s)",
            },
            {
                "id": "model_relationships_present",
                "status": "PASS" if len(relationships) > 0 else "WARN",
                "weight": 12,
                "message": f"Model defines {len(relationships)} relationship(s)",
            },
            {
                "id": "model_calculation_groups",
                "status": "PASS" if len(calc_groups) > 0 else "INFO",
                "weight": 6,
                "message": f"Model has {len(calc_groups)} calculation group(s)",
            },
            {
                "id": "model_annotations",
                "status": "PASS" if len(annotations) > 0 else "INFO",
                "weight": 4,
                "message": f"Model has {len(annotations)} annotation(s)",
            },
        ]

        inactive = 0
        for rel in relationships:
            if not isinstance(rel, dict):
                continue
            if rel.get("isActive") is False or str(rel.get("state", "")).lower() == "inactive":
                inactive += 1
        if relationships:
            rules.append(
                {
                    "id": "relationship_activity",
                    "status": "PASS" if inactive == 0 else "WARN",
                    "weight": 8,
                    "message": f"{inactive}/{len(relationships)} relationship(s) inactive",
                }
            )

        role_details: list[dict[str, Any]] = []
        roles_without_members: list[str] = []
        for role in roles:
            if not isinstance(role, dict):
                continue
            role_name = str(role.get("name") or role.get("Name") or "<unnamed>")
            members = SemanticModelBPA._extract_role_members(role)
            role_details.append({"name": role_name, "member_count": len(members), "members": members})
            if len(members) == 0:
                roles_without_members.append(role_name)

        rules.append(
            {
                "id": "role_definitions_present",
                "status": "PASS" if len(roles) > 0 else "INFO",
                "weight": 8,
                "message": f"Model defines {len(roles)} role(s)",
                "role_count": len(roles),
            }
        )
        if len(roles) > 0:
            rules.append(
                {
                    "id": "role_membership_coverage",
                    "status": "PASS" if len(roles_without_members) == 0 else "WARN",
                    "weight": 12,
                    "message": (
                        "All model roles include principals"
                        if len(roles_without_members) == 0
                        else "Roles missing principals: " + ", ".join(roles_without_members[:8])
                    ),
                    "roles_without_members": roles_without_members,
                    "roles": role_details,
                }
            )

        return rules

    @staticmethod
    def _extract_role_members(role: dict[str, Any]) -> list[str]:
        candidates = (
            role.get("members"),
            role.get("principals"),
            role.get("modelPermissionMembers"),
            role.get("Members"),
            role.get("Principals"),
        )

        members: list[str] = []
        for candidate in candidates:
            if not isinstance(candidate, list):
                continue
            for item in candidate:
                if isinstance(item, str) and item.strip():
                    members.append(item.strip())
                    continue
                if isinstance(item, dict):
                    for key in ("name", "principal", "memberName", "id", "objectId", "user"):
                        val = item.get(key)
                        if isinstance(val, str) and val.strip():
                            members.append(val.strip())
                            break
        # Preserve order while de-duplicating.
        seen: set[str] = set()
        out: list[str] = []
        for m in members:
            if m in seen:
                continue
            seen.add(m)
            out.append(m)
        return out

    @staticmethod
    def evaluate_capacity_merge(catalog: dict[str, Any], capacity_id: str | None = None) -> dict[str, Any]:
        """Check whether semantic-model merge scenarios require explicit capacity."""
        raw_items = catalog.get("items", []) if isinstance(catalog, dict) else []
        items = [i for i in raw_items if isinstance(i, dict)]
        plan = CompositeModelPlanner().plan(items)
        candidates = plan.get("summary", {}).get("composite_candidates", 0)

        if candidates == 0:
            return {
                "status": "PASS",
                "message": "No composite/merge semantic model candidates detected",
                "composite_candidates": 0,
                "capacity_required": False,
            }

        if capacity_id:
            return {
                "status": "PASS",
                "message": f"Composite candidates detected ({candidates}) and capacity is configured",
                "composite_candidates": candidates,
                "capacity_required": True,
                "capacity_id": capacity_id,
            }

        return {
            "status": "WARN",
            "message": (
                f"Composite semantic model merge candidates detected ({candidates}) but no capacity_id provided. "
                "Assign Premium/Fabric capacity before merge rollout."
            ),
            "composite_candidates": candidates,
            "capacity_required": True,
        }

    @staticmethod
    def _rule(rule_id: str, ok: bool, weight: int, message: str) -> dict[str, Any]:
        return {
            "id": rule_id,
            "status": "PASS" if ok else "WARN",
            "weight": weight,
            "message": message if ok else f"{message} (check failed)",
        }

    @staticmethod
    def _score(rules: list[dict[str, Any]]) -> int:
        total = sum(int(r.get("weight", 0)) for r in rules) or 1
        earned = 0.0
        for r in rules:
            w = float(r.get("weight", 0))
            status = r.get("status")
            if status == "PASS":
                earned += w
            elif status == "WARN":
                earned += 0.5 * w
            elif status == "INFO":
                earned += w
        return int(round((earned / total) * 100))

    @staticmethod
    def _count_legacy_providers(shared: list[dict[str, Any]] | list[Any], embedded: list[dict[str, Any]] | list[Any]) -> int:
        legacy_tokens = ("oracle", "odbc", "oledb", "analysis services")

        def _provider_name(entry: Any) -> str:
            if isinstance(entry, dict):
                return str(entry.get("Extension") or entry.get("Provider") or entry.get("DataSourceType") or "").lower()
            if isinstance(entry, str):
                return entry.lower()
            return ""

        count = 0
        for s in shared:
            if any(t in _provider_name(s) for t in legacy_tokens):
                count += 1
        for e in embedded:
            if not isinstance(e, dict):
                if any(t in _provider_name(e) for t in legacy_tokens):
                    count += 1
                continue
            inner = e.get("datasource", {}) if isinstance(e.get("datasource", {}), dict) else {}
            if any(t in _provider_name(inner) for t in legacy_tokens):
                count += 1
        return count