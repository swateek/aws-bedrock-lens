#!/usr/bin/env python3
"""
Probe AWS pricing sources for Bedrock (no catalog writes).

  python scraper/aws_pricing_probe.py           # public price list index
  python scraper/aws_pricing_probe.py --sample  # optional GetProducts (needs boto3 + AWS creds)
"""

from __future__ import annotations

import argparse
import json
import sys

import httpx

PRICE_LIST_INDEX = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/index.json"
BEDROCK_OFFER_CODES = (
    "AmazonBedrock",
    "AmazonBedrockFoundationModels",
)


def probe_public_index() -> int:
    print(f"GET {PRICE_LIST_INDEX}")
    r = httpx.get(PRICE_LIST_INDEX, timeout=30, follow_redirects=True)
    r.raise_for_status()
    data = r.json()
    offers = data.get("offers", {})
    print(f"Total AWS offers in index: {len(offers)}")

    found = []
    for code, meta in offers.items():
        if "bedrock" in code.lower() or "bedrock" in meta.get("offerCode", "").lower():
            found.append((code, meta.get("currentVersion"), meta.get("offerCode")))

    if not found:
        print("No Bedrock-related offers in index (search by name).")
        for guess in BEDROCK_OFFER_CODES:
            if guess in offers:
                found.append((guess, offers[guess].get("currentVersion"), guess))

    print("\nBedrock-related offers:")
    for code, version, offer in found:
        print(f"  - {code} (offerCode={offer}, version={version})")
        if version and offer:
            url = (
                f"https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/"
                f"{offer}/{version}/us-east-1/index.json"
            )
            print(f"    Region file: {url}")

    print(
        "\nNext step: download us-east-1 index.json and map SKUs to model_id "
        "(see docs/PRICING_SOURCES.md)."
    )
    return 0


def probe_get_products_sample() -> int:
    try:
        import boto3
    except ImportError:
        print("Install boto3 for --sample: pip install boto3", file=sys.stderr)
        return 1

    client = boto3.client("pricing", region_name="us-east-1")
    for service in ("AmazonBedrock", "AmazonBedrockFoundationModels", "Bedrock"):
        print(f"\nGetProducts ServiceCode={service!r} (max 3)...")
        try:
            resp = client.get_products(
                ServiceCode=service,
                Filters=[
                    {"Type": "TERM_MATCH", "Field": "regionCode", "Value": "us-east-1"},
                ],
                MaxResults=3,
            )
        except client.exceptions.ClientError as exc:
            print(f"  Error: {exc}")
            continue

        for i, row in enumerate(resp.get("PriceList", []), 1):
            product = json.loads(row)
            attrs = product.get("product", {}).get("attributes", {})
            print(f"  [{i}] {attrs.get('usagetype', '?')} | {attrs.get('operation', '?')}")
            print(f"      sku={product.get('product', {}).get('sku', '?')}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe AWS Bedrock pricing APIs")
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Call pricing:GetProducts (requires boto3 and AWS credentials)",
    )
    args = parser.parse_args()

    try:
        rc = probe_public_index()
        if args.sample:
            rc = probe_get_products_sample() or rc
        return rc
    except httpx.HTTPError as exc:
        print(f"HTTP error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
