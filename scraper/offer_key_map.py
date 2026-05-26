"""Map catalog model_id values to AmazonBedrock offer usage-type keys."""

from __future__ import annotations

import re

# pylint: disable=too-many-return-statements


def variant_base_id(model_id: str) -> str:
    """Strip context / modality suffixes (e.g. :24k, :128k, :mm) for price inheritance."""
    parts = model_id.split(":")
    while len(parts) > 2:
        tail = parts[-1]
        if tail in ("mm",) or re.fullmatch(r"\d+k", tail) or tail.isdigit():
            parts.pop()
        else:
            break
    return ":".join(parts)


def variant_base_candidates(model_id: str) -> list[str]:
    """Model IDs to try when inheriting prices for context / dimension variants."""
    seen: set[str] = set()
    candidates: list[str] = []

    def add(mid: str) -> None:
        if mid and mid not in seen:
            seen.add(mid)
            candidates.append(mid)

    add(model_id)
    add(variant_base_id(model_id))
    base = variant_base_id(model_id)
    if ":0" in base:
        add(base.rsplit(":0", 1)[0])
    if ":2:" in base:
        add(base.split(":2:")[0])
    return candidates


def offer_keys_for_model(
    model_id: str, *, pricing_type: str, display_name: str | None = None
) -> list[str]:
    """Return AmazonBedrock offer keys (USE1-{key}-...) that apply to this model."""
    keys: list[str] = []

    if model_id.startswith("amazon.nova-2-lite"):
        keys.append("Nova2.0Lite")
    elif model_id.startswith("amazon.nova-2-sonic"):
        keys.append("NovaSonic2.0")
    elif model_id.startswith("amazon.nova-lite"):
        keys.append("NovaLite")
    elif model_id.startswith("amazon.nova-micro"):
        keys.append("NovaMicro")
    elif model_id.startswith("amazon.nova-pro"):
        keys.append("NovaPro")
    elif model_id.startswith("amazon.nova-premier"):
        keys.append("NovaPremier")
    elif model_id.startswith("amazon.nova-sonic"):
        keys.append("NovaSonic")
    elif model_id.startswith("amazon.nova-canvas"):
        keys.append("NovaCanvas")
    elif model_id.startswith("amazon.nova-reel"):
        keys.append("NovaReel")
    elif model_id.startswith("amazon.nova-2-multimodal-embeddings"):
        keys.append("NovaMultiModalEmbeddings")
    elif model_id.startswith("amazon.titan-embed-text-v2"):
        keys.append("TitanEmbeddingV2-Text")
    elif model_id.startswith("amazon.titan-embed-g1-text") or model_id.startswith(
        "amazon.titan-embed-text-v1"
    ):
        keys.append("TitanEmbeddingsG1-Text")
    elif model_id.startswith("amazon.titan-embed-image"):
        keys.append("TitanEmbeddingsG1-Image")
    elif model_id.startswith("amazon.titan-image-generator-v1"):
        keys.append("TitanImageGeneratorG1")
    elif model_id.startswith("amazon.titan-image-generator-v2"):
        keys.append("TitanImageGeneratorV2")
    elif model_id.startswith("meta.llama3-1-405b"):
        keys.append("Llama3-1-405B")  # batch-only in offer; may stay unpriced
    elif model_id.startswith("meta.llama3-1-70b"):
        keys.append("Llama3-1-70B")
    elif model_id.startswith("meta.llama3-1-8b"):
        keys.append("Llama3-1-8B")
    elif model_id.startswith("meta.llama3-2-11b"):
        keys.append("Llama3-2-11B")
    elif model_id.startswith("meta.llama3-2-1b"):
        keys.append("Llama3-2-1B")
    elif model_id.startswith("meta.llama3-2-3b"):
        keys.append("Llama3-2-3B")
    elif model_id.startswith("meta.llama3-2-90b"):
        keys.append("Llama3-2-90B")
    elif model_id.startswith("meta.llama3-3-70b"):
        keys.append("Llama3-3-70B")
    elif model_id.startswith("meta.llama3-8b"):
        keys.append("Llama3-8B")
    elif model_id.startswith("meta.llama4-maverick"):
        keys.append("Llama4-Maverick-17B")
    elif model_id.startswith("meta.llama4-scout"):
        keys.append("Llama4-Scout-17B")
    elif model_id.startswith("google.gemma-3-12b"):
        keys.append("Gemma-3-12B-IT")
    elif model_id.startswith("google.gemma-3-27b"):
        keys.append("Gemma-3-27B-IT")
    elif model_id.startswith("google.gemma-3-4b"):
        keys.append("Gemma-3-4B-IT")
    elif model_id.startswith("deepseek.r1"):
        keys.append("DeepSeek-R1")
    elif model_id.startswith("cohere.command-r-plus"):
        keys.append("Cohere Command R+")  # not in AmazonBedrock; FM only
    elif model_id.startswith("mistral.magistral-small"):
        keys.append("Magistral-Small-2509")
    elif model_id.startswith("mistral.ministral-3-3b"):
        keys.append("Ministral-3-3b-Instruct")
    elif model_id.startswith("mistral.ministral-3-8b"):
        keys.append("Ministral-3-8b-Instruct")
    elif model_id.startswith("mistral.ministral-3-14b"):
        keys.append("Ministral-3-14b-Instruct")
    elif model_id.startswith("mistral.mistral-large-2402"):
        keys.append("MistralLarge")
    elif model_id.startswith("mistral.mistral-small-2402"):
        keys.append("MistralSmall")
    elif model_id.startswith("mistral.mixtral-8x7b"):
        keys.append("Mixtral8x7B")
    elif model_id.startswith("mistral.pixtral-large"):
        keys.append("PixtralLarge2502")
    elif model_id.startswith("mistral.voxtral-mini-3b"):
        keys.append("Voxtral-Mini-3B-2507")
    elif model_id.startswith("mistral.voxtral-small"):
        keys.append("Voxtral-Mini-24B-2507")
    elif model_id.startswith("nvidia.nemotron-nano-12b"):
        keys.append("Nemotron-Nano-12B-V2-VL-BF16")
    elif model_id.startswith("nvidia.nemotron-nano-3-30b"):
        keys.append("Nemotron-Nano-3-30B")
    elif model_id.startswith("nvidia.nemotron-nano-9b"):
        keys.append("Nemotron-Nano-9B-V2")
    elif model_id.startswith("qwen.qwen3-32b"):
        keys.append("Qwen3-32B")
    elif model_id.startswith("qwen.qwen3-coder-30b"):
        keys.append("Qwen3Coder-30B-A3B")
    elif model_id.startswith("qwen.qwen3-coder-480b"):
        keys.append("qwen.qwen3-coder-480b-a35b-instruct-mantle")
    elif model_id.startswith("writer.palmyra-vision"):
        keys.append("writer.palmyra-vision-7b")
    elif model_id.startswith("anthropic.claude-3-haiku-20240307-v1:0") and ":200k" not in model_id:
        keys.append("Claude3Haiku")
    elif (
        model_id.startswith("anthropic.claude-3-sonnet-20240229-v1:0")
        and ":200k" not in model_id
        and ":28k" not in model_id
    ):
        keys.append("Claude3Sonnet")

    # Models whose offer key equals the Bedrock model slug (no provider prefix).
    slug_by_model_id = {
        "deepseek.v3.2": "deepseek.v3.2",
        "openai.gpt-oss-120b-1:0": "gpt-oss-120b",
        "openai.gpt-oss-20b-1:0": "gpt-oss-20b",
        "minimax.minimax-m2.1": "minimax.minimax-m2.1",
        "minimax.minimax-m2.5": "minimax.minimax-m2.5",
        "mistral.devstral-2-123b": "mistral.devstral-2-123b",
        "moonshotai.kimi-k2.5": "moonshotai.kimi-k2.5",
        "nvidia.nemotron-super-3-120b": "nvidia.nemotron-super-3-120b",
        "qwen.qwen3-coder-next": "qwen.qwen3-coder-next",
        "zai.glm-4.7": "zai.glm-4.7",
        "zai.glm-4.7-flash": "zai.glm-4.7-flash",
        "zai.glm-5": "zai.glm5",
    }
    if model_id in slug_by_model_id:
        keys.append(slug_by_model_id[model_id])

    # Remove keys that only exist in FoundationModels (handled there).
    fm_only = {"Cohere Command R+"}
    keys = [k for k in keys if k not in fm_only]

    return list(dict.fromkeys(keys))


def build_model_to_offer_keys(catalog: dict) -> dict[str, list[str]]:
    """Precompute model_id -> offer keys for all catalog models."""
    out: dict[str, list[str]] = {}
    for model in catalog.get("models", []):
        keys = offer_keys_for_model(
            model["model_id"],
            pricing_type=model.get("pricing_type", "token"),
            display_name=model.get("display_name"),
        )
        if keys:
            out[model["model_id"]] = keys
    return out
