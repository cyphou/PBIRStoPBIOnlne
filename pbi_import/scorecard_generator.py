"""
Scorecard Generator — converts PBIRS KPI items to PBI Online Scorecard/Goals.

PBIRS KPI items have:
  - Name, Description
  - ValueExpression (measure expression)
  - GoalExpression (target expression)
  - StatusExpression (traffic-light logic)
  - TrendExpression (trend direction)

PBI Online Goals API (via Fabric REST) supports:
  - Scorecards (container)
  - Goals (individual metrics with current/target values)

This module maps PBIRS KPIs into Scorecard API payloads.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ScorecardGenerator:
    """Convert PBIRS KPI metadata to PBI Online Scorecard/Goals definitions."""

    def __init__(self, workspace_id: str = ""):
        self.workspace_id = workspace_id

    def generate(self, catalog: dict, scorecard_name: str = "Migrated KPIs") -> dict:
        """Generate a Scorecard definition with Goals from PBIRS KPI items.

        Args:
            catalog: PBIRS catalog containing KPI items.
            scorecard_name: Name for the PBI Online scorecard container.

        Returns:
            Dict with scorecard definition and goal definitions.
        """
        kpi_items = [
            item for item in catalog.get("items", [])
            if item.get("Type") == "Kpi"
        ]

        if not kpi_items:
            return {"scorecard": None, "goals": [], "summary": {"total_kpis": 0}}

        scorecard = self._build_scorecard(scorecard_name)
        goals = [self._build_goal(kpi, i) for i, kpi in enumerate(kpi_items)]

        return {
            "scorecard": scorecard,
            "goals": goals,
            "summary": {
                "total_kpis": len(kpi_items),
                "goals_generated": len(goals),
                "requires_manual": len([g for g in goals if g.get("requires_manual")]),
            },
        }

    def save(self, result: dict, output_dir: str) -> Path:
        """Save scorecard definition to JSON."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "scorecard_definition.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        logger.info("Scorecard definition saved to %s", path)
        return path

    # ------------------------------------------------------------------
    # Scorecard builder
    # ------------------------------------------------------------------

    def _build_scorecard(self, name: str) -> dict:
        """Build the PBI Online Scorecard container payload."""
        return {
            "name": name,
            "description": "Auto-generated from PBIRS KPI migration",
            "workspace_id": self.workspace_id,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "api_endpoint": f"https://api.powerbi.com/v1.0/myorg/groups/{self.workspace_id}/scorecards",
        }

    def _build_goal(self, kpi: dict, index: int) -> dict:
        """Build a Goal definition from a PBIRS KPI item."""
        name = kpi.get("Name", f"Goal {index + 1}")
        description = kpi.get("Description", "")

        # Extract KPI expressions
        value_expr = kpi.get("ValueExpression", "")
        goal_expr = kpi.get("GoalExpression", "")
        status_expr = kpi.get("StatusExpression", "")
        trend_expr = kpi.get("TrendExpression", "")

        # Determine if manual configuration is needed
        requires_manual = bool(value_expr or goal_expr)

        goal: dict[str, Any] = {
            "name": name,
            "description": description,
            "source_path": kpi.get("Path", ""),
            "source_id": kpi.get("Id", ""),
            "current_value": {
                "type": "manual",
                "note": "(TO FILL — connect to semantic model measure)",
            },
            "target_value": {
                "type": "manual",
                "note": "(TO FILL — set target value or connect to measure)",
            },
            "status_rules": self._map_status(status_expr),
            "requires_manual": requires_manual,
            "migration_notes": self._generate_notes(kpi),
            "original_expressions": {
                "value": value_expr,
                "goal": goal_expr,
                "status": status_expr,
                "trend": trend_expr,
            },
        }

        return goal

    @staticmethod
    def _map_status(status_expr: str) -> dict:
        """Map SSRS status expression to PBI Goals status rules."""
        if not status_expr:
            return {
                "type": "manual",
                "note": "No status expression found — configure manually",
            }
        return {
            "type": "rules",
            "note": "Review original status expression and recreate as Goals status rules",
            "original_expression": status_expr[:300],
            "suggested_rules": [
                {"condition": "current >= target", "status": "on_track", "color": "green"},
                {"condition": "current >= target * 0.8", "status": "at_risk", "color": "yellow"},
                {"condition": "current < target * 0.8", "status": "behind", "color": "red"},
            ],
        }

    @staticmethod
    def _generate_notes(kpi: dict) -> list[str]:
        """Generate migration guidance for a KPI → Goal conversion."""
        notes: list[str] = [
            "KPI items require manual configuration in PBI Online Scorecards",
            "Create a Goal in the Scorecard and connect it to a semantic model measure",
        ]

        if kpi.get("ValueExpression"):
            notes.append("Original value expression needs to be mapped to a DAX measure")
        if kpi.get("GoalExpression"):
            notes.append("Original goal/target expression needs manual target value")
        if kpi.get("TrendExpression"):
            notes.append("Trend tracking is automatic in PBI Goals — verify after setup")

        datasources = kpi.get("datasources", [])
        if datasources:
            notes.append(f"Connected to {len(datasources)} datasource(s) — ensure semantic model is published first")

        return notes
