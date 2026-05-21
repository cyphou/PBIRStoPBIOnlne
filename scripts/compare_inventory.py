"""
Compare PBIRS catalog inventory with PBI Online workspace content.

Usage:
    python scripts/compare_inventory.py \
        --catalog artifacts/export/catalog.json \
        --workspace-id <workspace-id> \
        --output artifacts/comparison.json
"""

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(description="Compare PBIRS inventory with PBI Online workspace")
    parser.add_argument("--catalog", required=True, help="Path to exported catalog JSON")
    parser.add_argument("--workspace-id", required=True, help="PBI Online workspace ID")
    parser.add_argument("--output", default="comparison.json", help="Output comparison file")
    args = parser.parse_args()

    with open(args.catalog, encoding="utf-8") as f:
        catalog = json.load(f)

    source_items = catalog.get("items", [])
    source_names = {i["Name"] for i in source_items if i.get("Type") in ("PowerBIReport", "Report")}

    print(f"Source: {len(source_names)} reports in PBIRS catalog")
    print(f"Target workspace: {args.workspace_id}")
    print(f"(Connect to PBI API to compare — placeholder script)")

    comparison = {
        "source_count": len(source_names),
        "source_names": sorted(source_names),
        "workspace_id": args.workspace_id,
        "status": "manual_review_required",
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2)

    print(f"Comparison written to {args.output}")


if __name__ == "__main__":
    main()
