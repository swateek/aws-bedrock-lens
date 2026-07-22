"""Map AWS Price List (AmazonBedrockFoundationModels) SKUs to catalog on-demand prices."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx

from inventory import (
    inventory_record_from_stub,
    provision_catalog_entries,
    stub_catalog_entry_from_model_id,
)
from model_id_inference import (
    _normalize_key,
    build_name_lookup,
    clean_service_name,
    infer_model_id,
    is_legacy_service_name,
)
from price_merge import apply_price_facts, facts_to_catalog_fields
from sku_facts import extract_fm_facts

PRICE_LIST_BASE = "https://pricing.us-east-1.amazonaws.com"
FOUNDATION_MODELS_INDEX = (
    f"{PRICE_LIST_BASE}/offers/v1.0/aws/AmazonBedrockFoundationModels/current/us-east-1/index.json"
)
OVERRIDES_PATH = Path(__file__).resolve().parent / "sku_overrides.json"

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
    warnings: list[str] = []
    facts = extract_fm_facts(index, warnings=warnings)
    grouped = facts_to_catalog_fields(facts, catalog, warnings=warnings)
    by_model: dict[str, dict[str, float | None]] = {}
    for model_id, payload in grouped.items():
        fields = payload["fields"]
        by_model[model_id] = {
            "input_per_1m": fields.get("input_per_1m"),
            "output_per_1m": fields.get("output_per_1m"),
            "standard_per_image": fields.get("standard_per_image"),
            "premium_per_image": fields.get("premium_per_image"),
            "per_second": fields.get("per_second"),
            "per_search_unit": fields.get("per_search_unit"),
        }
    return by_model


def enumerate_on_demand_service_names(index: dict[str, Any]) -> dict[str, set[str]]:
    """Return cleaned servicename -> usagetypes with OnDemand pricing."""
    products = index.get("products", {})
    on_demand = index.get("terms", {}).get("OnDemand", {})
    by_name: dict[str, set[str]] = {}
    for product_id, product in products.items():
        if product_id not in on_demand:
            continue
        attrs = product.get("attributes", {})
        service_name = clean_service_name(attrs.get("servicename", ""))
        if not service_name:
            continue
        by_name.setdefault(service_name, set()).add(attrs.get("usagetype", ""))
    return by_name


def discover_models_from_price_list(
    catalog: dict,
    index: dict[str, Any],
) -> tuple[int, list[dict[str, Any]], list[str]]:
    """Infer and provision catalog entries for unknown Price List servicenames."""
    warnings: list[str] = []
    lookup = build_name_lookup(catalog)
    by_id = {m["model_id"]: m for m in catalog.get("models", [])}
    new_entries: list[dict[str, Any]] = []
    new_records: list[dict[str, Any]] = []

    for service_name in sorted(enumerate_on_demand_service_names(index)):
        if resolve_service_to_model_id(service_name, lookup):
            continue
        if is_legacy_service_name(service_name):
            continue
        model_id = infer_model_id(service_name, catalog)
        if not model_id:
            warnings.append(f"Unmapped Price List service (add override): {service_name}")
            continue
        if model_id in by_id:
            continue
        entry = stub_catalog_entry_from_model_id(
            model_id,
            display_name=clean_service_name(service_name),
        )
        new_entries.append(entry)
        new_records.append(inventory_record_from_stub(entry))
        by_id[model_id] = entry
        lookup[_normalize_key(service_name)] = model_id
        warnings.append(f"Auto-provisioned catalog entry from Price List: {model_id}")

    added = provision_catalog_entries(catalog, new_entries)
    return added, new_records, warnings


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
    """Apply Price List prices; set pricing_source to price_list when matched."""
    warnings: list[str] = []
    if index is None:
        index = fetch_price_list_index()

    facts = extract_fm_facts(index, region=region, warnings=warnings)
    updated, matched = apply_price_facts(
        catalog,
        facts,
        fill_gaps_only=False,
        source_label="price_list",
        warnings=warnings,
    )

    catalog.setdefault("meta", {})["price_list_region"] = region
    return updated, matched, warnings


def main() -> int:
    import argparse
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
