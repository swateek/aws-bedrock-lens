#!/usr/bin/env python3
"""Validate pricing.json and optionally regenerate pricing.embed.js."""

from __future__ import annotations

import argparse
import sys

from catalog_io import (
    DATA_PATH,
    embed_matches_catalog,
    load_catalog,
    normalize_catalog,
    validate_catalog,
    write_catalog,
)


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

    from pathlib import Path

    path = Path(args.path)
    data = normalize_catalog(load_catalog(path))

    try:
        validate_catalog(data)
    except Exception as exc:
        print(f"Schema validation failed: {exc}", file=sys.stderr)
        return 1

    print(f"OK: {path} matches schema v{data['meta']['schema_version']}")

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
