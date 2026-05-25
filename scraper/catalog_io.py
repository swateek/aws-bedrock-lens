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
PARSER_VERSION = "2"


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
    """Stable hash of all on_demand pricing fields."""
    payload = {
        m["model_id"]: m.get("on_demand", {}) for m in sorted(models, key=lambda x: x["model_id"])
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
    if pricing_type == "image":
        return {
            "input_per_1k": None,
            "output_per_1k": None,
            "standard_per_image": None,
            "premium_per_image": None,
        }
    if pricing_type == "embedding":
        return {
            "input_per_1k": None,
            "output_per_1k": None,
            "standard_per_image": None,
            "premium_per_image": None,
        }
    return {
        "input_per_1k": None,
        "output_per_1k": None,
        "standard_per_image": None,
        "premium_per_image": None,
    }


def normalize_on_demand(model: dict) -> dict:
    base = empty_on_demand(model["pricing_type"])
    incoming = model.get("on_demand") or {}
    for key in base:
        if key in incoming:
            base[key] = incoming[key]
    return base


def model_has_price(model: dict) -> bool:
    """True if any on_demand field has a numeric price."""
    od = model.get("on_demand") or {}
    for key in ("input_per_1k", "output_per_1k", "standard_per_image", "premium_per_image"):
        val = od.get(key)
        if val is not None and isinstance(val, (int, float)):
            return True
    return False


def compute_coverage_stats(catalog: dict) -> dict[str, Any]:
    models = catalog.get("models", [])
    total = len(models)
    with_prices = sum(1 for m in models if model_has_price(m))
    auto_count = sum(1 for m in models if m.get("pricing_source") == "auto")
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


def normalize_catalog(data: dict) -> dict:
    """Ensure v2 shape and consistent on_demand keys."""
    meta = data.setdefault("meta", {})
    meta.setdefault("schema_version", "2.1")
    meta.setdefault("source", PRICING_URL)
    meta.setdefault("parser_version", PARSER_VERSION)
    meta.setdefault("last_scraped_at", None)
    meta.setdefault("pricing_updated_at", None)
    meta.setdefault("last_inventory_sync_at", None)
    meta.setdefault("models_known_to_aws", None)
    meta.setdefault("last_price_list_at", None)
    meta.setdefault("price_list_region", "us-east-1")
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
        model.setdefault("pricing_source", "manual")
        model.setdefault("availability", "ga")
        model.setdefault("alternate_ids", [])
        model["on_demand"] = normalize_on_demand(model)

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
