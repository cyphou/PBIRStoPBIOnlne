"""
Data Classifier — scans PBIRS content for sensitivity indicators.

Analyses datasource connection strings, report metadata, and folder paths
to tag content by sensitivity level before migration.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Patterns indicating sensitive data
_SENSITIVE_PATTERNS: list[tuple[str, str]] = [
    (r"\bSSN\b", "PII"),
    (r"\bsocial.?security", "PII"),
    (r"\bcredit.?card", "PCI"),
    (r"\bcard.?number", "PCI"),
    (r"\bsalary\b", "HR-Confidential"),
    (r"\bpayroll\b", "HR-Confidential"),
    (r"\bmedical\b", "PHI"),
    (r"\bhealth\b", "PHI"),
    (r"\bdiagnos", "PHI"),
    (r"\bpassword\b", "Credentials"),
    (r"\bsecret\b", "Credentials"),
    (r"\bapi.?key\b", "Credentials"),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), label) for p, label in _SENSITIVE_PATTERNS]


class DataClassifier:
    """Scan PBIRS catalog for data sensitivity indicators."""

    def scan(self, catalog: list[dict]) -> list[dict]:
        """Scan all items for sensitivity indicators.

        Returns a list of findings per item.
        """
        results: list[dict] = []

        for item in catalog:
            findings = self._scan_item(item)
            classification = self._classify(findings)
            results.append({
                "name": item.get("Name", ""),
                "path": item.get("Path", ""),
                "type": item.get("Type", ""),
                "findings": findings,
                "classification": classification,
                "risk_level": self._risk_level(findings),
            })

        high = sum(1 for r in results if r["risk_level"] == "high")
        medium = sum(1 for r in results if r["risk_level"] == "medium")
        logger.info(
            "Data classification: %d items scanned, %d high-risk, %d medium-risk",
            len(results), high, medium,
        )
        return results

    def summary(self, scan_results: list[dict]) -> dict:
        """Summarise classification results."""
        by_classification: dict[str, int] = {}
        by_risk: dict[str, int] = {}

        for r in scan_results:
            c = r["classification"]
            by_classification[c] = by_classification.get(c, 0) + 1
            rl = r["risk_level"]
            by_risk[rl] = by_risk.get(rl, 0) + 1

        return {
            "total_scanned": len(scan_results),
            "by_classification": by_classification,
            "by_risk_level": by_risk,
        }

    def _scan_item(self, item: dict) -> list[dict]:
        """Scan a single item's metadata for sensitive patterns."""
        findings: list[dict] = []
        text_fields = [
            item.get("Name", ""),
            item.get("Description", ""),
            item.get("Path", ""),
        ]

        # Scan datasource connection strings and names
        for ds in item.get("DataSources", []):
            text_fields.append(ds.get("ConnectionString", ""))
            text_fields.append(ds.get("Name", ""))

        # Scan parameters
        for param in item.get("Parameters", []):
            text_fields.append(param.get("Name", ""))
            text_fields.append(str(param.get("DefaultValues", "")))

        combined = " ".join(text_fields)
        for pattern, label in _COMPILED:
            if pattern.search(combined):
                findings.append({
                    "category": label,
                    "pattern": pattern.pattern,
                })

        return findings

    @staticmethod
    def _classify(findings: list[dict]) -> str:
        """Determine overall classification from findings."""
        categories = {f["category"] for f in findings}
        if categories & {"PII", "PCI", "PHI", "Credentials"}:
            return "Highly Confidential"
        if categories & {"HR-Confidential"}:
            return "Confidential"
        return "Internal"

    @staticmethod
    def _risk_level(findings: list[dict]) -> str:
        categories = {f["category"] for f in findings}
        if categories & {"PII", "PCI", "PHI", "Credentials"}:
            return "high"
        if findings:
            return "medium"
        return "low"
