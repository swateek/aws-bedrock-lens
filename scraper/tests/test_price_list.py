from price_list import (
    build_name_lookup,
    clean_service_name,
    discover_models_from_price_list,
    extract_token_prices_from_index,
    merge_price_list_into_catalog,
    resolve_service_to_model_id,
)


def test_clean_service_name():
    assert clean_service_name("Claude 3.5 Sonnet (Amazon Bedrock Edition)") == "Claude 3.5 Sonnet"


def test_resolve_service_with_catalog():
    catalog = {
        "models": [
            {
                "model_id": "anthropic.claude-3-5-sonnet-20240620-v1:0",
                "display_name": "Claude 3.5 Sonnet",
            }
        ]
    }
    lookup = build_name_lookup(catalog)
    mid = resolve_service_to_model_id("Claude 3.5 Sonnet (Amazon Bedrock Edition)", lookup)
    assert mid == "anthropic.claude-3-5-sonnet-20240620-v1:0"


def test_extract_token_prices_fixture():
    index = {
        "products": {
            "prod-in": {
                "attributes": {
                    "servicename": "Claude 3.5 Sonnet (Amazon Bedrock Edition)",
                    "usagetype": "USE1_InputTokenCount-Units",
                }
            },
            "prod-out": {
                "attributes": {
                    "servicename": "Claude 3.5 Sonnet (Amazon Bedrock Edition)",
                    "usagetype": "USE1_OutputTokenCount-Units",
                }
            },
        },
        "terms": {
            "OnDemand": {
                "prod-in": {
                    "term1": {"priceDimensions": {"dim1": {"pricePerUnit": {"USD": "3.0"}}}}
                },
                "prod-out": {
                    "term1": {"priceDimensions": {"dim1": {"pricePerUnit": {"USD": "15.0"}}}}
                },
            }
        },
    }
    catalog = {
        "models": [
            {
                "model_id": "anthropic.claude-3-5-sonnet-20240620-v1:0",
                "display_name": "Claude 3.5 Sonnet",
                "pricing_type": "token",
                "pricing_source": "manual",
                "on_demand": {
                    "input_per_1m": None,
                    "output_per_1m": None,
                },
            }
        ]
    }
    prices = extract_token_prices_from_index(index, catalog)
    assert prices["anthropic.claude-3-5-sonnet-20240620-v1:0"]["input_per_1m"] == 3.0
    assert prices["anthropic.claude-3-5-sonnet-20240620-v1:0"]["output_per_1m"] == 15.0

    updated, matched, _warnings = merge_price_list_into_catalog(
        catalog, index=index, region="us-east-1"
    )
    assert updated == 1
    assert matched == 1
    assert catalog["models"][0]["pricing_source"] == "auto"


def test_extract_new_style_token_usagetypes():
    index = {
        "products": {
            "prod-in": {
                "attributes": {
                    "servicename": "Claude Opus 4.7 (Amazon Bedrock Edition)",
                    "usagetype": "USE1-MP:USE1_input_tokens_standard-Units",
                }
            },
            "prod-out": {
                "attributes": {
                    "servicename": "Claude Opus 4.7 (Amazon Bedrock Edition)",
                    "usagetype": "USE1-MP:USE1_output_tokens_standard-Units",
                }
            },
        },
        "terms": {
            "OnDemand": {
                "prod-in": {
                    "term1": {"priceDimensions": {"dim1": {"pricePerUnit": {"USD": "5.5"}}}}
                },
                "prod-out": {
                    "term1": {"priceDimensions": {"dim1": {"pricePerUnit": {"USD": "27.5"}}}}
                },
            }
        },
    }
    catalog = {
        "models": [
            {
                "model_id": "anthropic.claude-opus-4-7",
                "display_name": "Claude Opus 4.7",
                "pricing_type": "token",
                "pricing_source": "manual",
                "on_demand": {"input_per_1m": None, "output_per_1m": None},
            }
        ]
    }
    prices = extract_token_prices_from_index(index, catalog)
    assert prices["anthropic.claude-opus-4-7"]["input_per_1m"] == 5.5
    assert prices["anthropic.claude-opus-4-7"]["output_per_1m"] == 27.5


def test_merge_promotes_manual_when_prices_unchanged():
    index = {
        "products": {
            "prod-in": {
                "attributes": {
                    "servicename": "Claude 3 Opus (Amazon Bedrock Edition)",
                    "usagetype": "USE1_InputTokenCount-Units",
                }
            },
            "prod-out": {
                "attributes": {
                    "servicename": "Claude 3 Opus (Amazon Bedrock Edition)",
                    "usagetype": "USE1_OutputTokenCount-Units",
                }
            },
        },
        "terms": {
            "OnDemand": {
                "prod-in": {
                    "term1": {"priceDimensions": {"dim1": {"pricePerUnit": {"USD": "15.0"}}}}
                },
                "prod-out": {
                    "term1": {"priceDimensions": {"dim1": {"pricePerUnit": {"USD": "75.0"}}}}
                },
            }
        },
    }
    catalog = {
        "models": [
            {
                "model_id": "anthropic.claude-3-opus-20240229-v1:0",
                "display_name": "Claude 3 Opus",
                "pricing_type": "token",
                "pricing_source": "manual",
                "on_demand": {
                    "input_per_1m": 15.0,
                    "output_per_1m": 75.0,
                    "standard_per_image": None,
                    "premium_per_image": None,
                },
            }
        ]
    }
    updated, matched, _warnings = merge_price_list_into_catalog(
        catalog, index=index, region="us-east-1"
    )
    assert matched == 1
    assert updated == 0
    assert catalog["models"][0]["pricing_source"] == "auto"


def test_discover_provisions_opus_48_and_merges_prices():
    index = {
        "products": {
            "prod-in": {
                "attributes": {
                    "servicename": "Claude Opus 4.8 (Amazon Bedrock Edition)",
                    "usagetype": "USE1-MP:USE1_input_tokens_standard-Units",
                }
            },
            "prod-out": {
                "attributes": {
                    "servicename": "Claude Opus 4.8 (Amazon Bedrock Edition)",
                    "usagetype": "USE1-MP:USE1_output_tokens_standard-Units",
                }
            },
        },
        "terms": {
            "OnDemand": {
                "prod-in": {
                    "term1": {"priceDimensions": {"dim1": {"pricePerUnit": {"USD": "6.0"}}}}
                },
                "prod-out": {
                    "term1": {"priceDimensions": {"dim1": {"pricePerUnit": {"USD": "30.0"}}}}
                },
            }
        },
    }
    catalog: dict = {"meta": {}, "models": []}
    added, records, warnings = discover_models_from_price_list(catalog, index)
    assert added == 1
    assert records[0]["modelId"] == "anthropic.claude-opus-4-8"
    assert any("Auto-provisioned" in w for w in warnings)

    updated, matched, _merge_warnings = merge_price_list_into_catalog(
        catalog, index=index, region="us-east-1"
    )
    by_id = {m["model_id"]: m for m in catalog["models"]}
    assert "anthropic.claude-opus-4-8" in by_id
    assert by_id["anthropic.claude-opus-4-8"]["on_demand"]["input_per_1m"] == 6.0
    assert by_id["anthropic.claude-opus-4-8"]["on_demand"]["output_per_1m"] == 30.0
    assert updated == 1
    assert matched == 1
