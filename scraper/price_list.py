"""Map AWS Price List (AmazonBedrockFoundationModels) SKUs to catalog on-demand prices."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx

from catalog_io import REPO_ROOT
from parser import per_1m_to_per_1k

PRICE_LIST_BASE = "https://pricing.us-east-1.amazonaws.com"
FOUNDATION_MODELS_INDEX = (
    f"{PRICE_LIST_BASE}/offers/v1.0/aws/AmazonBedrockFoundationModels/current/us-east-1/index.json"
)
OVERRIDES_PATH = Path(__file__).resolve().parent / "sku_overrides.json"

_SERVICE_SUFFIX_RE = re.compile(r"\s*\(Amazon Bedrock Edition\)\s*$", re.IGNORECASE)


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
    if "InputTokenCount" not in usagetype and "OutputTokenCount" not in usagetype:
        return False
    if any(x in usagetype for x in ("Cache", "Reserved", "Provisioned", "Batch")):
        return False
    return True


def fetch_price_list_index(url: str = FOUNDATION_MODELS_INDEX) -> dict[str, Any]:
    response = httpx.get(url, timeout=180, follow_redirects=True)
    response.raise_for_status()
    return response.json()


def extract_token_prices_from_index(
    index: dict[str, Any],
    catalog: dict,
) -> dict[str, dict[str, float | None]]:
    """Return model_id -> {input_per_1k, output_per_1k} from OnDemand token SKUs."""
    lookup = build_name_lookup(catalog)
    products = index.get("products", {})
    on_demand = index.get("terms", {}).get("OnDemand", {})

    by_model: dict[str, dict[str, float | None]] = {}

    for product_id, product in products.items():
        if product_id not in on_demand:
            continue
        attrs = product.get("attributes", {})
        usagetype = attrs.get("usagetype", "")
        if not is_on_demand_token_usagetype(usagetype):
            continue

        service_name = attrs.get("servicename", "")
        model_id = resolve_service_to_model_id(service_name, lookup)
        if not model_id:
            continue

        price_usd: float | None = None
        for dimension in on_demand[product_id].values():
            for price_dim in dimension.get("priceDimensions", {}).values():
                raw = price_dim.get("pricePerUnit", {}).get("USD")
                if raw is not None:
                    price_usd = float(raw)
                    break
            if price_usd is not None:
                break
        if price_usd is None:
            continue

        per_1k = per_1m_to_per_1k(price_usd)
        entry = by_model.setdefault(model_id, {"input_per_1k": None, "output_per_1k": None})
        if "InputTokenCount" in usagetype:
            entry["input_per_1k"] = per_1k
        elif "OutputTokenCount" in usagetype:
            entry["output_per_1k"] = per_1k

    return by_model


def merge_price_list_into_catalog(
    catalog: dict,
    *,
    index: dict[str, Any] | None = None,
    region: str = "us-east-1",
) -> tuple[int, int, list[str]]:
    """Apply Price List token prices; set pricing_source to auto when updated."""
    warnings: list[str] = []
    if index is None:
        index = fetch_price_list_index()

    prices_by_model = extract_token_prices_from_index(index, catalog)
    by_id = {m["model_id"]: m for m in catalog["models"]}
    updated = 0
    skipped = 0

    for model_id, prices in prices_by_model.items():
        if model_id not in by_id:
            warnings.append(f"Price list matched unknown model_id: {model_id}")
            continue
        model = by_id[model_id]
        if model["pricing_type"] != "token":
            skipped += 1
            continue
        if prices.get("input_per_1k") is None and prices.get("output_per_1k") is None:
            continue

        old = dict(model.get("on_demand", {}))
        new_slice = {**old}
        if prices.get("input_per_1k") is not None:
            new_slice["input_per_1k"] = prices["input_per_1k"]
        if prices.get("output_per_1k") is not None:
            new_slice["output_per_1k"] = prices["output_per_1k"]

        if old == new_slice:
            continue

        model["on_demand"] = new_slice
        model["pricing_source"] = "auto"
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
