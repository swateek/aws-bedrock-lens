#!/usr/bin/env python3
"""Sync Bedrock foundation model inventory into data/pricing.json."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from catalog_io import (
    DATA_PATH,
    REPO_ROOT,
    load_catalog,
    normalize_catalog,
    write_catalog,
)
from inventory import (
    SNAPSHOT_PATH_NAME,
    fetch_inventory_from_api,
    merge_inventory_into_catalog,
)

DEFAULT_REGIONS = ("us-east-1", "us-west-2", "eu-west-1")
SNAPSHOT_PATH = REPO_ROOT / "data" / SNAPSHOT_PATH_NAME


def load_snapshot(path: Path = SNAPSHOT_PATH) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Inventory snapshot not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("models", [])


def write_snapshot(models: list[dict], regions: list[str], path: Path = SNAPSHOT_PATH) -> None:
    payload = {
        "synced_at": date.today().isoformat(),
        "regions_scanned": regions,
        "models": models,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
        f.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Bedrock model inventory into pricing.json")
    parser.add_argument(
        "--from-api",
        action="store_true",
        help="Fetch inventory via ListFoundationModels (requires AWS credentials)",
    )
    parser.add_argument(
        "--write-snapshot",
        action="store_true",
        help="With --from-api, also update data/model-inventory.snapshot.json",
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=SNAPSHOT_PATH,
        help="Snapshot JSON path when not using --from-api",
    )
    parser.add_argument(
        "--regions",
        nargs="+",
        default=list(DEFAULT_REGIONS),
        help="Regions to scan with --from-api",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=DATA_PATH,
        help="Path to pricing.json",
    )
    args = parser.parse_args()

    try:
        if args.from_api:
            print(f"Fetching foundation models from API ({', '.join(args.regions)})...")
            inventory = fetch_inventory_from_api(args.regions)
            if args.write_snapshot:
                write_snapshot(inventory, args.regions)
                print(f"Wrote snapshot: {args.snapshot}")
        else:
            print(f"Loading inventory snapshot: {args.snapshot}")
            inventory = load_snapshot(args.snapshot)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    catalog = normalize_catalog(load_catalog(args.catalog))
    today = date.today().isoformat()
    added, updated, warnings = merge_inventory_into_catalog(catalog, inventory)

    catalog["meta"]["last_inventory_sync_at"] = today
    catalog["meta"]["models_known_to_aws"] = len(inventory)

    if warnings:
        for w in warnings[:20]:
            print(f"WARN: {w}")
        if len(warnings) > 20:
            print(f"WARN: ... and {len(warnings) - 20} more")

    write_catalog(catalog, args.catalog)
    print(
        f"Inventory sync: {len(inventory)} AWS models, "
        f"{added} added, {updated} metadata updates, "
        f"{len(catalog['models'])} total in catalog"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
