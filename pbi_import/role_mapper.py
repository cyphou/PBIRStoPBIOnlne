"""
Role Mapper — pluggable mapping from custom SSRS roles to PBI Online roles.

Extends the default ``permission_mapper.ROLE_MAP`` with user-provided overrides
loaded from a JSON file via ``--role-map PATH``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pbi_import.permission_mapper import ROLE_MAP as DEFAULT_ROLE_MAP

logger = logging.getLogger(__name__)

PBI_ROLES = {"Admin", "Member", "Contributor", "Viewer"}


class RoleMapper:
    """Resolve SSRS role names to PBI Online workspace roles, with overrides."""

    def __init__(self, overrides: dict[str, str] | None = None):
        self.mapping: dict[str, str] = dict(DEFAULT_ROLE_MAP)
        if overrides:
            invalid = {k: v for k, v in overrides.items() if v not in PBI_ROLES}
            if invalid:
                raise ValueError(
                    f"Invalid PBI roles in overrides: {invalid}. "
                    f"Allowed: {sorted(PBI_ROLES)}"
                )
            self.mapping.update(overrides)
            logger.info("Applied %d custom role overrides", len(overrides))

    @classmethod
    def from_file(cls, path: str | Path) -> "RoleMapper":
        """Load overrides from a JSON file ``{"ssrs_role": "pbi_role", ...}``."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Role map file {path} must contain a JSON object")
        logger.info("Loaded %d role overrides from %s", len(data), path)
        return cls({str(k): str(v) for k, v in data.items()})

    def resolve(self, ssrs_role: str) -> str | None:
        """Return the PBI Online role for *ssrs_role*, or None if unmapped."""
        return self.mapping.get(ssrs_role)

    def suggest(self, ssrs_role: str) -> str:
        """Heuristic suggestion based on the role name when no mapping exists."""
        lowered = ssrs_role.lower()
        if any(k in lowered for k in ("admin", "owner", "manager")):
            return "Admin"
        if any(k in lowered for k in ("publish", "author", "edit", "writer")):
            return "Contributor"
        if any(k in lowered for k in ("read", "view", "browser", "consumer")):
            return "Viewer"
        return "Viewer"

    def report_unmapped(self, ssrs_roles: list[str]) -> dict:
        """Build a report of unmapped roles with suggestions."""
        unmapped = [r for r in set(ssrs_roles) if r and self.resolve(r) is None]
        return {
            "unmapped_count": len(unmapped),
            "suggestions": [
                {"ssrs_role": r, "suggested_pbi_role": self.suggest(r)}
                for r in sorted(unmapped)
            ],
        }
