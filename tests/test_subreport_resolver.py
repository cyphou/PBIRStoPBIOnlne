"""Tests for SubreportResolver."""

import pytest
from pbi_import.subreport_resolver import SubreportResolver


def _make_catalog(items: list[dict]) -> dict:
    return {"items": items}


class TestSubreportResolver:

    def test_simple_dependency(self):
        catalog = _make_catalog([
            {"Path": "/Reports/Main", "Type": "Report", "subreports": ["Detail"]},
            {"Path": "/Reports/Detail", "Type": "Report", "subreports": []},
        ])
        resolver = SubreportResolver(catalog)
        result = resolver.resolve()
        order = result["import_order"]
        assert order.index("/Reports/Detail") < order.index("/Reports/Main")

    def test_no_subreports(self):
        catalog = _make_catalog([
            {"Path": "/Reports/A", "Type": "Report", "subreports": []},
            {"Path": "/Reports/B", "Type": "Report", "subreports": []},
        ])
        resolver = SubreportResolver(catalog)
        result = resolver.resolve()
        # No dependencies → no items in import_order (only dependent items are sorted)
        assert result["circular"] == []
        assert result["orphan_refs"] == []

    def test_circular_dependency(self):
        catalog = _make_catalog([
            {"Path": "/Reports/A", "Type": "Report", "subreports": ["B"]},
            {"Path": "/Reports/B", "Type": "Report", "subreports": ["A"]},
        ])
        resolver = SubreportResolver(catalog)
        result = resolver.resolve()
        assert len(result["circular"]) > 0

    def test_multi_level_dependency(self):
        catalog = _make_catalog([
            {"Path": "/Reports/Top", "Type": "Report", "subreports": ["Mid"]},
            {"Path": "/Reports/Mid", "Type": "Report", "subreports": ["Bottom"]},
            {"Path": "/Reports/Bottom", "Type": "Report", "subreports": []},
        ])
        resolver = SubreportResolver(catalog)
        result = resolver.resolve()
        order = result["import_order"]
        assert order.index("/Reports/Bottom") < order.index("/Reports/Mid")
        assert order.index("/Reports/Mid") < order.index("/Reports/Top")

    def test_orphan_subreport_ref(self):
        catalog = _make_catalog([
            {"Path": "/Reports/Main", "Type": "Report", "subreports": ["Missing"]},
        ])
        resolver = SubreportResolver(catalog)
        result = resolver.resolve()
        assert len(result["orphan_refs"]) > 0

    def test_dependency_graph(self):
        catalog = _make_catalog([
            {"Path": "/Reports/A", "Type": "Report", "subreports": ["B", "C"]},
            {"Path": "/Reports/B", "Type": "Report", "subreports": []},
            {"Path": "/Reports/C", "Type": "Report", "subreports": ["B"]},
        ])
        resolver = SubreportResolver(catalog)
        result = resolver.resolve()
        graph = result["dependency_graph"]
        assert "/Reports/B" in graph.get("/Reports/A", [])
        assert "/Reports/C" in graph.get("/Reports/A", [])

    def test_non_report_items_ignored(self):
        catalog = _make_catalog([
            {"Path": "/Reports/A", "Type": "Report", "subreports": []},
            {"Path": "/DataSources/DS1", "Type": "DataSource"},
        ])
        resolver = SubreportResolver(catalog)
        result = resolver.resolve()
        # Only report items appear in order
        assert "/DataSources/DS1" not in result["import_order"]
