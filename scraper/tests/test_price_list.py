from price_list import (
    build_name_lookup,
    clean_service_name,
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
                    "term1": {
                        "priceDimensions": {
                            "dim1": {"pricePerUnit": {"USD": "3.0"}}
                        }
                    }
                },
                "prod-out": {
                    "term1": {
                        "priceDimensions": {
                            "dim1": {"pricePerUnit": {"USD": "15.0"}}
                        }
                    }
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
                    "input_per_1k": None,
                    "output_per_1k": None,
                },
            }
        ]
    }
    prices = extract_token_prices_from_index(index, catalog)
    assert prices["anthropic.claude-3-5-sonnet-20240620-v1:0"]["input_per_1k"] == 0.003
    assert prices["anthropic.claude-3-5-sonnet-20240620-v1:0"]["output_per_1k"] == 0.015

    updated, matched, _warnings = merge_price_list_into_catalog(
        catalog, index=index, region="us-east-1"
    )
    assert updated == 1
    assert matched == 1
    assert catalog["models"][0]["pricing_source"] == "auto"


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
                    "term1": {
                        "priceDimensions": {
                            "dim1": {"pricePerUnit": {"USD": "15.0"}}
                        }
                    }
                },
                "prod-out": {
                    "term1": {
                        "priceDimensions": {
                            "dim1": {"pricePerUnit": {"USD": "75.0"}}
                        }
                    }
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
                "on_demand": {"input_per_1k": 0.015, "output_per_1k": 0.075},
            }
        ]
    }
    updated, matched, _warnings = merge_price_list_into_catalog(
        catalog, index=index, region="us-east-1"
    )
    assert matched == 1
    assert updated == 0
    assert catalog["models"][0]["pricing_source"] == "auto"
