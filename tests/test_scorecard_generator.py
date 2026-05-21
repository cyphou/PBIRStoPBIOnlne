"""Tests for ScorecardGenerator."""

import json
import pytest
from pbi_import.scorecard_generator import ScorecardGenerator


def _kpi_catalog(kpis: list[dict] | None = None) -> dict:
    if kpis is None:
        kpis = [
            {
                "Path": "/KPIs/Revenue",
                "Name": "Revenue",
                "Type": "Kpi",
                "Id": "kpi-1",
                "Description": "Monthly revenue",
                "ValueExpression": "=Sum(Fields!Revenue.Value)",
                "GoalExpression": "=1000000",
                "StatusExpression": "=IIF(Fields!Revenue.Value>=1000000,1,-1)",
                "TrendExpression": "=IIF(Fields!Revenue.Value>Previous,1,-1)",
                "datasources": [{"name": "SalesDB"}],
            },
            {
                "Path": "/KPIs/NPS",
                "Name": "NPS Score",
                "Type": "Kpi",
                "Id": "kpi-2",
                "Description": "Net Promoter Score",
                "ValueExpression": "",
                "GoalExpression": "",
                "StatusExpression": "",
                "TrendExpression": "",
            },
        ]
    return {"items": kpis}


class TestScorecardGenerator:

    def test_generates_scorecard(self):
        gen = ScorecardGenerator(workspace_id="ws-1")
        result = gen.generate(_kpi_catalog())
        assert result["scorecard"] is not None
        assert result["scorecard"]["name"] == "Migrated KPIs"

    def test_generates_goals(self):
        gen = ScorecardGenerator()
        result = gen.generate(_kpi_catalog())
        assert len(result["goals"]) == 2
        names = {g["name"] for g in result["goals"]}
        assert names == {"Revenue", "NPS Score"}

    def test_goal_has_original_expressions(self):
        gen = ScorecardGenerator()
        result = gen.generate(_kpi_catalog())
        revenue = [g for g in result["goals"] if g["name"] == "Revenue"][0]
        assert "Sum(Fields!Revenue.Value)" in revenue["original_expressions"]["value"]
        assert revenue["original_expressions"]["goal"] == "=1000000"

    def test_status_rules_mapped(self):
        gen = ScorecardGenerator()
        result = gen.generate(_kpi_catalog())
        revenue = [g for g in result["goals"] if g["name"] == "Revenue"][0]
        assert revenue["status_rules"]["type"] == "rules"
        assert len(revenue["status_rules"]["suggested_rules"]) == 3

    def test_empty_status_expression(self):
        gen = ScorecardGenerator()
        result = gen.generate(_kpi_catalog())
        nps = [g for g in result["goals"] if g["name"] == "NPS Score"][0]
        assert nps["status_rules"]["type"] == "manual"

    def test_requires_manual_flag(self):
        gen = ScorecardGenerator()
        result = gen.generate(_kpi_catalog())
        revenue = [g for g in result["goals"] if g["name"] == "Revenue"][0]
        nps = [g for g in result["goals"] if g["name"] == "NPS Score"][0]
        assert revenue["requires_manual"] is True  # has expressions
        assert nps["requires_manual"] is False  # no expressions

    def test_migration_notes(self):
        gen = ScorecardGenerator()
        result = gen.generate(_kpi_catalog())
        revenue = [g for g in result["goals"] if g["name"] == "Revenue"][0]
        assert any("DAX measure" in n for n in revenue["migration_notes"])

    def test_no_kpis(self):
        gen = ScorecardGenerator()
        result = gen.generate({"items": []})
        assert result["scorecard"] is None
        assert result["goals"] == []
        assert result["summary"]["total_kpis"] == 0

    def test_non_kpi_items_ignored(self):
        catalog = {"items": [
            {"Path": "/Reports/A", "Type": "Report", "Name": "A"},
            {"Path": "/KPIs/Rev", "Type": "Kpi", "Name": "Rev", "Id": "k1"},
        ]}
        gen = ScorecardGenerator()
        result = gen.generate(catalog)
        assert len(result["goals"]) == 1

    def test_save(self, tmp_path):
        gen = ScorecardGenerator()
        result = gen.generate(_kpi_catalog())
        path = gen.save(result, str(tmp_path))
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "scorecard" in data
        assert len(data["goals"]) == 2

    def test_custom_scorecard_name(self):
        gen = ScorecardGenerator()
        result = gen.generate(_kpi_catalog(), scorecard_name="Q4 Metrics")
        assert result["scorecard"]["name"] == "Q4 Metrics"

    def test_summary_counts(self):
        gen = ScorecardGenerator()
        result = gen.generate(_kpi_catalog())
        assert result["summary"]["total_kpis"] == 2
        assert result["summary"]["goals_generated"] == 2
