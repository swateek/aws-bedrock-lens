"""Curated list prices for models missing from AWS Price List SKUs (preview / video / batch-only)."""

from __future__ import annotations

from catalog_io import empty_on_demand, model_has_price

# Verified against AWS marketing examples or published list prices (2026-05).
# pricing_source remains "manual" — not overwritten by scrape merges.
PRICE_SEEDS: dict[str, dict] = {
    "meta.llama3-1-405b-instruct-v1:0": {
        "input_per_1m": 5.32,
        "output_per_1m": 16.0,
        "notes": "On-demand list price per AWS Bedrock pricing page (batch tiers may differ).",
    },
    "amazon.rerank-v1:0": {
        "input_per_1m": 0.002,
        "notes": "Per search unit (Rerank API); aligned with Amazon Rerank 1.0 pricing examples on AWS site.",
    },
    "luma.ray-v2:0": {
        "input_per_1m": 0.08,
        "notes": "Video generation billed per second of output; value shown is USD per second (not per 1M tokens).",
    },
}


def merge_price_seeds_into_catalog(catalog: dict) -> int:
    """Fill gaps from PRICE_SEEDS for models still without list prices."""
    by_id = {m["model_id"]: m for m in catalog["models"]}
    updated = 0
    for model_id, seed in PRICE_SEEDS.items():
        model = by_id.get(model_id)
        if not model or model_has_price(model):
            continue
        pricing_type = model["pricing_type"]
        new_slice = {**empty_on_demand(pricing_type), **model.get("on_demand", {})}
        if pricing_type == "token":
            if seed.get("input_per_1m") is not None:
                new_slice["input_per_1m"] = seed["input_per_1m"]
            if seed.get("output_per_1m") is not None:
                new_slice["output_per_1m"] = seed["output_per_1m"]
        elif pricing_type == "embedding" and seed.get("input_per_1m") is not None:
            new_slice["input_per_1m"] = seed["input_per_1m"]
        if not model_has_price({"on_demand": new_slice, "pricing_type": pricing_type}):
            continue
        model["on_demand"] = new_slice
        model["pricing_source"] = "manual"
        if seed.get("notes"):
            model["notes"] = seed["notes"]
        updated += 1
    return updated
