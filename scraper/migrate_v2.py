#!/usr/bin/env python3
"""One-off migration: schema v1 -> v2 with pricing_source and scrape manifest."""

from __future__ import annotations

from datetime import date

from catalog_io import load_catalog, normalize_catalog, write_catalog

OLD_UPDATED = "2026-05-26"


def main() -> None:
    data = load_catalog()
    old_meta = data.get("meta", {})
    last = old_meta.get("last_updated") or old_meta.get("pricing_updated_at") or OLD_UPDATED

    data["meta"] = {
        "schema_version": "2",
        "source": old_meta.get("source", "https://aws.amazon.com/bedrock/pricing/"),
        "last_scraped_at": last,
        "pricing_updated_at": last,
        "parser_version": "2",
    }

    for model in data["models"]:
        model["pricing_source"] = "auto" if model.get("pricing_source") else "manual"

    auto = sum(1 for m in data["models"] if m["pricing_source"] == "auto")
    total = len(data["models"])
    data["scrape"] = {
        "models_matched": auto,
        "models_in_catalog": total,
        "coverage_pct": round(100 * auto / total) if total else 0,
        "warnings": [],
    }

    normalize_catalog(data)
    write_catalog(data)
    print(f"Migrated {total} models to schema v2.")


if __name__ == "__main__":
    main()
