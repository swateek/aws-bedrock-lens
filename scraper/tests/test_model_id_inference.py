from model_id_inference import (
    infer_model_id,
    infer_model_id_from_rules,
    is_legacy_service_name,
    lookup_model_id,
)


def test_infer_opus_48_from_rules():
    assert infer_model_id_from_rules("Claude Opus 4.8") == "anthropic.claude-opus-4-8"
    assert infer_model_id("Claude Opus 4.8 (Amazon Bedrock Edition)") == "anthropic.claude-opus-4-8"


def test_legacy_claude_instant_not_inferred():
    assert is_legacy_service_name("Claude Instant")
    assert infer_model_id("Claude Instant") is None


def test_override_takes_precedence_over_rules():
    catalog = {
        "models": [
            {
                "model_id": "anthropic.claude-3-5-sonnet-20240620-v1:0",
                "display_name": "Claude 3.5 Sonnet",
            }
        ]
    }
    assert (
        lookup_model_id("Claude 3.5 Sonnet (Amazon Bedrock Edition)", catalog)
        == "anthropic.claude-3-5-sonnet-20240620-v1:0"
    )


def test_infer_llama_instruct():
    assert infer_model_id_from_rules("Llama 3.1 70B Instruct") == "meta.llama3-1-70b-instruct-v1:0"
