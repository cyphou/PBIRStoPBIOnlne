"""
UAT Report Generator — creates User Acceptance Testing reports.

Generates comprehensive UAT test plans and reports from migration results,
assessment data, and validation outputs.
"""

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class UATGenerator:
    """Generate UAT test plans and reports for migrated content."""

    def generate_test_plan(self, catalog: list[dict], assessment: dict | None = None) -> dict:
        """Generate a UAT test plan from the migration catalog.

        Args:
            catalog: migrated content items.
            assessment: optional assessment results for risk-based prioritisation.
        """
        test_cases: list[dict] = []

        for item in catalog:
            name = item.get("Name", "")
            item_type = item.get("Type", "")
            score = self._get_score(item, assessment)

            # Common test cases
            cases = [
                {
                    "test_id": f"TC-{len(test_cases) + 1:04d}",
                    "category": "accessibility",
                    "description": f"Verify {name} is accessible in PBI Online workspace",
                    "priority": "P1",
                    "status": "pending",
                },
                {
                    "test_id": f"TC-{len(test_cases) + 2:04d}",
                    "category": "data_accuracy",
                    "description": f"Verify data accuracy for {name}",
                    "priority": "P1",
                    "status": "pending",
                },
            ]

            # Type-specific tests
            if item_type == "PowerBIReport":
                cases.extend([
                    {
                        "test_id": f"TC-{len(test_cases) + 3:04d}",
                        "category": "interactivity",
                        "description": f"Test all slicers and filters in {name}",
                        "priority": "P2",
                        "status": "pending",
                    },
                    {
                        "test_id": f"TC-{len(test_cases) + 4:04d}",
                        "category": "visual_fidelity",
                        "description": f"Compare visual layout of {name} with source",
                        "priority": "P2",
                        "status": "pending",
                    },
                ])
            elif item_type == "Report":  # Paginated
                cases.extend([
                    {
                        "test_id": f"TC-{len(test_cases) + 3:04d}",
                        "category": "export",
                        "description": f"Test PDF/Excel export for {name}",
                        "priority": "P2",
                        "status": "pending",
                    },
                    {
                        "test_id": f"TC-{len(test_cases) + 4:04d}",
                        "category": "parameters",
                        "description": f"Test all report parameters in {name}",
                        "priority": "P2",
                        "status": "pending",
                    },
                ])

            # Security test
            cases.append({
                "test_id": f"TC-{len(test_cases) + len(cases) + 1:04d}",
                "category": "security",
                "description": f"Verify permissions for {name} match source",
                "priority": "P1",
                "status": "pending",
            })

            for case in cases:
                case["item_name"] = name
                case["item_type"] = item_type
                case["risk_score"] = score

            test_cases.extend(cases)

        plan = {
            "test_plan": {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "total_test_cases": len(test_cases),
                "total_items": len(catalog),
                "test_cases": test_cases,
            },
            "summary": {
                "by_priority": self._count_by(test_cases, "priority"),
                "by_category": self._count_by(test_cases, "category"),
                "by_status": self._count_by(test_cases, "status"),
            },
        }

        logger.info("Generated UAT plan: %d test cases for %d items", len(test_cases), len(catalog))
        return plan

    def generate_report(self, test_plan: dict, results: list[dict]) -> dict:
        """Generate a UAT report from test results.

        Args:
            test_plan: output from ``generate_test_plan()``.
            results: list of ``{"test_id": "TC-0001", "status": "pass|fail|skip", "notes": "..."}``.
        """
        results_map = {r["test_id"]: r for r in results}
        test_cases = test_plan.get("test_plan", {}).get("test_cases", [])

        updated: list[dict] = []
        for tc in test_cases:
            result = results_map.get(tc["test_id"], {})
            tc_copy = dict(tc)
            tc_copy["status"] = result.get("status", "pending")
            tc_copy["notes"] = result.get("notes", "")
            tc_copy["tester"] = result.get("tester", "")
            updated.append(tc_copy)

        passed = sum(1 for t in updated if t["status"] == "pass")
        failed = sum(1 for t in updated if t["status"] == "fail")

        report = {
            "uat_report": {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "test_cases": updated,
            },
            "summary": {
                "total": len(updated),
                "passed": passed,
                "failed": failed,
                "skipped": sum(1 for t in updated if t["status"] == "skip"),
                "pending": sum(1 for t in updated if t["status"] == "pending"),
                "pass_rate": round(passed / max(passed + failed, 1) * 100, 1),
                "verdict": "PASS" if failed == 0 and passed > 0 else "FAIL",
            },
        }

        logger.info(
            "UAT report: %d/%d passed (%.1f%%) — %s",
            passed, len(updated), report["summary"]["pass_rate"],
            report["summary"]["verdict"],
        )
        return report

    def save(self, output_dir: str, data: dict, name: str = "uat_report") -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{name}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return path

    @staticmethod
    def _get_score(item: dict, assessment: dict | None) -> int:
        if not assessment:
            return 50
        scores = assessment.get("scores", {})
        return scores.get(item.get("Name", ""), {}).get("overall", 50)

    @staticmethod
    def _count_by(items: list[dict], key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            v = item.get(key, "unknown")
            counts[v] = counts.get(v, 0) + 1
        return counts
