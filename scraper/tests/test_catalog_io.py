import json

from catalog_io import (
    catalogs_meaningfully_differ,
    normalize_catalog,
    normalize_on_demand,
    pricing_fingerprint,
    validate_catalog,
)


def test_fingerprint_changes_when_price_changes():
    models = [
        {
            "model_id": "a",
            "pricing_type": "token",
            "on_demand": {"input_per_1k": 0.001, "output_per_1k": 0.002},
        }
    ]
    h1 = pricing_fingerprint(models)
    models[0]["on_demand"]["input_per_1k"] = 0.002
    h2 = pricing_fingerprint(models)
    assert h1 != h2


def test_normalize_on_demand_token_shape():
    model = {
        "pricing_type": "token",
        "on_demand": {"input_per_1k": 0.001, "output_per_1k": 0.002},
    }
    od = normalize_on_demand(model)
    assert od["standard_per_image"] is None
    assert od["input_per_1k"] == 0.001


def test_schema_accepts_minimal_v2_catalog():
    data = {
        "meta": {
            "schema_version": "2.1",
            "source": "https://aws.amazon.com/bedrock/pricing/",
            "last_scraped_at": "2026-01-01",
            "pricing_updated_at": "2026-01-01",
            "parser_version": "2",
            "last_inventory_sync_at": "2026-01-01",
            "models_known_to_aws": 1,
        },
        "scrape": {
            "models_matched": 0,
            "models_in_catalog": 1,
            "models_with_prices": 1,
            "models_known_to_aws": 1,
            "coverage_pct": 0,
            "price_coverage_pct": 100,
            "inventory_coverage_pct": 100,
            "warnings": [],
        },
        "models": [
            {
                "model_id": "test.model:1",
                "display_name": "Test",
                "provider": "Test",
                "pricing_type": "token",
                "pricing_source": "manual",
                "regions": ["us-east-1"],
                "on_demand": {
                    "input_per_1k": 0.001,
                    "output_per_1k": 0.002,
                    "standard_per_image": None,
                    "premium_per_image": None,
                },
                "context_window": 8192,
                "modalities": ["text"],
                "notes": None,
                "availability": "ga",
                "alternate_ids": [],
            }
        ],
    }
    normalize_catalog(data)
    validate_catalog(data)


def test_model_has_price_and_coverage_stats():
    from catalog_io import compute_coverage_stats, model_has_price

    model = {
        "pricing_type": "token",
        "on_demand": {"input_per_1k": 0.001, "output_per_1k": None},
    }
    assert model_has_price(model)
    stats = compute_coverage_stats(
        {
            "meta": {"models_known_to_aws": 10},
            "models": [model, {"pricing_type": "token", "on_demand": {}}],
        }
    )
    assert stats["models_with_prices"] == 1
    assert stats["price_coverage_pct"] == 50


def test_meaningful_diff_ignores_last_scraped_only():
    base = {
        "meta": {
            "schema_version": "2",
            "source": "https://aws.amazon.com/bedrock/pricing/",
            "last_scraped_at": "2026-01-01",
            "pricing_updated_at": "2026-01-01",
            "parser_version": "2",
        },
        "scrape": {
            "models_matched": 1,
            "models_in_catalog": 1,
            "coverage_pct": 100,
            "warnings": [],
        },
        "models": [
            {
                "model_id": "test.model:1",
                "display_name": "Test",
                "provider": "Test",
                "pricing_type": "token",
                "pricing_source": "manual",
                "regions": ["us-east-1"],
                "on_demand": {
                    "input_per_1k": 0.001,
                    "output_per_1k": 0.002,
                    "standard_per_image": None,
                    "premium_per_image": None,
                },
                "context_window": 8192,
                "modalities": ["text"],
                "notes": None,
            }
        ],
    }
    before = json.loads(json.dumps(base))
    after = json.loads(json.dumps(base))
    after["meta"]["last_scraped_at"] = "2026-06-01"
    assert not catalogs_meaningfully_differ(before, after)


def test_meaningful_diff_detects_price_change():
    before = {
        "meta": {
            "schema_version": "2",
            "source": "https://aws.amazon.com/bedrock/pricing/",
            "last_scraped_at": "2026-01-01",
            "pricing_updated_at": "2026-01-01",
            "parser_version": "2",
        },
        "scrape": {
            "models_matched": 0,
            "models_in_catalog": 1,
            "coverage_pct": 0,
            "warnings": [],
        },
        "models": [
            {
                "model_id": "test.model:1",
                "display_name": "Test",
                "provider": "Test",
                "pricing_type": "token",
                "pricing_source": "manual",
                "regions": ["us-east-1"],
                "on_demand": {
                    "input_per_1k": 0.001,
                    "output_per_1k": 0.002,
                    "standard_per_image": None,
                    "premium_per_image": None,
                },
                "context_window": 8192,
                "modalities": ["text"],
                "notes": None,
            }
        ],
    }
    after = json.loads(json.dumps(before))
    after["models"][0]["on_demand"]["input_per_1k"] = 0.002
    assert catalogs_meaningfully_differ(before, after)
