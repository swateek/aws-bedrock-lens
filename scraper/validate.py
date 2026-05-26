#!/usr/bin/env python3
"""Validate pricing.json and optionally regenerate pricing.embed.js."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from catalog_io import (
    DATA_PATH,
    embed_matches_catalog,
    load_catalog,
    normalize_catalog,
    validate_catalog,
    write_catalog,
)

INVENTORY_STALE_DAYS = 90


def _check_duplicate_model_ids(models: list[dict]) -> list[str]:
    seen: set[str] = set()
    errors: list[str] = []
    for model in models:
        mid = model.get("model_id", "")
        if mid in seen:
            errors.append(f"Duplicate model_id: {mid}")
        seen.add(mid)
    return errors


def _warn_stale_inventory(meta: dict) -> str | None:
    synced = meta.get("last_inventory_sync_at")
    if not synced:
        return "meta.last_inventory_sync_at is missing; run make sync-models"
    try:
        synced_date = date.fromisoformat(synced)
    except ValueError:
        return f"Invalid last_inventory_sync_at: {synced}"
    age = (date.today() - synced_date).days
    if age > INVENTORY_STALE_DAYS:
        return (
            f"Inventory sync is {age} days old (>{INVENTORY_STALE_DAYS}); "
            "update data/model-inventory.snapshot.json and run make sync-models"
        )
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate AWS Bedrock Lens pricing data")
    parser.add_argument(
        "path",
        nargs="?",
        default=str(DATA_PATH),
        help="Path to pricing.json (default: data/pricing.json)",
    )
    parser.add_argument(
        "--sync-embed",
        action="store_true",
        help="Regenerate pricing.embed.js from pricing.json",
    )
    parser.add_argument(
        "--check-embed",
        action="store_true",
        help="Fail if pricing.embed.js is out of sync",
    )
    args = parser.parse_args()

    path = Path(args.path)
    data = normalize_catalog(load_catalog(path))

    try:
        validate_catalog(data)
    except Exception as exc:
        print(f"Schema validation failed: {exc}", file=sys.stderr)
        return 1

    dup_errors = _check_duplicate_model_ids(data.get("models", []))
    if dup_errors:
        for err in dup_errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    stale = _warn_stale_inventory(data.get("meta", {}))
    if stale:
        print(f"WARN: {stale}", file=sys.stderr)

    print(f"OK: {path} matches schema v{data['meta']['schema_version']}")
    print(
        f"    {data['scrape']['models_with_prices']}/{data['scrape']['models_in_catalog']} "
        f"models with list prices"
    )

    if args.sync_embed:
        write_catalog(data, path)
        print("Regenerated pricing.embed.js")

    if args.check_embed:
        if not embed_matches_catalog(path):
            print("ERROR: pricing.embed.js is out of sync with pricing.json", file=sys.stderr)
            return 1
        print("OK: pricing.embed.js in sync")

    return 0


if __name__ == "__main__":
    sys.exit(main())
