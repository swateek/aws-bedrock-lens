#!/usr/bin/env python3
"""One-off migration: on_demand input/output from per-1K to per-1M token fields."""

from __future__ import annotations

from catalog_io import load_catalog, normalize_catalog, write_catalog

# Models priced per search unit, second, etc. — rename keys only, do not scale values.
SKIP_MULTIPLY_MODEL_IDS = frozenset(
    {
        "amazon.rerank-v1:0",
        "cohere.rerank-v3-5:0",
        "luma.ray-v2:0",
    }
)


def _should_multiply(model: dict, field: str) -> bool:
    if model["model_id"] in SKIP_MULTIPLY_MODEL_IDS:
        return False
    notes = (model.get("notes") or "").lower()
    if "per second" in notes or "search unit" in notes or "per 1k tokens" in notes:
        return False
    pricing_type = model["pricing_type"]
    if pricing_type == "token":
        return field in ("input_per_1k", "output_per_1k")
    if pricing_type == "embedding" and field == "input_per_1k":
        return True
    return False


def _scale(value: float | None, multiply: bool) -> float | None:
    if value is None:
        return None
    if multiply:
        return round(value * 1000, 6)
    return value


def migrate_on_demand(model: dict) -> None:
    od = model.get("on_demand") or {}
    new_od: dict = {}
    for key, val in od.items():
        if key == "input_per_1k":
            new_key = "input_per_1m"
            new_od[new_key] = _scale(val, _should_multiply(model, key))
        elif key == "output_per_1k":
            new_key = "output_per_1m"
            new_od[new_key] = _scale(val, _should_multiply(model, key))
        else:
            new_od[key] = val
    model["on_demand"] = new_od


def main() -> None:
    data = load_catalog()
    data.setdefault("meta", {})["schema_version"] = "2.2"
    for model in data.get("models", []):
        migrate_on_demand(model)
    normalize_catalog(data)
    write_catalog(data)
    print(f"Migrated {len(data.get('models', []))} models to per-1M token fields (schema 2.2).")


if __name__ == "__main__":
    main()
