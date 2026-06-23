"""
Audience Bucketer — bridges PBIRS item-level security to PBI Online App Audiences.

PBI Online workspaces enforce one ACL per workspace. To preserve the granularity
of PBIRS item-level security without exploding into many workspaces, this module
groups items by their effective ACL signature and emits one App Audience per
distinct group — to be consumed by ``AppPublisher``.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class AudienceBucketer:
    """Group items by ACL signature into App audience buckets."""

    def __init__(self, max_audiences: int = 10):
        """``max_audiences`` is the PBI Online soft limit per app (currently 10)."""
        self.max_audiences = max_audiences

    def bucket(self, item_policies: list[dict]) -> dict:
        """Group *item_policies* into audience buckets.

        Each entry is ``{"item_id": str, "item_name": str, "principals": [
        {"name": str, "role": str}, ...]}``.

        Returns ``{"audiences": [...], "items_per_audience": {...}, "overflow": int}``.
        """
        buckets: dict[str, dict] = {}
        for item in item_policies:
            principals = item.get("principals") or item.get("policies") or []
            sig = self._signature(principals)
            bucket = buckets.setdefault(sig, {
                "signature": sig,
                "principals": _normalise(principals),
                "items": [],
            })
            bucket["items"].append({
                "item_id": item.get("item_id") or item.get("ItemId"),
                "item_name": item.get("item_name") or item.get("Name"),
            })

        audiences = self._build_audiences(buckets)
        overflow = 0
        if len(audiences) > self.max_audiences:
            overflow = len(audiences) - self.max_audiences
            audiences = self._collapse_least_used(audiences, self.max_audiences)
            logger.warning(
                "Collapsed %d audience buckets into %d (overflow=%d)",
                len(buckets), len(audiences), overflow,
            )

        return {
            "audiences": audiences,
            "items_per_audience": {a["name"]: len(a["items"]) for a in audiences},
            "overflow": overflow,
            "total_items": sum(len(a["items"]) for a in audiences),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _signature(principals: list[Any]) -> str:
        norm = sorted(
            (
                (p.get("name") or p.get("GroupUserName") or "").lower(),
                "+".join(sorted(_roles_of(p))),
            )
            for p in principals
        )
        return hashlib.sha1(json.dumps(norm).encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _build_audiences(buckets: dict[str, dict]) -> list[dict]:
        audiences = []
        for i, (sig, bucket) in enumerate(
            sorted(buckets.items(), key=lambda kv: -len(kv[1]["items"]))
        ):
            audiences.append({
                "name": f"Audience-{i + 1:02d}",
                "signature": sig,
                "principals": bucket["principals"],
                "items": bucket["items"],
            })
        return audiences

    @staticmethod
    def _collapse_least_used(audiences: list[dict], limit: int) -> list[dict]:
        keep = audiences[: limit - 1]
        tail = audiences[limit - 1:]
        merged_principals: list[dict] = []
        merged_items: list[dict] = []
        seen: set[str] = set()
        for a in tail:
            for p in a["principals"]:
                key = (p.get("name") or "").lower()
                if key and key not in seen:
                    merged_principals.append(p)
                    seen.add(key)
            merged_items.extend(a["items"])
        keep.append({
            "name": f"Audience-{limit:02d}-Other",
            "signature": "merged",
            "principals": merged_principals,
            "items": merged_items,
        })
        return keep


def _roles_of(principal: Any) -> list[str]:
    if "role" in principal:
        return [principal["role"]]
    if "roles" in principal:
        return [str(r) for r in principal["roles"]]
    if "Roles" in principal:
        return [r.get("Name", "") if isinstance(r, dict) else str(r) for r in principal["Roles"]]
    return []


def _normalise(principals: list[Any]) -> list[dict]:
    out = []
    for p in principals:
        name = p.get("name") or p.get("GroupUserName") or ""
        roles = _roles_of(p)
        out.append({"name": name, "roles": roles})
    return out
