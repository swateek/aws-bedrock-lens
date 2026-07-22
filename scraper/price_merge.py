"""Resolve SKU facts to catalog models and apply merge policy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from catalog_io import PRICE_EPSILON as CATALOG_EPSILON
from catalog_io import empty_on_demand, model_has_price
from model_id_inference import _normalize_key, build_name_lookup, clean_service_name, infer_model_id
from offer_key_map import build_model_to_offer_keys
from sku_facts import SkuFact

OVERRIDES_PATH = Path(__file__).resolve().parent / "sku_overrides.json"


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


def resolve_fact_model_id(fact: SkuFact, catalog: dict, lookup: dict[str, str]) -> str | None:
    if fact.model_id:
        return fact.model_id
    if fact.service_name:
        mid = resolve_service_to_model_id(fact.service_name, lookup)
        if mid:
            return mid
        mid = infer_model_id(fact.service_name, catalog)
        if mid:
            return mid
    return None


def facts_to_catalog_fields(
    facts: list[SkuFact],
    catalog: dict,
    *,
    fill_gaps_only: bool = False,
    warnings: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Group resolved facts into model_id -> {field: value, provenance: {...}}."""
    warn = warnings if warnings is not None else []
    lookup = build_name_lookup(catalog)
    overrides = _load_overrides()
    lookup.update({_normalize_key(k): v for k, v in overrides.items()})

    offer_key_to_model: dict[str, str] = {}
    for model_id, keys in build_model_to_offer_keys(catalog).items():
        for key in keys:
            offer_key_to_model.setdefault(key, model_id)

    by_model: dict[str, dict[str, Any]] = {}

    for fact in facts:
        model_id = resolve_fact_model_id(fact, catalog, lookup)
        if not model_id and fact.offer_key:
            model_id = offer_key_to_model.get(fact.offer_key)
        if not model_id:
            continue

        entry = by_model.setdefault(model_id, {"fields": {}, "provenance": {}})
        field = fact.catalog_field
        existing = entry["fields"].get(field)
        if existing is not None and abs(existing - fact.rate_usd) > CATALOG_EPSILON:
            warn.append(
                f"Price conflict for {model_id}.{field}: "
                f"{existing} vs {fact.rate_usd} ({fact.source_offer})"
            )
            if fill_gaps_only:
                continue
            # Prefer higher-confidence non-zero rate over a later conflicting SKU.
            if fact.rate_usd <= existing:
                continue
        if fill_gaps_only and existing is not None:
            continue
        if existing is None:
            entry["fields"][field] = fact.rate_usd
            entry["provenance"][field] = fact.to_provenance()

    return by_model


def apply_price_facts(
    catalog: dict,
    facts: list[SkuFact],
    *,
    fill_gaps_only: bool = False,
    source_label: str = "price_list",
    warnings: list[str] | None = None,
) -> tuple[int, int]:
    """Apply resolved facts to catalog. Returns (updated_count, matched_count)."""
    warn = warnings if warnings is not None else []
    grouped = facts_to_catalog_fields(facts, catalog, fill_gaps_only=fill_gaps_only, warnings=warn)
    by_id = {m["model_id"]: m for m in catalog["models"]}
    updated = 0
    matched = 0

    for model_id, payload in grouped.items():
        fields = payload["fields"]
        if not fields:
            continue
        if model_id not in by_id:
            from inventory import provision_catalog_entries, stub_catalog_entry_from_model_id

            entry = stub_catalog_entry_from_model_id(model_id)
            provision_catalog_entries(catalog, [entry])
            by_id[model_id] = entry
            warn.append(f"Auto-provisioned catalog entry from Price List: {model_id}")

        model = by_id[model_id]
        pricing_type = model["pricing_type"]
        old = dict(model.get("on_demand", {}))
        new_slice = {**empty_on_demand(pricing_type), **old}

        applicable = _applicable_fields(pricing_type, fields)
        if not applicable:
            continue

        matched += 1
        changed = False
        for field, val in applicable.items():
            if fill_gaps_only and new_slice.get(field) is not None:
                continue
            if new_slice.get(field) != val:
                new_slice[field] = val
                changed = True

        if not model_has_price({"on_demand": new_slice, "pricing_type": pricing_type}):
            continue

        prov = model.get("price_provenance") or {}
        for field, p in payload.get("provenance", {}).items():
            if field in applicable:
                prov[field] = p
        if prov:
            model["price_provenance"] = prov

        model["pricing_source"] = source_label
        if changed:
            model["on_demand"] = new_slice
            updated += 1
        elif model.get("pricing_source") != source_label:
            model["pricing_source"] = source_label
            updated += 1

    return updated, matched


def _applicable_fields(pricing_type: str, fields: dict[str, float]) -> dict[str, float]:
    token_fields = {"input_per_1m", "output_per_1m"}
    image_fields = {"standard_per_image", "premium_per_image"}
    video_fields = {"per_second"}
    rerank_fields = {"per_search_unit"}
    embedding_fields = {"input_per_1m"}

    allowed: set[str]
    if pricing_type == "token":
        allowed = token_fields
    elif pricing_type == "image":
        allowed = image_fields
    elif pricing_type == "video":
        allowed = video_fields
    elif pricing_type == "rerank":
        allowed = rerank_fields
    elif pricing_type == "embedding":
        allowed = embedding_fields
    else:
        allowed = set(fields.keys())

    return {k: v for k, v in fields.items() if k in allowed}


def qa_check_html_prices(
    catalog: dict,
    scraped_rows: list[dict],
    *,
    warnings: list[str] | None = None,
) -> int:
    """Compare HTML marketing literals to catalog; emit warnings only."""
    warn = warnings if warnings is not None else []
    mismatches = 0
    by_id = {m["model_id"]: m for m in catalog["models"]}

    for row in scraped_rows:
        model_id = row["model_id"]
        model = by_id.get(model_id)
        if not model:
            continue
        od = model.get("on_demand") or {}
        for field, html_val in row.get("pricing", {}).items():
            if html_val is None:
                continue
            cat_val = od.get(field)
            if cat_val is None:
                continue
            if abs(cat_val - html_val) > CATALOG_EPSILON:
                mismatches += 1
                warn.append(
                    f"HTML QA mismatch {model_id}.{field}: catalog={cat_val} html={html_val}"
                )
    return mismatches
