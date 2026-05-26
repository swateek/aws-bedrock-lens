"""Map AWS Price List (AmazonBedrockFoundationModels) SKUs to catalog on-demand prices."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx

from catalog_io import REPO_ROOT, empty_on_demand

PRICE_LIST_BASE = "https://pricing.us-east-1.amazonaws.com"
FOUNDATION_MODELS_INDEX = (
    f"{PRICE_LIST_BASE}/offers/v1.0/aws/AmazonBedrockFoundationModels/current/us-east-1/index.json"
)
OVERRIDES_PATH = Path(__file__).resolve().parent / "sku_overrides.json"

_SERVICE_SUFFIX_RE = re.compile(r"\s*\(Amazon Bedrock Edition\)\s*$", re.IGNORECASE)
_EXCLUDED_UT = re.compile(
    r"batch|flex|priority|latency|provisioned|reserved|cache|global|"
    r"customization|custom model",
    re.IGNORECASE,
)


def _load_overrides() -> dict[str, str]:
    if not OVERRIDES_PATH.exists():
        return {}
    data = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    return dict(data.get("service_name_to_model_id", {}))


def clean_service_name(name: str) -> str:
    return _SERVICE_SUFFIX_RE.sub("", name).strip()


def _normalize_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def build_name_lookup(catalog: dict) -> dict[str, str]:
    """Map normalized display/model names and overrides to model_id."""
    lookup: dict[str, str] = {}
    for override_name, model_id in _load_overrides().items():
        lookup[_normalize_key(override_name)] = model_id
    for model in catalog.get("models", []):
        model_id = model["model_id"]
        for name in (model.get("display_name"), model_id.split(".")[-1]):
            if name:
                lookup[_normalize_key(name)] = model_id
        lookup[_normalize_key(model_id)] = model_id
    return lookup


def resolve_service_to_model_id(service_name: str, lookup: dict[str, str]) -> str | None:
    clean = clean_service_name(service_name)
    key = _normalize_key(clean)
    if key in lookup:
        return lookup[key]
    return None


def is_on_demand_token_usagetype(usagetype: str) -> bool:
    if _EXCLUDED_UT.search(usagetype):
        return False
    lower = usagetype.lower()
    if "inputtokencount" in lower or "outputtokencount" in lower:
        return True
    if re.search(r"input[_-]tokens(?:_standard)?-units$", lower):
        return "global" not in lower and "cache" not in lower
    if re.search(r"output[_-]tokens(?:_standard)?-units$", lower):
        return "global" not in lower and "cache" not in lower
    return False


def is_on_demand_embedding_usagetype(usagetype: str) -> bool:
    if _EXCLUDED_UT.search(usagetype):
        return False
    lower = usagetype.lower()
    if "cohere_embed" in lower:
        return True
    if "inputtokencount" in lower and "embed" in lower:
        return True
    if "inputtokencount-units" in lower:
        return True
    if "inputtextrequestcount" in lower:
        return True
    return False


def is_on_demand_image_usagetype(usagetype: str) -> bool:
    if _EXCLUDED_UT.search(usagetype):
        return False
    lower = usagetype.lower()
    return "created_image" in lower or "created-image" in lower


def is_on_demand_rerank_usagetype(usagetype: str) -> bool:
    return "search_units" in usagetype.lower()


def fetch_price_list_index(url: str = FOUNDATION_MODELS_INDEX) -> dict[str, Any]:
    response = httpx.get(url, timeout=180, follow_redirects=True)
    response.raise_for_status()
    return response.json()


def _price_from_on_demand(on_demand: dict, product_id: str) -> float | None:
    for dimension in on_demand.get(product_id, {}).values():
        for price_dim in dimension.get("priceDimensions", {}).values():
            raw = price_dim.get("pricePerUnit", {}).get("USD")
            if raw is not None:
                return float(raw)
    return None


def _token_field(usagetype: str) -> str | None:
    lower = usagetype.lower()
    if "inputtokencount" in lower or re.search(r"input[_-]tokens", lower):
        return "input_per_1m"
    if "outputtokencount" in lower or re.search(r"output[_-]tokens", lower):
        return "output_per_1m"
    return None


def extract_prices_from_index(
    index: dict[str, Any],
    catalog: dict,
) -> dict[str, dict[str, float | None]]:
    """Return model_id -> on_demand fields from Foundation Models OnDemand SKUs."""
    lookup = build_name_lookup(catalog)
    products = index.get("products", {})
    on_demand = index.get("terms", {}).get("OnDemand", {})

    by_model: dict[str, dict[str, float | None]] = {}

    for product_id, product in products.items():
        if product_id not in on_demand:
            continue
        attrs = product.get("attributes", {})
        usagetype = attrs.get("usagetype", "")
        service_name = attrs.get("servicename", "")
        model_id = resolve_service_to_model_id(service_name, lookup)
        if not model_id:
            continue

        price_usd = _price_from_on_demand(on_demand, product_id)
        if price_usd is None:
            continue

        entry = by_model.setdefault(
            model_id,
            {
                "input_per_1m": None,
                "output_per_1m": None,
                "standard_per_image": None,
                "premium_per_image": None,
            },
        )

        model = next((m for m in catalog.get("models", []) if m["model_id"] == model_id), None)
        ptype = model.get("pricing_type", "token") if model else "token"

        if ptype == "token" and is_on_demand_token_usagetype(usagetype):
            field = _token_field(usagetype)
            if field:
                entry[field] = round(price_usd, 6)
        elif ptype == "embedding":
            if is_on_demand_rerank_usagetype(usagetype):
                entry["input_per_1m"] = price_usd
            elif is_on_demand_embedding_usagetype(usagetype) or is_on_demand_token_usagetype(usagetype):
                per_1m = round(price_usd, 6) if "tokencount" in usagetype.lower() else price_usd
                if entry["input_per_1m"] is None:
                    entry["input_per_1m"] = per_1m
        elif ptype == "image" and is_on_demand_image_usagetype(usagetype):
            if entry["standard_per_image"] is None:
                entry["standard_per_image"] = price_usd

    return by_model


def extract_token_prices_from_index(
    index: dict[str, Any],
    catalog: dict,
) -> dict[str, dict[str, float | None]]:
    """Backward-compatible token-only view."""
    all_prices = extract_prices_from_index(index, catalog)
    return {
        mid: {"input_per_1m": p["input_per_1m"], "output_per_1m": p["output_per_1m"]}
        for mid, p in all_prices.items()
    }


def merge_price_list_into_catalog(
    catalog: dict,
    *,
    index: dict[str, Any] | None = None,
    region: str = "us-east-1",
) -> tuple[int, int, list[str]]:
    """Apply Price List prices; set pricing_source to auto when matched."""
    warnings: list[str] = []
    if index is None:
        index = fetch_price_list_index()

    prices_by_model = extract_prices_from_index(index, catalog)
    by_id = {m["model_id"]: m for m in catalog["models"]}
    updated = 0
    skipped = 0

    for model_id, prices in prices_by_model.items():
        if model_id not in by_id:
            warnings.append(f"Price list matched unknown model_id: {model_id}")
            continue
        model = by_id[model_id]
        pricing_type = model["pricing_type"]
        if not any(v is not None for v in prices.values()):
            continue

        if pricing_type == "token":
            if prices.get("input_per_1m") is None and prices.get("output_per_1m") is None:
                continue
        elif pricing_type == "embedding":
            if prices.get("input_per_1m") is None:
                skipped += 1
                continue
        elif pricing_type == "image":
            if prices.get("standard_per_image") is None and prices.get("premium_per_image") is None:
                skipped += 1
                continue
        else:
            skipped += 1
            continue

        old = dict(model.get("on_demand", {}))
        new_slice = {**empty_on_demand(pricing_type), **old}
        if pricing_type == "token":
            if prices.get("input_per_1m") is not None:
                new_slice["input_per_1m"] = prices["input_per_1m"]
            if prices.get("output_per_1m") is not None:
                new_slice["output_per_1m"] = prices["output_per_1m"]
        elif pricing_type == "embedding":
            new_slice["input_per_1m"] = prices["input_per_1m"]
        elif pricing_type == "image" and prices.get("standard_per_image") is not None:
            new_slice["standard_per_image"] = prices["standard_per_image"]

        model["pricing_source"] = "auto"
        if old == new_slice:
            continue

        model["on_demand"] = new_slice
        updated += 1

    catalog.setdefault("meta", {})["price_list_region"] = region
    return updated, len(prices_by_model), warnings


def main() -> int:
    import argparse
    import sys
    from datetime import date

    from catalog_io import DATA_PATH, load_catalog, write_catalog

    parser = argparse.ArgumentParser(description="Merge AWS Price List into pricing.json")
    parser.add_argument("--catalog", type=Path, default=DATA_PATH)
    args = parser.parse_args()

    catalog = load_catalog(args.catalog)
    today = date.today().isoformat()
    updated, matched, warnings = merge_price_list_into_catalog(catalog)
    catalog["meta"]["last_price_list_at"] = today

    for w in warnings[:15]:
        print(f"WARN: {w}")

    write_catalog(catalog, args.catalog)
    print(f"Price list: {matched} services mapped, {updated} catalog rows updated")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
