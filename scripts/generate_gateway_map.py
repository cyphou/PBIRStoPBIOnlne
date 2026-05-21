"""
Generate a gateway mapping template from exported datasources.

Usage:
    python scripts/generate_gateway_map.py \
        --datasources artifacts/export/datasources.json \
        --output gateway_mapping.json
"""

import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(description="Generate gateway mapping template")
    parser.add_argument("--datasources", required=True, help="Path to exported datasources JSON")
    parser.add_argument("--output", default="gateway_mapping.json", help="Output mapping file")
    args = parser.parse_args()

    with open(args.datasources, encoding="utf-8") as f:
        datasources = json.load(f)

    template = {}
    for ds in datasources.get("embedded_datasources", []):
        item_name = ds.get("item_name", "")
        if item_name and item_name not in template:
            template[item_name] = {
                "gateway_id": "<FILL IN>",
                "datasource_ids": ["<FILL IN>"],
                "_connection_info": ds.get("datasource", {}),
            }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(template, f, indent=2)

    print(f"Generated gateway mapping template with {len(template)} entries → {args.output}")
    print("Fill in gateway_id and datasource_ids for each entry before running import phase.")


if __name__ == "__main__":
    main()
