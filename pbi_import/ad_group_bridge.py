"""Windows AD → Azure AD group bridge.

Two outputs:
    1. A CSV manifest of all on-prem groups referenced in the export so an
       admin can run Azure AD Connect / manual sync against a known list.
    2. An optional Graph API helper that creates / verifies the equivalent
       Azure AD security groups (idempotent, dry-run by default).

This bridges the long-standing "Windows AD Groups" limitation noted in
``docs/KNOWN_LIMITATIONS.md``.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_DOMAIN_USER_RE = re.compile(r"^(?P<dom>[^\\/@]+)[\\/](?P<name>.+)$")


def _is_group(principal: str) -> bool:
    """Heuristic — group names typically lack the ``user`` look + have UPNs absent."""
    # Common SSRS exports represent groups with no @ and usually CamelCase or _Group suffix
    if "@" in principal:
        return False
    # bare username (no domain prefix) — assume user unless it ends in 'Group' / starts with 'GG_'
    if "\\" not in principal and "/" not in principal:
        return principal.endswith(("Group", "Users", "Admins")) or principal.startswith(("GG_", "DL_", "SG_"))
    return True


def _normalise(principal: str) -> dict[str, str]:
    m = _DOMAIN_USER_RE.match(principal)
    if m:
        return {"domain": m.group("dom"), "name": m.group("name"), "raw": principal}
    return {"domain": "", "name": principal, "raw": principal}


class ADGroupBridge:
    """Discover AD principals in an export and prepare AAD-side artefacts."""

    def __init__(self, graph_client: Any | None = None):
        """``graph_client`` may be any object with ``ensure_group(display_name, mail_nickname)``.

        When omitted the bridge runs in CSV-only mode.
        """
        self.graph_client = graph_client

    def discover(self, permissions: list[dict] | dict[str, list[dict]]) -> dict[str, Any]:
        """Walk a permissions payload and return unique users + groups."""
        principals: set[str] = set()
        if isinstance(permissions, dict):
            for plist in permissions.values():
                for p in plist:
                    self._collect(p, principals)
        else:
            for p in permissions:
                self._collect(p, principals)

        users: list[dict] = []
        groups: list[dict] = []
        for raw in sorted(principals):
            norm = _normalise(raw)
            (groups if _is_group(norm["name"]) else users).append(norm)
        return {
            "total_principals": len(principals),
            "users": users,
            "groups": groups,
        }

    def _collect(self, entry: Any, out: set[str]) -> None:
        if isinstance(entry, str):
            out.add(entry)
            return
        if not isinstance(entry, dict):
            return
        for key in ("principal", "Principal", "user", "User", "group", "Group", "name", "Name"):
            v = entry.get(key)
            if isinstance(v, str) and v:
                out.add(v)
        for nested in entry.get("permissions", []) or []:
            self._collect(nested, out)

    def write_csv(self, discovered: dict, path: str | Path) -> Path:
        """Emit a CSV that Azure AD Connect operators can audit / load."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["kind", "domain", "name", "raw", "suggested_aad_display_name"])
            for entry in discovered["groups"]:
                w.writerow([
                    "group",
                    entry["domain"],
                    entry["name"],
                    entry["raw"],
                    self._suggest_display_name(entry["name"]),
                ])
            for entry in discovered["users"]:
                w.writerow([
                    "user",
                    entry["domain"],
                    entry["name"],
                    entry["raw"],
                    "",
                ])
        logger.info(
            "AD bridge CSV written: %s (groups=%d, users=%d)",
            p, len(discovered["groups"]), len(discovered["users"]),
        )
        return p

    def ensure_aad_groups(
        self,
        discovered: dict,
        dry_run: bool = True,
    ) -> list[dict]:
        """Create missing Azure AD groups via the Graph helper."""
        results: list[dict] = []
        if not discovered.get("groups"):
            return results
        if not self.graph_client and not dry_run:
            raise RuntimeError("ADGroupBridge: graph_client required for live mode")

        for entry in discovered["groups"]:
            display = self._suggest_display_name(entry["name"])
            nickname = self._mail_nickname(entry["name"])
            if dry_run or not self.graph_client:
                results.append({
                    "raw": entry["raw"],
                    "aad_display_name": display,
                    "mail_nickname": nickname,
                    "status": "dry_run",
                })
                continue
            try:
                resp = self.graph_client.ensure_group(display, nickname)
                results.append({
                    "raw": entry["raw"],
                    "aad_display_name": display,
                    "aad_group_id": resp.get("id"),
                    "status": "ensured",
                })
            except Exception as e:  # noqa: BLE001
                logger.warning("Failed to ensure AAD group %s: %s", display, e)
                results.append({
                    "raw": entry["raw"],
                    "aad_display_name": display,
                    "status": "failed",
                    "error": str(e),
                })
        return results

    def write_report(self, discovered: dict, results: list[dict], path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {"discovered": discovered, "ensure_results": results}
        with p.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return p

    def _suggest_display_name(self, name: str) -> str:
        # Strip common AD prefixes and convert to a Title-Case display name
        for prefix in ("GG_", "DL_", "SG_", "PBI_", "BI_"):
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        return name.replace("_", " ").replace("-", " ").strip().title()

    def _mail_nickname(self, name: str) -> str:
        return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower() or "group"
