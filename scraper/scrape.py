#!/usr/bin/env python3
"""Sync inventory, merge Price List + HTML scrape into data/pricing.json."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from catalog_io import (
    PARSER_VERSION,
    PRICING_URL,
    catalogs_meaningfully_differ,
    load_catalog,
    normalize_catalog,
    pricing_fingerprint,
    update_scrape_manifest,
    write_catalog,
)
from inventory import SNAPSHOT_PATH_NAME, merge_inventory_into_catalog
from parser import extract_rows
from price_list import merge_price_list_into_catalog

USER_AGENT = (
    "aws-bedrock-lens-scraper/2.0 (+https://github.com/swateek/aws-bedrock-lens)"
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = REPO_ROOT / "data" / SNAPSHOT_PATH_NAME


def load_snapshot(path: Path = SNAPSHOT_PATH) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("models", [])


def merge_scraped_prices(catalog: dict, scraped_rows: list[dict]) -> tuple[int, int, list[str]]:
    by_id = {m["model_id"]: m for m in catalog["models"]}
    updated = 0
    unchanged = 0
    warnings: list[str] = []

    for row in scraped_rows:
        model_id = row["model_id"]
        if model_id not in by_id:
            warnings.append(f"No catalog entry for scraped model: {row['name']}")
            continue

        model = by_id[model_id]
        pricing_type = model["pricing_type"]
        unit = row.get("unit", "token")

        if pricing_type == "image" and unit != "image":
            warnings.append(f"Skipped {row['name']}: table unit mismatch (expected image)")
            continue
        if pricing_type == "embedding" and unit == "image":
            warnings.append(f"Skipped {row['name']}: table unit mismatch (expected embedding)")
            continue
        if pricing_type == "token" and unit == "image":
            warnings.append(f"Skipped {row['name']}: table unit mismatch (expected token)")
            continue

        old_slice = dict(model.get("on_demand", {}))
        new_slice = {**old_slice, **row["pricing"]}
        model["pricing_source"] = "auto"

        if old_slice == new_slice:
            unchanged += 1
            continue

        model["on_demand"] = new_slice
        updated += 1

    return updated, unchanged, warnings


def run_html_scrape(catalog: dict) -> tuple[list[dict], list[str], list[str]]:
    warnings: list[str] = []
    print(f"Fetching {PRICING_URL} ...")
    try:
        response = httpx.get(
            PRICING_URL,
            follow_redirects=True,
            timeout=60,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        warnings.append(f"HTML scrape skipped: {exc}")
        return [], warnings, []

    soup = BeautifulSoup(response.text, "html.parser")
    scraped_rows, unmapped = extract_rows(soup, catalog)
    for name in unmapped:
        warnings.append(f"Unmapped pricing page row: {name}")
    if not scraped_rows:
        warnings.append("No pricing rows parsed from HTML (JS placeholders or layout change).")
    else:
        print(f"Parsed {len(scraped_rows)} model(s) with literal prices from page.")
    return scraped_rows, warnings, unmapped


def main() -> int:
    parser = argparse.ArgumentParser(description="Update Bedrock pricing catalog")
    parser.add_argument(
        "--skip-inventory",
        action="store_true",
        help="Do not merge model-inventory.snapshot.json",
    )
    parser.add_argument(
        "--skip-price-list",
        action="store_true",
        help="Do not merge AWS Price List API data",
    )
    parser.add_argument(
        "--skip-html",
        action="store_true",
        help="Do not scrape AWS marketing pricing page",
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=SNAPSHOT_PATH,
        help="Inventory snapshot path",
    )
    args = parser.parse_args()

    catalog = normalize_catalog(load_catalog())
    before_snapshot = json.loads(json.dumps(catalog))
    old_hash = pricing_fingerprint(catalog["models"])
    today = date.today().isoformat()
    warnings: list[str] = []

    if not args.skip_inventory:
        inventory = load_snapshot(args.snapshot)
        if inventory:
            added, _updated, inv_warnings = merge_inventory_into_catalog(catalog, inventory)
            catalog["meta"]["last_inventory_sync_at"] = today
            catalog["meta"]["models_known_to_aws"] = len(inventory)
            warnings.extend(inv_warnings)
            print(f"Inventory: {len(inventory)} AWS models, {added} new catalog entries")
        else:
            warnings.append(f"No inventory snapshot at {args.snapshot}; run sync-models first.")

    if not args.skip_price_list:
        try:
            pl_updated, pl_matched, pl_warnings = merge_price_list_into_catalog(catalog)
            catalog["meta"]["last_price_list_at"] = today
            warnings.extend(pl_warnings)
            print(f"Price list: {pl_matched} mapped, {pl_updated} rows updated")
        except httpx.HTTPError as exc:
            warnings.append(f"Price list merge skipped: {exc}")

    html_updated = 0
    if not args.skip_html:
        scraped_rows, html_warnings, _unmapped = run_html_scrape(catalog)
        warnings.extend(html_warnings)
        if scraped_rows:
            html_updated, _unchanged, merge_warnings = merge_scraped_prices(catalog, scraped_rows)
            warnings.extend(merge_warnings)
            catalog["meta"]["last_scraped_at"] = today

    new_hash = pricing_fingerprint(catalog["models"])
    catalog["meta"]["parser_version"] = PARSER_VERSION
    catalog["meta"]["source"] = PRICING_URL
    catalog["meta"]["schema_version"] = "2.1"

    if new_hash != old_hash:
        catalog["meta"]["pricing_updated_at"] = today
        print("Pricing values changed — updated pricing_updated_at.")
    else:
        print("No pricing value changes — pricing_updated_at unchanged.")

    update_scrape_manifest(catalog, warnings=warnings)
    write_catalog(catalog)

    stats = catalog["scrape"]
    meaningful = catalogs_meaningfully_differ(before_snapshot, catalog)
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with Path(github_output).open("a", encoding="utf-8") as fh:
            fh.write(f"pricing_changed={'true' if meaningful else 'false'}\n")

    print(
        f"Summary: HTML {html_updated} updated; "
        f"{stats['models_with_prices']}/{stats['models_in_catalog']} models have list prices "
        f"({stats['price_coverage_pct']}%); "
        f"inventory {stats['inventory_coverage_pct']}% of AWS ({stats['models_known_to_aws']} known)"
    )
    print(f"PR-worthy changes: {'yes' if meaningful else 'no (metadata/scrape only)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
