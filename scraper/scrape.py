#!/usr/bin/env python3
"""Scrape AWS Bedrock pricing and merge into data/pricing.json."""

from __future__ import annotations

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
    write_catalog,
)
from parser import extract_rows

USER_AGENT = "aws-bedrock-lens-scraper/2.0 (+https://github.com/swateek/aws-bedrock-lens)"


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


def main() -> int:
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
        print(f"ERROR: Failed to fetch pricing page: {exc}", file=sys.stderr)
        return 1

    soup = BeautifulSoup(response.text, "html.parser")
    scraped_rows = extract_rows(soup)

    if not scraped_rows:
        print(
            "ERROR: No pricing rows parsed — page structure may have changed.",
            file=sys.stderr,
        )
        return 1

    print(f"Parsed {len(scraped_rows)} model(s) with literal prices from page.")

    catalog = normalize_catalog(load_catalog())
    before_snapshot = json.loads(json.dumps(catalog))
    old_hash = pricing_fingerprint(catalog["models"])
    today = date.today().isoformat()

    updated, unchanged, warnings = merge_scraped_prices(catalog, scraped_rows)
    new_hash = pricing_fingerprint(catalog["models"])

    catalog["meta"]["last_scraped_at"] = today
    catalog["meta"]["parser_version"] = PARSER_VERSION
    catalog["meta"]["source"] = PRICING_URL

    if new_hash != old_hash:
        catalog["meta"]["pricing_updated_at"] = today
        print("Pricing values changed — updated pricing_updated_at.")
    else:
        print("No pricing value changes — pricing_updated_at unchanged.")

    by_id = {m["model_id"]: m for m in catalog["models"]}
    matched_ids = {r["model_id"] for r in scraped_rows if r["model_id"] in by_id}
    auto_count = sum(1 for m in catalog["models"] if m.get("pricing_source") == "auto")
    total = len(catalog["models"])
    if len(matched_ids) < len(scraped_rows):
        warnings.append(
            f"Parsed {len(scraped_rows)} rows; {len(matched_ids)} matched catalog entries."
        )

    catalog["scrape"] = {
        "models_matched": auto_count,
        "models_in_catalog": total,
        "coverage_pct": round(100 * auto_count / total) if total else 0,
        "warnings": warnings,
    }

    if catalog["scrape"]["coverage_pct"] < 50:
        warnings.append(
            "Low automated coverage: most AWS prices use JS placeholders; "
            "curate data/pricing.json manually or add a Price List API source."
        )
        catalog["scrape"]["warnings"] = warnings

    write_catalog(catalog)

    meaningful = catalogs_meaningfully_differ(before_snapshot, catalog)
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with Path(github_output).open("a", encoding="utf-8") as fh:
            fh.write(f"pricing_changed={'true' if meaningful else 'false'}\n")

    print(
        f"Summary: {updated} price rows updated, {unchanged} unchanged, "
        f"{auto_count}/{catalog['scrape']['models_in_catalog']} auto-sourced "
        f"({catalog['scrape']['coverage_pct']}% coverage)"
    )
    print(f"PR-worthy changes: {'yes' if meaningful else 'no (metadata/scrape only)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
