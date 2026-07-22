"""Tests for SKU tier classification and multi-region fact extraction."""

from sku_facts import classify_tier, extract_fm_facts


def test_classify_tier_on_demand():
    assert classify_tier("USE1_InputTokenCount-Units") == "on_demand"


def test_classify_tier_batch_and_global():
    assert classify_tier("USE1-Claude-batch-input-tokens") == "batch"
    assert classify_tier("USE1-Claude-global-input-tokens") == "on_demand_global"
    assert classify_tier("USE1-Claude-batch-global-input-tokens") == "batch_global"


def test_classify_tier_cache_flex_priority():
    assert classify_tier("USE1-Claude-cache-read-input-tokens") == "cache"
    assert classify_tier("USE1-Claude-flex-input-tokens") == "flex"
    assert classify_tier("USE1-Claude-priority-input-tokens") == "priority"


def test_classify_tier_skips_provisioned():
    assert classify_tier("USE1-Claude-provisioned-input-tokens") is None


def test_extract_fm_facts_multi_region():
    index = {
        "products": {
            "a": {
                "attributes": {
                    "servicename": "Claude",
                    "usagetype": "USE1_InputTokenCount-Units",
                    "regionCode": "us-east-1",
                }
            },
            "b": {
                "attributes": {
                    "servicename": "Claude",
                    "usagetype": "USW2_InputTokenCount-Units",
                    "regionCode": "us-west-2",
                }
            },
            "c": {
                "attributes": {
                    "servicename": "Claude",
                    "usagetype": "USE1-Claude-batch-InputTokenCount-Units",
                    "regionCode": "us-east-1",
                }
            },
        },
        "terms": {
            "OnDemand": {
                "a": {
                    "t": {
                        "priceDimensions": {
                            "d": {
                                "pricePerUnit": {"USD": "3.0"},
                                "unit": "Units",
                                "description": "Price per 1 million input tokens",
                            }
                        }
                    }
                },
                "b": {
                    "t": {
                        "priceDimensions": {
                            "d": {
                                "pricePerUnit": {"USD": "3.2"},
                                "unit": "Units",
                                "description": "Price per 1 million input tokens",
                            }
                        }
                    }
                },
                "c": {
                    "t": {
                        "priceDimensions": {
                            "d": {
                                "pricePerUnit": {"USD": "1.5"},
                                "unit": "Units",
                                "description": "Price per 1 million input tokens",
                            }
                        }
                    }
                },
            }
        },
    }
    facts = extract_fm_facts(index)
    assert len(facts) == 3
    by_key = {(f.region, f.tier): f for f in facts}
    assert by_key[("us-east-1", "on_demand")].rate_usd == 3.0
    assert by_key[("us-west-2", "on_demand")].rate_usd == 3.2
    assert by_key[("us-east-1", "batch")].rate_usd == 1.5
