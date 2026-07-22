from bedrock_offer import (
    _parse_token_usagetype,
    extract_offer_prices,
    merge_bedrock_offer_into_catalog,
)
from offer_key_map import offer_keys_for_model, variant_base_candidates


def test_parse_token_usagetype_sonic():
    parsed = _parse_token_usagetype("USE1-NovaSonic2.0-text-input-tokens")
    assert parsed == ("NovaSonic2.0", "text-input-tokens")


def test_parse_token_usagetype_mantle_standard():
    parsed = _parse_token_usagetype(
        "USE1-qwen.qwen3-coder-480b-a35b-instruct-mantle-input-tokens-standard"
    )
    assert parsed == ("qwen.qwen3-coder-480b-a35b-instruct-mantle", "input-tokens")


def test_offer_keys_for_nova_lite():
    keys = offer_keys_for_model("amazon.nova-lite-v1:0", pricing_type="token")
    assert "NovaLite" in keys


def test_variant_base_candidates_embed():
    candidates = variant_base_candidates("cohere.embed-english-v3:0:512")
    assert "cohere.embed-english-v3" in candidates


def test_extract_offer_prices_1m_tokens_not_scaled():
    """1M token SKUs must not be multiplied by 1000."""
    index = {
        "products": {
            "p1": {
                "attributes": {
                    "usagetype": "USE1-xai.grok-4.3-mantle-output-tokens",
                }
            },
        },
        "terms": {
            "OnDemand": {
                "p1": {
                    "t1": {
                        "priceDimensions": {
                            "d1": {
                                "pricePerUnit": {"USD": "1.25"},
                                "unit": "1M tokens",
                                "description": "USD 1.25 per 1M tokens",
                            }
                        }
                    }
                },
            }
        },
    }
    prices = extract_offer_prices(index)
    assert prices["xai.grok-4.3-mantle"]["output_per_1m"] == 1.25


def test_merge_bedrock_offer_fixture():
    index = {
        "products": {
            "p1": {
                "attributes": {
                    "usagetype": "USE1-NovaLite-input-tokens",
                }
            },
            "p2": {
                "attributes": {
                    "usagetype": "USE1-NovaLite-output-tokens",
                }
            },
        },
        "terms": {
            "OnDemand": {
                "p1": {
                    "t1": {
                        "priceDimensions": {
                            "d1": {
                                "pricePerUnit": {"USD": "0.00006"},
                                "unit": "1K tokens",
                                "description": "$0.00006 per 1K input tokens",
                            }
                        }
                    }
                },
                "p2": {
                    "t1": {
                        "priceDimensions": {
                            "d2": {
                                "pricePerUnit": {"USD": "0.00024"},
                                "unit": "1K tokens",
                                "description": "$0.00024 per 1K output tokens",
                            }
                        }
                    }
                },
            }
        },
    }
    catalog = {
        "models": [
            {
                "model_id": "amazon.nova-lite-v1:0",
                "display_name": "Nova Lite",
                "pricing_type": "token",
                "pricing_source": "manual",
                "on_demand": {
                    "input_per_1m": None,
                    "output_per_1m": None,
                    "standard_per_image": None,
                    "premium_per_image": None,
                },
            }
        ]
    }
    prices = extract_offer_prices(index)
    assert prices["NovaLite"]["input_per_1m"] == 0.06
    assert prices["NovaLite"]["output_per_1m"] == 0.24
    updated, matched, _ = merge_bedrock_offer_into_catalog(catalog, index=index)
    assert matched == 1
    assert updated == 1
    assert catalog["models"][0]["pricing_source"] == "price_list"
