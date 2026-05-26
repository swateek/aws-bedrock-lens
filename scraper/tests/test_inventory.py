from inventory import infer_pricing_type, inventory_record_to_catalog_entry, merge_inventory_into_catalog


def test_infer_pricing_type_embedding():
    assert infer_pricing_type("cohere.embed-english-v3", ["TEXT"], ["EMBEDDING"]) == "embedding"


def test_infer_pricing_type_image():
    assert infer_pricing_type("amazon.titan-image-generator-v2:0", ["TEXT"], ["IMAGE"]) == "image"


def test_merge_preserves_existing_prices():
    catalog = {
        "meta": {},
        "scrape": {},
        "models": [
            {
                "model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
                "display_name": "Old Name",
                "provider": "Anthropic",
                "pricing_type": "token",
                "pricing_source": "manual",
                "regions": ["us-east-1"],
                "on_demand": {"input_per_1m": 3.0, "output_per_1m": 15.0},
                "context_window": 200000,
                "modalities": ["text"],
                "notes": None,
            }
        ],
    }
    inventory = [
        {
            "modelId": "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "modelName": "Claude 3.5 Sonnet v2",
            "providerName": "Anthropic",
            "inputModalities": ["TEXT"],
            "outputModalities": ["TEXT"],
            "regions": ["us-east-1", "us-west-2"],
        },
        {
            "modelId": "openai.gpt-oss-120b-1:0",
            "modelName": "GPT OSS 120B",
            "providerName": "OpenAI",
            "inputModalities": ["TEXT"],
            "outputModalities": ["TEXT"],
            "regions": ["us-east-1"],
        },
    ]
    added, _updated, _warnings = merge_inventory_into_catalog(catalog, inventory)
    by_id = {m["model_id"]: m for m in catalog["models"]}
    assert added == 1
    assert by_id["anthropic.claude-3-5-sonnet-20241022-v2:0"]["on_demand"]["input_per_1m"] == 3.0
    assert by_id["openai.gpt-oss-120b-1:0"]["provider"] == "OpenAI"
    assert by_id["openai.gpt-oss-120b-1:0"]["on_demand"]["input_per_1m"] is None


def test_inventory_record_to_catalog_entry():
    entry = inventory_record_to_catalog_entry(
        {
            "modelId": "openai.gpt-oss-20b-1:0",
            "modelName": "GPT OSS 20B",
            "providerName": "OpenAI",
            "inputModalities": ["TEXT"],
            "outputModalities": ["TEXT"],
            "regions": ["us-east-1"],
            "modelLifecycle": {"status": "ACTIVE"},
        }
    )
    assert entry["model_id"] == "openai.gpt-oss-20b-1:0"
    assert entry["availability"] == "ga"
