"""Read, validate, hash, and write the pricing catalog."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "data" / "pricing.json"
EMBED_PATH = REPO_ROOT / "data" / "pricing.embed.js"
SCHEMA_PATH = REPO_ROOT / "schemas" / "pricing.schema.json"
PRICING_URL = "https://aws.amazon.com/bedrock/pricing/"
PARSER_VERSION = "4"
PRICE_EPSILON = 1e-6
DEFAULT_PRICE_REGION = "us-east-1"
SCHEMA_VERSION = "3.0"


def load_schema() -> dict:
    with SCHEMA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def load_catalog(path: Path = DATA_PATH) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def validate_catalog(data: dict) -> None:
    schema = load_schema()
    jsonschema.validate(instance=data, schema=schema)


def pricing_fingerprint(models: list[dict]) -> str:
    """Stable hash of list_prices (and on_demand fallback) for all models."""
    payload = {}
    for m in sorted(models, key=lambda x: x["model_id"]):
        payload[m["model_id"]] = {
            "on_demand": m.get("on_demand", {}),
            "list_prices": m.get("list_prices", {}),
        }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def pr_change_payload(data: dict) -> dict[str, Any]:
    """Fields that should trigger a pricing PR (excludes last_scraped_at)."""
    return {
        "pricing_hash": pricing_fingerprint(data.get("models", [])),
        "pricing_updated_at": data.get("meta", {}).get("pricing_updated_at"),
        "pricing_sources": {
            m["model_id"]: m.get("pricing_source", "manual")
            for m in sorted(data.get("models", []), key=lambda x: x["model_id"])
        },
        "scrape": data.get("scrape", {}),
    }


def catalogs_meaningfully_differ(before: dict, after: dict) -> bool:
    """True if a human should review a PR (not scrape-only timestamp churn)."""
    return json.dumps(pr_change_payload(before), sort_keys=True) != json.dumps(
        pr_change_payload(after), sort_keys=True
    )


def empty_on_demand(pricing_type: str) -> dict:
    base = {
        "input_per_1m": None,
        "output_per_1m": None,
        "standard_per_image": None,
        "premium_per_image": None,
        "per_second": None,
        "per_search_unit": None,
    }
    return dict(base)


def empty_rate_slice(*, cache: bool = False) -> dict:
    if cache:
        return {
            "read_input_per_1m": None,
            "write_input_per_1m": None,
            "write_1h_input_per_1m": None,
        }
    return empty_on_demand("token")


def sync_on_demand_alias(model: dict, *, default_region: str = DEFAULT_PRICE_REGION) -> None:
    """Keep top-level on_demand ≡ list_prices[default].on_demand when present."""
    list_prices = model.get("list_prices") or {}
    region_prices = list_prices.get(default_region) or {}
    od_tier = region_prices.get("on_demand")
    if isinstance(od_tier, dict) and any(
        v is not None and isinstance(v, int | float) for v in od_tier.values()
    ):
        merged = {
            **empty_on_demand(model["pricing_type"]),
            **{k: od_tier.get(k) for k in empty_on_demand(model["pricing_type"])},
        }
        model["on_demand"] = normalize_on_demand({**model, "on_demand": merged})
    elif not model.get("on_demand"):
        model["on_demand"] = empty_on_demand(model["pricing_type"])


def ensure_list_prices(model: dict, *, default_region: str = DEFAULT_PRICE_REGION) -> None:
    """Migrate flat on_demand into list_prices[default].on_demand when missing."""
    list_prices = model.setdefault("list_prices", {})
    region_prices = list_prices.setdefault(default_region, {})
    if "on_demand" not in region_prices and model.get("on_demand"):
        od = normalize_on_demand(model)
        if any(v is not None for v in od.values()):
            region_prices["on_demand"] = {
                k: od.get(k) for k in empty_on_demand(model["pricing_type"])
            }
    # Normalize existing non-cache tiers to known keys only
    for region, tiers in list(list_prices.items()):
        if not isinstance(tiers, dict):
            continue
        for tier, slice_ in list(tiers.items()):
            if not isinstance(slice_, dict):
                continue
            if tier.startswith("cache"):
                list_prices[region][tier] = {
                    **empty_rate_slice(cache=True),
                    **{k: slice_.get(k) for k in empty_rate_slice(cache=True)},
                }
            else:
                list_prices[region][tier] = {
                    k: slice_.get(k) for k in empty_on_demand(model["pricing_type"])
                }
    sync_on_demand_alias(model, default_region=default_region)


def normalize_on_demand(model: dict) -> dict:
    base = empty_on_demand(model["pricing_type"])
    incoming = model.get("on_demand") or {}
    for key in base:
        if key in incoming:
            base[key] = incoming[key]
    pricing_type = model["pricing_type"]
    if pricing_type == "token":
        base["standard_per_image"] = None
        base["premium_per_image"] = None
    elif pricing_type == "embedding":
        base["output_per_1m"] = None
        base["standard_per_image"] = None
        base["premium_per_image"] = None
    elif pricing_type == "image":
        base["input_per_1m"] = None
        base["output_per_1m"] = None
        base["per_second"] = None
        base["per_search_unit"] = None
    elif pricing_type == "video":
        base["input_per_1m"] = None
        base["output_per_1m"] = None
        base["standard_per_image"] = None
        base["premium_per_image"] = None
        base["per_search_unit"] = None
    elif pricing_type == "rerank":
        base["input_per_1m"] = None
        base["output_per_1m"] = None
        base["standard_per_image"] = None
        base["premium_per_image"] = None
        base["per_second"] = None
    return base


def model_has_price(model: dict) -> bool:
    """True if any on_demand field has a numeric price."""
    od = model.get("on_demand") or {}
    for key in (
        "input_per_1m",
        "output_per_1m",
        "standard_per_image",
        "premium_per_image",
        "per_second",
        "per_search_unit",
    ):
        val = od.get(key)
        if val is not None and isinstance(val, int | float):
            return True
    return False


def compute_coverage_stats(catalog: dict) -> dict[str, Any]:
    models = catalog.get("models", [])
    total = len(models)
    with_prices = sum(1 for m in models if model_has_price(m))
    auto_count = sum(1 for m in models if m.get("pricing_source") in ("auto", "price_list"))
    models_known = catalog.get("meta", {}).get("models_known_to_aws") or total
    return {
        "models_matched": auto_count,
        "models_in_catalog": total,
        "models_with_prices": with_prices,
        "models_known_to_aws": models_known,
        "coverage_pct": round(100 * auto_count / total) if total else 0,
        "price_coverage_pct": round(100 * with_prices / total) if total else 0,
        "inventory_coverage_pct": (
            min(100, round(100 * total / models_known)) if models_known else 100
        ),
        "warnings": list(catalog.get("scrape", {}).get("warnings", [])),
    }


def migrate_legacy_unit_fields(model: dict) -> None:
    """Move mis-typed per-second / per-search prices off input_per_1m."""
    model_id = model.get("model_id", "")
    od = model.get("on_demand") or {}
    if model_id == "amazon.rerank-v1:0" and od.get("input_per_1m") is not None:
        model["pricing_type"] = "rerank"
        od = {**empty_on_demand("rerank"), **od}
        od["per_search_unit"] = od.pop("input_per_1m")
        od["input_per_1m"] = None
        model["on_demand"] = od
    if model_id == "luma.ray-v2:0" and od.get("input_per_1m") is not None:
        model["pricing_type"] = "video"
        od = {**empty_on_demand("video"), **od}
        od["per_second"] = od.pop("input_per_1m")
        od["input_per_1m"] = None
        model["on_demand"] = od


def normalize_catalog(data: dict) -> dict:
    """Ensure v3 shape with list_prices and consistent on_demand keys."""
    meta = data.setdefault("meta", {})
    meta["schema_version"] = SCHEMA_VERSION
    meta.setdefault("source", PRICING_URL)
    meta.setdefault("parser_version", PARSER_VERSION)
    meta.setdefault("last_scraped_at", None)
    meta.setdefault("pricing_updated_at", None)
    meta.setdefault("last_inventory_sync_at", None)
    meta.setdefault("models_known_to_aws", None)
    meta.setdefault("last_price_list_at", None)
    default_region = (
        meta.get("default_price_region") or meta.get("price_list_region") or DEFAULT_PRICE_REGION
    )
    meta["default_price_region"] = default_region
    meta["price_list_region"] = default_region
    if not meta.get("price_list_regions"):
        meta["price_list_regions"] = [default_region]
    products = meta.get("products")
    if products is None:
        meta["products"] = [
            {
                "id": "codex-on-bedrock",
                "name": "Codex on Amazon Bedrock",
                "provider": "OpenAI",
                "notes": (
                    "Codex is a coding agent product that routes inference through Bedrock; "
                    "it is not a separate foundation model_id. Bill via underlying OpenAI "
                    "models or your AWS agreement."
                ),
                "url": "https://aws.amazon.com/about-aws/whats-new/2026/04/bedrock-openai-models-codex-managed-agents/",
            }
        ]

    scrape = data.setdefault("scrape", {})
    scrape.setdefault("models_matched", 0)
    scrape.setdefault("models_in_catalog", len(data.get("models", [])))
    scrape.setdefault("models_with_prices", 0)
    scrape.setdefault("models_known_to_aws", meta.get("models_known_to_aws") or 0)
    scrape.setdefault("coverage_pct", 0)
    scrape.setdefault("price_coverage_pct", 0)
    scrape.setdefault("inventory_coverage_pct", 100)
    scrape.setdefault("warnings", [])

    for model in data.get("models", []):
        migrate_legacy_unit_fields(model)
        model.setdefault("pricing_source", "manual")
        model.setdefault("availability", "ga")
        model.setdefault("alternate_ids", [])
        model["on_demand"] = normalize_on_demand(model)
        ensure_list_prices(model, default_region=default_region)

    stats = compute_coverage_stats(data)
    data["scrape"].update(
        {
            "models_matched": stats["models_matched"],
            "models_in_catalog": stats["models_in_catalog"],
            "models_with_prices": stats["models_with_prices"],
            "models_known_to_aws": stats["models_known_to_aws"],
            "coverage_pct": stats["coverage_pct"],
            "price_coverage_pct": stats["price_coverage_pct"],
            "inventory_coverage_pct": stats["inventory_coverage_pct"],
        }
    )
    return data


def write_embed_js(data: dict, path: Path = EMBED_PATH) -> None:
    payload = json.dumps(data, separators=(",", ":"))
    path.write_text(f"window.PRICING_DATA = {payload};\n", encoding="utf-8")


def embed_matches_catalog(catalog_path: Path = DATA_PATH, embed_path: Path = EMBED_PATH) -> bool:
    catalog = load_catalog(catalog_path)
    expected = json.dumps(catalog, separators=(",", ":"))
    text = embed_path.read_text(encoding="utf-8")
    prefix = "window.PRICING_DATA = "
    if not text.startswith(prefix):
        return False
    actual = text[len(prefix) :].rstrip().rstrip(";")
    return actual == expected


def write_catalog(data: dict, path: Path = DATA_PATH) -> None:
    normalize_catalog(data)
    validate_catalog(data)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    write_embed_js(data)


def update_scrape_manifest(
    data: dict,
    *,
    warnings: list[str] | None = None,
) -> None:
    if warnings is not None:
        existing = list(data.get("scrape", {}).get("warnings", []))
        for w in warnings:
            if w not in existing:
                existing.append(w)
        data.setdefault("scrape", {})["warnings"] = existing
    stats = compute_coverage_stats(data)
    data["scrape"] = {**stats, "warnings": data.get("scrape", {}).get("warnings", [])}
    if stats["price_coverage_pct"] < 50:
        msg = (
            f"{stats['models_with_prices']}/{stats['models_in_catalog']} models have "
            "on-demand list prices; preview and marketplace models may lack public pricing."
        )
        if msg not in data["scrape"]["warnings"]:
            data["scrape"]["warnings"].append(msg)
