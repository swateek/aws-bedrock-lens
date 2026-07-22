"""Merge on-demand prices from the AmazonBedrock public Price List offer."""

from __future__ import annotations

from typing import Any

import httpx

from catalog_io import empty_on_demand, model_has_price
from offer_key_map import variant_base_candidates
from price_merge import apply_price_facts
from sku_facts import extract_bedrock_offer_facts

PRICE_LIST_BASE = "https://pricing.us-east-1.amazonaws.com"
BEDROCK_OFFER_INDEX = f"{PRICE_LIST_BASE}/offers/v1.0/aws/AmazonBedrock/current/index.json"
BEDROCK_OFFER_INDEX_REGIONAL = (
    f"{PRICE_LIST_BASE}/offers/v1.0/aws/AmazonBedrock/current/{{region}}/index.json"
)

_TOKEN_UT_SUFFIXES = (
    "text-input-tokens",
    "text-output-tokens",
    "speech-input-tokens",
    "speech-output-tokens",
    "input-tokens",
    "output-tokens",
)


def _parse_token_usagetype(usagetype: str) -> tuple[str, str] | None:
    if not usagetype.startswith("USE1-"):
        return None
    body = usagetype[5:]
    for suffix in _TOKEN_UT_SUFFIXES:
        for tail in ("", "-standard"):
            needle = f"-{suffix}{tail}"
            if body.endswith(needle):
                key = body[: -len(needle)]
                return key, suffix
    return None


def fetch_bedrock_offer_index(url: str = BEDROCK_OFFER_INDEX) -> dict[str, Any]:
    response = httpx.get(url, timeout=180, follow_redirects=True)
    response.raise_for_status()
    return response.json()


def extract_offer_prices(index: dict[str, Any]) -> dict[str, dict[str, float | None]]:
    """Return offer_key -> partial on_demand fields from AmazonBedrock SKUs."""
    warnings: list[str] = []
    facts = extract_bedrock_offer_facts(index, warnings=warnings)
    by_key: dict[str, dict[str, float | None]] = {}

    for fact in facts:
        if not fact.offer_key:
            continue
        entry = by_key.setdefault(
            fact.offer_key,
            {
                "input_per_1m": None,
                "output_per_1m": None,
                "standard_per_image": None,
                "premium_per_image": None,
            },
        )
        field = fact.catalog_field
        if entry.get(field) is None:
            entry[field] = fact.rate_usd

    return by_key


def merge_bedrock_offer_into_catalog(
    catalog: dict,
    *,
    index: dict[str, Any] | None = None,
    region: str = "us-east-1",
    regions_allowlist: set[str] | None = None,
) -> tuple[int, int, list[str]]:
    """Apply AmazonBedrock offer prices to catalog (fills gaps after FM Price List)."""
    warnings: list[str] = []
    if index is None:
        index = fetch_bedrock_offer_index()

    facts = extract_bedrock_offer_facts(
        index,
        region=region,
        regions_allowlist=regions_allowlist,
        warnings=warnings,
    )
    updated, matched = apply_price_facts(
        catalog,
        facts,
        fill_gaps_only=True,
        source_label="price_list",
        warnings=warnings,
    )

    catalog.setdefault("meta", {})["bedrock_offer_region"] = region
    return updated, matched, warnings


def propagate_variant_prices(catalog: dict) -> int:
    """Copy on_demand / list_prices from base model_id to context variants."""
    from catalog_io import DEFAULT_PRICE_REGION, ensure_list_prices, sync_on_demand_alias

    by_id = {m["model_id"]: m for m in catalog["models"]}
    default_region = catalog.get("meta", {}).get("default_price_region") or DEFAULT_PRICE_REGION
    updated = 0
    for model in catalog["models"]:
        if model_has_price(model):
            continue
        base = None
        for base_id in variant_base_candidates(model["model_id"])[1:]:
            candidate = by_id.get(base_id)
            if candidate and model_has_price(candidate):
                base = candidate
                break
        if not base:
            continue
        if model["pricing_type"] != base["pricing_type"]:
            continue
        old = dict(model.get("on_demand", {}))
        model["on_demand"] = {**empty_on_demand(model["pricing_type"]), **base.get("on_demand", {})}
        if base.get("list_prices"):
            model["list_prices"] = {
                region: {tier: dict(slice_) for tier, slice_ in tiers.items()}
                for region, tiers in base["list_prices"].items()
            }
        else:
            ensure_list_prices(model, default_region=default_region)
        sync_on_demand_alias(model, default_region=default_region)
        model["pricing_source"] = base.get("pricing_source", "price_list")
        if base.get("price_provenance"):
            model["price_provenance"] = dict(base["price_provenance"])
        if model["on_demand"] != old:
            updated += 1
    return updated
