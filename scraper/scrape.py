#!/usr/bin/env python3
"""Sync inventory, merge Price List into data/pricing.json."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from bedrock_offer import merge_bedrock_offer_into_catalog, propagate_variant_prices
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
from golden_rates import validate_golden_canaries
from inventory import (
    SNAPSHOT_PATH_NAME,
    append_inventory_records,
    inventory_record_from_stub,
    merge_inventory_into_catalog,
    provision_catalog_entries,
    stub_catalog_entry_from_model_id,
)
from model_id_inference import infer_model_id, is_legacy_service_name
from parser import extract_rows, normalize_name
from price_list import (
    discover_models_from_price_list,
    fetch_price_list_index,
    merge_price_list_into_catalog,
)
from price_merge import qa_check_html_prices
from price_seeds import merge_price_seeds_into_catalog

USER_AGENT = "aws-bedrock-lens-scraper/3.0 (+https://github.com/swateek/aws-bedrock-lens)"

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = REPO_ROOT / "data" / SNAPSHOT_PATH_NAME


def load_snapshot(path: Path = SNAPSHOT_PATH) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("models", [])


def provision_from_html_unmapped(
    catalog: dict,
    unmapped_names: list[str],
) -> tuple[list[dict], list[str]]:
    """Create catalog stubs for HTML table rows that inference can resolve."""
    warnings: list[str] = []
    snapshot_records: list[dict] = []
    new_entries: list[dict] = []
    by_id = {m["model_id"]: m for m in catalog.get("models", [])}

    for raw_name in unmapped_names:
        name = normalize_name(raw_name)
        if is_legacy_service_name(name):
            continue
        model_id = infer_model_id(name, catalog)
        if not model_id:
            warnings.append(f"Unmapped pricing page row: {name}")
            continue
        if model_id in by_id:
            continue
        entry = stub_catalog_entry_from_model_id(model_id, display_name=name)
        new_entries.append(entry)
        snapshot_records.append(inventory_record_from_stub(entry))
        by_id[model_id] = entry
        warnings.append(f"Auto-provisioned catalog entry from HTML: {model_id}")

    if new_entries:
        provision_catalog_entries(catalog, new_entries)
    return snapshot_records, warnings


def run_html_qa(catalog: dict) -> tuple[int, list[str], list[dict]]:
    """Fetch marketing page for discovery stubs and QA only (no price writes)."""
    warnings: list[str] = []
    print(f"Fetching {PRICING_URL} for QA ...")
    try:
        response = httpx.get(
            PRICING_URL,
            follow_redirects=True,
            timeout=60,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        warnings.append(f"HTML QA skipped: {exc}")
        return 0, warnings, []

    soup = BeautifulSoup(response.text, "html.parser")
    scraped_rows, unmapped = extract_rows(soup, catalog)
    html_records, provision_warnings = provision_from_html_unmapped(catalog, unmapped)
    warnings.extend(provision_warnings)
    if html_records:
        scraped_rows, _unmapped = extract_rows(soup, catalog)

    if not scraped_rows:
        warnings.append("No pricing rows parsed from HTML (JS placeholders or layout change).")
    else:
        print(f"Parsed {len(scraped_rows)} model(s) with literal prices for QA.")
        mismatches = qa_check_html_prices(catalog, scraped_rows, warnings=warnings)
        if mismatches:
            print(f"HTML QA: {mismatches} price mismatch(es) vs catalog.")
        else:
            print("HTML QA: catalog matches parsed marketing literals.")

    return len(scraped_rows), warnings, html_records


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
        help="Do not merge AWS Price List data",
    )
    parser.add_argument(
        "--skip-html",
        action="store_true",
        help="Do not run HTML marketing page QA",
    )
    parser.add_argument(
        "--skip-golden",
        action="store_true",
        help="Do not validate golden canary rates",
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

    snapshot_records_to_append: list[dict] = []

    if not args.skip_price_list:
        try:
            pl_index = fetch_price_list_index()
            disc_added, disc_records, disc_warnings = discover_models_from_price_list(
                catalog, pl_index
            )
            warnings.extend(disc_warnings)
            snapshot_records_to_append.extend(disc_records)
            if disc_added:
                print(f"Price list discovery: {disc_added} new catalog entries")

            pl_updated, pl_matched, pl_warnings = merge_price_list_into_catalog(
                catalog, index=pl_index
            )
            catalog["meta"]["last_price_list_at"] = today
            warnings.extend(pl_warnings)
            print(f"Price list (FM): {pl_matched} mapped, {pl_updated} rows updated")
        except httpx.HTTPError as exc:
            warnings.append(f"Price list merge skipped: {exc}")

        try:
            bo_updated, bo_matched, bo_warnings = merge_bedrock_offer_into_catalog(catalog)
            catalog["meta"]["last_bedrock_offer_at"] = today
            warnings.extend(bo_warnings)
            print(f"Bedrock offer: {bo_matched} mapped, {bo_updated} gap-fills")
        except httpx.HTTPError as exc:
            warnings.append(f"Bedrock offer merge skipped: {exc}")

    variant_updated = propagate_variant_prices(catalog)
    if variant_updated:
        print(f"Variant propagation: {variant_updated} rows inherited base model prices")

    seed_updated = merge_price_seeds_into_catalog(catalog)
    if seed_updated:
        print(f"Price seeds: {seed_updated} rows filled from curated list prices")

    html_parsed = 0
    if not args.skip_html:
        html_parsed, html_warnings, html_records = run_html_qa(catalog)
        warnings.extend(html_warnings)
        snapshot_records_to_append.extend(html_records)
        if html_parsed:
            catalog["meta"]["last_scraped_at"] = today

    if not args.skip_golden:
        failures = validate_golden_canaries(catalog)
        if failures:
            for msg in failures:
                warnings.append(f"Golden canary failed: {msg}")
            print(f"Golden canaries: {len(failures)} failure(s)")
            for msg in failures[:10]:
                print(f"  - {msg}")
            return 1
        print("Golden canaries: pass")

    new_hash = pricing_fingerprint(catalog["models"])
    catalog["meta"]["parser_version"] = PARSER_VERSION
    catalog["meta"]["source"] = PRICING_URL
    catalog["meta"]["schema_version"] = "2.3"

    if new_hash != old_hash:
        catalog["meta"]["pricing_updated_at"] = today
        print("Pricing values changed — updated pricing_updated_at.")
    else:
        print("No pricing value changes — pricing_updated_at unchanged.")

    if snapshot_records_to_append and args.snapshot.exists():
        snap_added = append_inventory_records(args.snapshot, snapshot_records_to_append)
        if snap_added:
            inventory = load_snapshot(args.snapshot)
            catalog["meta"]["models_known_to_aws"] = len(inventory)
            print(f"Inventory snapshot: appended {snap_added} discovered model(s)")

    update_scrape_manifest(catalog, warnings=warnings)
    write_catalog(catalog)

    stats = catalog["scrape"]
    meaningful = catalogs_meaningfully_differ(before_snapshot, catalog)
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with Path(github_output).open("a", encoding="utf-8") as fh:
            fh.write(f"pricing_changed={'true' if meaningful else 'false'}\n")

    print(
        f"Summary: HTML QA {html_parsed} parsed; "
        f"{stats['models_with_prices']}/{stats['models_in_catalog']} models have list prices "
        f"({stats['price_coverage_pct']}%); "
        f"inventory {stats['inventory_coverage_pct']}% of AWS "
        f"({stats['models_known_to_aws']} known)"
    )
    print(f"Commit-worthy changes: {'yes' if meaningful else 'no (metadata/scrape only)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
