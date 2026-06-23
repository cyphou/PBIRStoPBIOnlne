"""DAX auto-fix — rewrite common PBIRS-vs-PBI compatibility issues.

``DAXHealthChecker`` (existing) only *reports* issues. This module produces
a rewritten expression and a per-measure diff so the conversion phase can
ship an updated semantic model definition.

Rewrites are conservative — anything ambiguous is flagged but left alone.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class Rewrite:
    """One DAX rewrite rule."""

    name: str
    pattern: re.Pattern[str]
    replacement: Callable[[re.Match[str]], str] | str
    description: str


def _earlier_to_var(_m: re.Match[str]) -> str:
    # Heuristic: replace bare EARLIER(col) with a VAR placeholder so users
    # see the intent.  Full conversion needs context — leave a hint.
    return "/* TODO: replace with VAR (was EARLIER) */ {}".format(_m.group(0))


_RULES: list[Rewrite] = [
    Rewrite(
        name="contains_to_in",
        pattern=re.compile(r"CONTAINS\s*\(\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^)]+)\)", re.IGNORECASE),
        replacement=lambda m: f"{m.group(3).strip()} IN VALUES({m.group(2).strip()})",
        description="CONTAINS(table, col, value) → value IN VALUES(col)",
    ),
    Rewrite(
        name="distinctcount_alias",
        pattern=re.compile(r"\bCOUNTROWS\s*\(\s*DISTINCT\s*\(\s*([^)]+)\)\s*\)", re.IGNORECASE),
        replacement=lambda m: f"DISTINCTCOUNT({m.group(1).strip()})",
        description="COUNTROWS(DISTINCT(col)) → DISTINCTCOUNT(col)",
    ),
    Rewrite(
        name="iferror_to_divide",
        pattern=re.compile(
            r"IFERROR\s*\(\s*([^/,()]+)\s*/\s*([^,()]+)\s*,\s*([^)]+)\)",
            re.IGNORECASE,
        ),
        replacement=lambda m: f"DIVIDE({m.group(1).strip()}, {m.group(2).strip()}, {m.group(3).strip()})",
        description="IFERROR(a/b, alt) → DIVIDE(a, b, alt)",
    ),
    Rewrite(
        name="if_hasonevalue_to_selectedvalue",
        pattern=re.compile(
            r"IF\s*\(\s*HASONEVALUE\s*\(\s*([^)]+)\)\s*,\s*VALUES\s*\(\s*\1\s*\)\s*,\s*([^)]+)\)",
            re.IGNORECASE,
        ),
        replacement=lambda m: f"SELECTEDVALUE({m.group(1).strip()}, {m.group(2).strip()})",
        description="IF(HASONEVALUE(c),VALUES(c),x) → SELECTEDVALUE(c, x)",
    ),
    Rewrite(
        name="earlier_warning",
        pattern=re.compile(r"\bEARLIER\s*\(", re.IGNORECASE),
        replacement=_earlier_to_var,
        description="EARLIER → VAR (manual finish required)",
    ),
]


@dataclass
class FixResult:
    """Per-measure rewrite outcome."""

    name: str
    table: str
    original: str
    rewritten: str
    applied_rules: list[str] = field(default_factory=list)
    changed: bool = False


class DAXAutoFixer:
    """Apply safe rewrites to a list of measures."""

    def __init__(self, rules: list[Rewrite] | None = None):
        self.rules = rules or _RULES

    def fix_expression(self, expression: str) -> tuple[str, list[str]]:
        applied: list[str] = []
        rewritten = expression
        for rule in self.rules:
            new = rule.pattern.sub(rule.replacement, rewritten)
            if new != rewritten:
                applied.append(rule.name)
                rewritten = new
        return rewritten, applied

    def fix_measures(self, measures: list[dict]) -> list[FixResult]:
        results: list[FixResult] = []
        for m in measures:
            expr = m.get("expression") or m.get("Expression") or ""
            rewritten, applied = self.fix_expression(expr)
            results.append(FixResult(
                name=m.get("name") or m.get("Name") or "?",
                table=m.get("table") or m.get("Table") or "",
                original=expr,
                rewritten=rewritten,
                applied_rules=applied,
                changed=rewritten != expr,
            ))
        return results

    def summary(self, results: list[FixResult]) -> dict:
        by_rule: dict[str, int] = {}
        changed = 0
        for r in results:
            if r.changed:
                changed += 1
            for rule in r.applied_rules:
                by_rule[rule] = by_rule.get(rule, 0) + 1
        return {
            "total_measures": len(results),
            "changed": changed,
            "unchanged": len(results) - changed,
            "by_rule": by_rule,
        }
