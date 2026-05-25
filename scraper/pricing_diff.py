#!/usr/bin/env python3
"""Compare two pricing catalogs for PR-worthy differences."""

from __future__ import annotations

import argparse
import sys

from catalog_io import catalogs_meaningfully_differ, load_catalog


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True, help="Path to pricing.json before scrape")
    parser.add_argument("--after", default=None, help="Path after (default: data/pricing.json)")
    args = parser.parse_args()

    before = load_catalog(args.before)
    after_path = args.after
    from catalog_io import DATA_PATH

    after = load_catalog(after_path or DATA_PATH)

    if catalogs_meaningfully_differ(before, after):
        print("Meaningful pricing changes detected.")
        return 0
    print("No meaningful pricing changes (metadata-only).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
