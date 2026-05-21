"""
DAX Health Checker — analyses DAX measures for deprecated functions and anti-patterns.

Parses DAX expressions from dataset metadata and flags issues like deprecated
functions, non-optimal patterns, and potential performance problems.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Deprecated DAX functions and their replacements
_DEPRECATED: dict[str, str] = {
    "ADDCOLUMNS": "",  # Not deprecated, but often misused
    "LOOKUPVALUE": "Consider TREATAS or relationships for better performance",
    "CONTAINS": "Consider IN operator for scalar checks",
    "EARLIER": "Use variables (VAR) instead — clearer and faster",
    "EARLIEST": "Use variables (VAR) instead",
}

# Anti-patterns (regex, description, suggestion)
_ANTIPATTERNS: list[tuple[str, str, str]] = [
    (
        r"\bCALCULATE\s*\(\s*COUNTROWS",
        "CALCULATE(COUNTROWS(...)) — may be slow on large tables",
        "Consider COUNTX with filter context or pre-aggregated measures",
    ),
    (
        r"\bSUMX\s*\(\s*ALL\s*\(",
        "SUMX(ALL(...)) — iterates entire table ignoring filters",
        "Verify intent — this ignores all filter context",
    ),
    (
        r"\bIF\s*\(\s*HASONEVALUE",
        "IF(HASONEVALUE(...)) pattern",
        "Consider SELECTEDVALUE with alternate result parameter",
    ),
    (
        r"\bFILTER\s*\(\s*ALL\s*\(",
        "FILTER(ALL(...)) — expensive full-table scan",
        "Use KEEPFILTERS or specific column filters when possible",
    ),
    (
        r"FORMAT\s*\([^,]+,\s*\"",
        "FORMAT() in measures — disables storage engine optimisation",
        "Move FORMAT to visual layer or report-level formatting",
    ),
    (
        r"\bCALCULATETABLE\s*\(",
        "CALCULATETABLE — ensure context transition is intended",
        "Review if CALCULATE with scalar aggregation would suffice",
    ),
]


class DAXHealthChecker:
    """Analyse DAX measures for deprecated functions and anti-patterns."""

    def check(self, measures: list[dict]) -> list[dict]:
        """Check a list of DAX measures for issues.

        Each measure should have ``name`` and ``expression`` fields.
        """
        results: list[dict] = []

        for measure in measures:
            name = measure.get("name", "")
            expression = measure.get("expression", "")
            issues = self._analyse(expression)

            results.append({
                "measure_name": name,
                "table": measure.get("table", ""),
                "expression_length": len(expression),
                "issues": issues,
                "health": "healthy" if not issues else (
                    "warning" if len(issues) <= 2 else "critical"
                ),
            })

        total_issues = sum(len(r["issues"]) for r in results)
        critical = sum(1 for r in results if r["health"] == "critical")
        logger.info(
            "DAX health check: %d measures, %d issues, %d critical",
            len(results), total_issues, critical,
        )
        return results

    def summary(self, results: list[dict]) -> dict:
        by_health: dict[str, int] = {}
        issue_types: dict[str, int] = {}

        for r in results:
            h = r["health"]
            by_health[h] = by_health.get(h, 0) + 1
            for issue in r["issues"]:
                t = issue["type"]
                issue_types[t] = issue_types.get(t, 0) + 1

        return {
            "total_measures": len(results),
            "by_health": by_health,
            "issue_types": issue_types,
        }

    def _analyse(self, expression: str) -> list[dict]:
        """Analyse a single DAX expression."""
        issues: list[dict] = []

        # Check deprecated functions
        for func, suggestion in _DEPRECATED.items():
            if not suggestion:
                continue
            if re.search(rf"\b{func}\b", expression, re.IGNORECASE):
                issues.append({
                    "type": "deprecated",
                    "function": func,
                    "suggestion": suggestion,
                })

        # Check anti-patterns
        for pattern, description, suggestion in _ANTIPATTERNS:
            if re.search(pattern, expression, re.IGNORECASE):
                issues.append({
                    "type": "antipattern",
                    "description": description,
                    "suggestion": suggestion,
                })

        # Check expression complexity (deeply nested)
        nesting = self._max_nesting(expression)
        if nesting > 5:
            issues.append({
                "type": "complexity",
                "description": f"Deep nesting ({nesting} levels)",
                "suggestion": "Break into sub-measures or use variables (VAR/RETURN)",
            })

        return issues

    @staticmethod
    def _max_nesting(expression: str) -> int:
        """Count maximum parenthesis nesting depth."""
        depth = 0
        max_depth = 0
        for ch in expression:
            if ch == "(":
                depth += 1
                max_depth = max(max_depth, depth)
            elif ch == ")":
                depth = max(depth - 1, 0)
        return max_depth
