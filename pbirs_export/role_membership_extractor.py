"""Extract RLS/OLS role memberships with attached accounts.

Builds a normalized view of role assignments from exported PBIRS permission and
security artifacts and emits both JSON and CSV outputs.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


class RoleMembershipExtractor:
    """Extract role memberships across item and effective permission scopes."""

    def extract(
        self,
        permissions: dict[str, Any],
        security: dict[str, Any],
        model_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rows: list[dict[str, str]] = []

        # Item-level policies from permission extractor.
        for item in permissions.get("item_policies", []):
            if not isinstance(item, dict):
                continue
            item_name = str(item.get("item_name", ""))
            item_path = str(item.get("item_path", ""))
            item_type = str(item.get("item_type", ""))
            if item_type != "PowerBIReport":
                continue
            for policy in item.get("policies", []):
                if not isinstance(policy, dict):
                    continue
                principal = str(policy.get("GroupUserName", ""))
                if not principal:
                    continue
                principal_meta = self._principal_meta(principal)
                for role in policy.get("Roles", []):
                    role_name = self._role_name(role)
                    if not role_name or not self._is_rls_ols_role(role_name):
                        continue
                    rows.append(
                        {
                            "security_type": self._classify_security_type(role_name),
                            "role_name": role_name,
                            "account": principal,
                            "account_type": principal_meta["account_type"],
                            "domain": principal_meta["domain"],
                            "scope": "item_policy",
                            "item_path": item_path,
                            "item_name": item_name,
                            "item_type": item_type,
                            "source": "permissions.item_policies",
                        }
                    )

        # Effective permissions from security extractor for inherited visibility.
        for entry in security.get("effective_permissions", []):
            if not isinstance(entry, dict):
                continue
            role_name = str(entry.get("ssrs_role", ""))
            principal = str(entry.get("principal", ""))
            if str(entry.get("item_type", "")) != "PowerBIReport":
                continue
            if not role_name or not principal or not self._is_rls_ols_role(role_name):
                continue
            principal_meta = self._principal_meta(principal)
            rows.append(
                {
                    "security_type": self._classify_security_type(role_name),
                    "role_name": role_name,
                    "account": principal,
                    "account_type": principal_meta["account_type"],
                    "domain": principal_meta["domain"],
                    "scope": str(entry.get("source", "effective")).strip() or "effective",
                    "item_path": str(entry.get("item_path", "")),
                    "item_name": str(entry.get("item_name", "")),
                    "item_type": str(entry.get("item_type", "")),
                    "source": "security.effective_permissions",
                }
            )

        model_rows, roles_without_members = self._rows_from_model_snapshot(model_snapshot)
        rows.extend(model_rows)

        deduped = self._dedupe(rows)
        security_counts = {
            "RLS": sum(1 for r in deduped if r["security_type"] == "RLS"),
            "OLS": sum(1 for r in deduped if r["security_type"] == "OLS"),
        }

        return {
            "rows": deduped,
            "summary": {
                "total_assignments": len(deduped),
                "unique_roles": len({r["role_name"] for r in deduped}),
                "unique_accounts": len({r["account"] for r in deduped}),
                "by_security_type": security_counts,
                "model_roles_detected": len(
                    {
                        r.get("role_name", "")
                        for r in deduped
                        if str(r.get("source", "")).startswith("model_snapshot.roles")
                    }
                ),
                "model_roles_without_members": sorted(roles_without_members),
            },
        }

    def save_json(self, output_dir: str, payload: dict[str, Any]) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "rls_ols_role_accounts.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return path

    def save_csv(self, output_dir: str, payload: dict[str, Any]) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "rls_ols_role_accounts.csv"
        rows = payload.get("rows", []) if isinstance(payload, dict) else []
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "security_type",
                    "role_name",
                    "account",
                    "account_type",
                    "domain",
                    "scope",
                    "item_path",
                    "item_name",
                    "item_type",
                    "source",
                ]
            )
            for r in rows:
                if not isinstance(r, dict):
                    continue
                writer.writerow(
                    [
                        r.get("security_type", ""),
                        r.get("role_name", ""),
                        r.get("account", ""),
                        r.get("account_type", ""),
                        r.get("domain", ""),
                        r.get("scope", ""),
                        r.get("item_path", ""),
                        r.get("item_name", ""),
                        r.get("item_type", ""),
                        r.get("source", ""),
                    ]
                )
        return path

    @staticmethod
    def _role_name(role: Any) -> str:
        if isinstance(role, dict):
            return str(role.get("Name", "")).strip()
        return str(role).strip() if isinstance(role, str) else ""

    @staticmethod
    def _classify_security_type(role_name: str) -> str:
        token = role_name.lower()
        if "ols" in token or "object" in token or "column" in token:
            return "OLS"
        return "RLS"

    @staticmethod
    def _is_rls_ols_role(role_name: str) -> bool:
        token = role_name.casefold()
        return any(
            marker in token
            for marker in ("rls", "ols", "row-level", "row level", "object-level", "object level")
        )

    @staticmethod
    def _principal_meta(principal: str) -> dict[str, str]:
        if "\\" in principal:
            domain = principal.split("\\", 1)[0]
            return {"account_type": "ad_account", "domain": domain}
        if "@" in principal:
            return {"account_type": "email", "domain": ""}
        if principal.upper().startswith("BUILTIN\\"):
            return {"account_type": "builtin", "domain": "BUILTIN"}
        return {"account_type": "local", "domain": ""}

    @staticmethod
    def _dedupe(rows: list[dict[str, str]]) -> list[dict[str, str]]:
        seen: set[tuple[str, ...]] = set()
        out: list[dict[str, str]] = []
        for row in rows:
            key = (
                row.get("security_type", ""),
                row.get("role_name", ""),
                row.get("account", ""),
                row.get("scope", ""),
                row.get("item_path", ""),
                row.get("source", ""),
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
        return out

    def _rows_from_model_snapshot(
        self,
        model_snapshot: dict[str, Any] | None,
    ) -> tuple[list[dict[str, str]], set[str]]:
        if not isinstance(model_snapshot, dict):
            return [], set()
        if not model_snapshot.get("available"):
            return [], set()

        roles = model_snapshot.get("roles", [])
        if not isinstance(roles, list):
            return [], set()

        rows: list[dict[str, str]] = []
        roles_without_members: set[str] = set()
        for role in roles:
            if not isinstance(role, dict):
                continue
            role_name = str(role.get("name") or role.get("Name") or "").strip()
            if not role_name:
                continue

            members = self._extract_role_members(role)
            if not members:
                roles_without_members.add(role_name)
                rows.append(
                    {
                        "security_type": self._classify_security_type(role_name),
                        "role_name": role_name,
                        "account": "",
                        "account_type": "",
                        "domain": "",
                        "scope": "model_role",
                        "item_path": "[Model]",
                        "item_name": "[SemanticModel]",
                        "item_type": "SemanticModel",
                        "source": "model_snapshot.roles.missing_principals",
                    }
                )
                continue

            for principal in members:
                principal_meta = self._principal_meta(principal)
                rows.append(
                    {
                        "security_type": self._classify_security_type(role_name),
                        "role_name": role_name,
                        "account": principal,
                        "account_type": principal_meta["account_type"],
                        "domain": principal_meta["domain"],
                        "scope": "model_role",
                        "item_path": "[Model]",
                        "item_name": "[SemanticModel]",
                        "item_type": "SemanticModel",
                        "source": "model_snapshot.roles",
                    }
                )

        return rows, roles_without_members

    @staticmethod
    def _extract_role_members(role: dict[str, Any]) -> list[str]:
        candidates = (
            role.get("members"),
            role.get("principals"),
            role.get("modelPermissionMembers"),
            role.get("Members"),
            role.get("Principals"),
        )

        out: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if not isinstance(candidate, list):
                continue
            for item in candidate:
                val = ""
                if isinstance(item, str):
                    val = item.strip()
                elif isinstance(item, dict):
                    for key in ("name", "principal", "memberName", "id", "objectId", "user"):
                        v = item.get(key)
                        if isinstance(v, str) and v.strip():
                            val = v.strip()
                            break
                if not val or val in seen:
                    continue
                seen.add(val)
                out.append(val)
        return out
