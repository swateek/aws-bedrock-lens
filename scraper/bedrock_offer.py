"""Merge on-demand prices from the AmazonBedrock public Price List offer."""

from __future__ import annotations

import re
from typing import Any

import httpx

from catalog_io import empty_on_demand, model_has_price
from offer_key_map import build_model_to_offer_keys, variant_base_candidates

def _token_unit_price(price_usd: float) -> float:
    """AmazonBedrock offer token SKUs are per 1K tokens; catalog stores per 1M."""
    return round(price_usd * 1000, 6)


PRICE_LIST_BASE = "https://pricing.us-east-1.amazonaws.com"
BEDROCK_OFFER_INDEX = (
    f"{PRICE_LIST_BASE}/offers/v1.0/aws/AmazonBedrock/current/us-east-1/index.json"
)

_EXCLUDED_UT = re.compile(
    r"batch|flex|priority|latency|provisioned|reserved|cache|cross-region|"
    r"custom-model|customization|rft|global|grounding",
    re.IGNORECASE,
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


def _is_standard_on_demand(usagetype: str) -> bool:
    return not _EXCLUDED_UT.search(usagetype)


def _price_from_on_demand(on_demand: dict, product_id: str) -> float | None:
    for dimension in on_demand.get(product_id, {}).values():
        for price_dim in dimension.get("priceDimensions", {}).values():
            raw = price_dim.get("pricePerUnit", {}).get("USD")
            if raw is not None:
                return float(raw)
    return None


def extract_offer_prices(index: dict[str, Any]) -> dict[str, dict[str, float | None]]:
    """Return offer_key -> partial on_demand fields from AmazonBedrock SKUs."""
    products = index.get("products", {})
    on_demand = index.get("terms", {}).get("OnDemand", {})
    by_key: dict[str, dict[str, float | None]] = {}

    def slot(key: str) -> dict[str, float | None]:
        return by_key.setdefault(
            key,
            {
                "input_per_1m": None,
                "output_per_1m": None,
                "standard_per_image": None,
                "premium_per_image": None,
            },
        )

    for product_id, product in products.items():
        if product_id not in on_demand:
            continue
        ut = product.get("attributes", {}).get("usagetype", "")
        if not _is_standard_on_demand(ut):
            continue
        price_usd = _price_from_on_demand(on_demand, product_id)
        if price_usd is None:
            continue

        if "T2I-1024-Standard" in ut or "I2I-1024-Standard" in ut:
            key = ut.split("-", 2)[1] if ut.startswith("USE1-") else ut
            m = re.search(r"USE1-(?P<k>NovaCanvas|NovaReel|TitanImageGenerator[^-]+)", ut)
            if m:
                entry = slot(m.group("k"))
                if entry["standard_per_image"] is None:
                    entry["standard_per_image"] = price_usd
            continue
        if "T2I-1024-Premium" in ut or "I2I-1024-Premium" in ut:
            m = re.search(r"USE1-(?P<k>NovaCanvas|TitanImageGenerator[^-]+)", ut)
            if m:
                slot(m.group("k"))["premium_per_image"] = price_usd
            continue
        if "NovaReel-T2V" in ut or "NovaReel-I2V" in ut:
            entry = slot("NovaReel")
            if entry["standard_per_image"] is None:
                entry["standard_per_image"] = price_usd
            continue
        if "NovaMultiModalEmbeddings-input-tokens" in ut:
            slot("NovaMultiModalEmbeddings")["input_per_1m"] = _token_unit_price(price_usd)
            continue
        if "TitanEmbeddingsG1-Text-input-tokens" in ut:
            slot("TitanEmbeddingsG1-Text")["input_per_1m"] = _token_unit_price(price_usd)
            continue
        if "TitanEmbeddingV2-Text-input-tokens" in ut:
            slot("TitanEmbeddingV2-Text")["input_per_1m"] = _token_unit_price(price_usd)
            continue
        if "TitanEmbeddingsG1-Image-input-tokens" in ut:
            slot("TitanEmbeddingsG1-Image")["input_per_1m"] = _token_unit_price(price_usd)
            continue

        parsed = _parse_token_usagetype(ut)
        if not parsed:
            continue
        key, kind = parsed
        entry = slot(key)
        per_1m = _token_unit_price(price_usd)
        if "input" in kind:
            if entry["input_per_1m"] is None:
                entry["input_per_1m"] = per_1m
        elif "output" in kind:
            if entry["output_per_1m"] is None:
                entry["output_per_1m"] = per_1m

    return by_key


def _apply_prices(model: dict, prices: dict[str, float | None]) -> tuple[bool, bool]:
    """Return (changed_values, has_any_price)."""
    pricing_type = model["pricing_type"]
    old = dict(model.get("on_demand", {}))
    new_slice = {**empty_on_demand(pricing_type), **old}

    if pricing_type == "token":
        for field in ("input_per_1m", "output_per_1m"):
            val = prices.get(field)
            if val is not None:
                new_slice[field] = val
    elif pricing_type == "embedding":
        val = prices.get("input_per_1m")
        if val is not None:
            new_slice["input_per_1m"] = val
    elif pricing_type == "image":
        for field in ("standard_per_image", "premium_per_image"):
            val = prices.get(field)
            if val is not None:
                new_slice[field] = val

    has_price = model_has_price({"on_demand": new_slice, "pricing_type": pricing_type})
    if not has_price:
        return False, False

    changed = new_slice != old
    model["pricing_source"] = "auto"
    if changed:
        model["on_demand"] = new_slice
    return changed, True


def merge_bedrock_offer_into_catalog(
    catalog: dict,
    *,
    index: dict[str, Any] | None = None,
    region: str = "us-east-1",
) -> tuple[int, int, list[str]]:
    """Apply AmazonBedrock offer prices to catalog models."""
    warnings: list[str] = []
    if index is None:
        index = fetch_bedrock_offer_index()

    offer_prices = extract_offer_prices(index)
    model_keys = build_model_to_offer_keys(catalog)
    by_id = {m["model_id"]: m for m in catalog["models"]}
    updated = 0
    matched = 0

    for model_id, keys in model_keys.items():
        if model_id not in by_id:
            continue
        merged: dict[str, float | None] = {
            "input_per_1m": None,
            "output_per_1m": None,
            "standard_per_image": None,
            "premium_per_image": None,
        }
        for key in keys:
            chunk = offer_prices.get(key)
            if not chunk:
                continue
            for field, val in chunk.items():
                if val is not None:
                    if field.endswith("_per_1m") and merged.get(field) is None:
                        merged[field] = val
                    elif field.endswith("_per_image") and merged.get(field) is None:
                        merged[field] = val

        if not any(v is not None for v in merged.values()):
            continue

        matched += 1
        model = by_id[model_id]
        changed, _ = _apply_prices(model, merged)
        if changed:
            updated += 1

    catalog.setdefault("meta", {})["bedrock_offer_region"] = region
    return updated, matched, warnings


def propagate_variant_prices(catalog: dict) -> int:
    """Copy on_demand prices from base model_id to context variants."""
    by_id = {m["model_id"]: m for m in catalog["models"]}
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
        model["pricing_source"] = base.get("pricing_source", "auto")
        if model["on_demand"] != old:
            updated += 1
    return updated
