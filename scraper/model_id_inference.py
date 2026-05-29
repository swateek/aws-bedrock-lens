"""Infer Bedrock model_id from AWS Price List servicenames or marketing display names."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

OVERRIDES_PATH = Path(__file__).resolve().parent / "sku_overrides.json"
_SERVICE_SUFFIX_RE = re.compile(r"\s*\(Amazon Bedrock Edition\)\s*$", re.IGNORECASE)


def _load_overrides() -> dict[str, str]:
    if not OVERRIDES_PATH.exists():
        return {}
    data = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    return dict(data.get("service_name_to_model_id", {}))


def clean_service_name(name: str) -> str:
    return _SERVICE_SUFFIX_RE.sub("", name).strip()


def _normalize_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


# Price List servicenames that are not modern foundation model_id targets.
LEGACY_SERVICE_NAMES: frozenset[str] = frozenset(
    {
        "Claude",
        "Claude (100K)",
        "Claude Instant",
        "Claude Instant (100K)",
        "Jurassic-2 Mid",
        "Jurassic-2 Ultra",
    }
)

_PROVIDER_FROM_PREFIX: dict[str, str] = {
    "anthropic.": "Anthropic",
    "meta.": "Meta",
    "amazon.": "Amazon",
    "cohere.": "Cohere",
    "mistral.": "Mistral AI",
    "openai.": "OpenAI",
    "deepseek.": "DeepSeek",
    "google.": "Google",
    "ai21.": "AI21 Labs",
    "stability.": "Stability AI",
    "twelvelabs.": "TwelveLabs",
    "writer.": "Writer",
    "nvidia.": "NVIDIA",
    "qwen.": "Qwen",
    "minimax.": "MiniMax",
    "moonshot.": "Moonshot AI",
    "moonshotai.": "Moonshot AI",
    "luma.": "Luma AI",
    "zai.": "Z.AI",
}

# (compiled regex, builder receiving match -> model_id or None)
_InferenceRule = tuple[re.Pattern[str], Callable[[re.Match[str]], str | None]]

_ANTHROPIC_TIER_VERSION = re.compile(
    r"^Claude (Opus|Sonnet|Haiku) (\d+)\.(\d+)$",
    re.IGNORECASE,
)
_LLAMA_INSTRUCT = re.compile(
    r"^Llama (\d)\.(\d+) (\d+[bB]) Instruct$",
    re.IGNORECASE,
)
_JAMBA = re.compile(r"^Jamba (\d)\.(\d+) (Large|Mini)$", re.IGNORECASE)
_PALMYRA = re.compile(r"^Palmyra (X\d+)$", re.IGNORECASE)
_STABLE_DIFFUSION = re.compile(
    r"^Stable Diffusion (\d(?:\.\d)?) (Large) v(\d+\.\d+)$",
    re.IGNORECASE,
)
_STABLE_IMAGE = re.compile(r"^Stable Image (Core|Ultra)$", re.IGNORECASE)
_TWELVELABS_MARENGO = re.compile(
    r"^TwelveLabs Marengo Embed (\d+\.\d+)$",
    re.IGNORECASE,
)
_TWELVELABS_PEGASUS = re.compile(
    r"^TwelveLabs Pegasus (\d+\.\d+)$",
    re.IGNORECASE,
)
_COHERE_COMMAND_R = re.compile(r"^Cohere Command R\+?$", re.IGNORECASE)
_COHERE_EMBED_EN = re.compile(r"^Cohere Embed 3 Model - English$", re.IGNORECASE)
_COHERE_EMBED_MULTI = re.compile(
    r"^Cohere Embed Model 3 - Multilingual$",
    re.IGNORECASE,
)
_COHERE_EMBED_4 = re.compile(r"^Cohere Embed 4 Model$", re.IGNORECASE)
_COHERE_RERANK = re.compile(r"^Cohere Rerank v(\d+\.\d+)$", re.IGNORECASE)
_COHERE_COMMAND = re.compile(r"^Cohere Generate Model - Command(-Light)?$", re.IGNORECASE)


def _anthropic_tier_version(match: re.Match[str]) -> str:
    tier = match.group(1).lower()
    return f"anthropic.claude-{tier}-{match.group(2)}-{match.group(3)}"


def _llama_instruct(match: re.Match[str]) -> str:
    size = match.group(3).lower()
    return f"meta.llama{match.group(1)}-{match.group(2)}-{size}-instruct-v1:0"


def _jamba(match: re.Match[str]) -> str:
    size = match.group(3).lower()
    return f"ai21.jamba-{match.group(1)}-{match.group(2)}-{size}-v1:0"


def _palmyra(match: re.Match[str]) -> str:
    return f"writer.palmyra-{match.group(1).lower()}-v1:0"


def _stable_diffusion(match: re.Match[str]) -> str:
    ver = match.group(1).replace(".", "")
    if ver == "35":
        return "stability.sd3-5-large-v1:0"
    return "stability.sd3-large-v1:0"


def _stable_image(match: re.Match[str]) -> str:
    kind = match.group(1).lower()
    if kind == "core":
        return "stability.stable-image-core-v1:1"
    return "stability.stable-image-ultra-v1:1"


def _twelvelabs_marengo(match: re.Match[str]) -> str:
    ver = match.group(1).replace(".", "-")
    return f"twelvelabs.marengo-embed-{ver}-v1:0"


def _twelvelabs_pegasus(match: re.Match[str]) -> str:
    ver = match.group(1).replace(".", "-")
    return f"twelvelabs.pegasus-{ver}-v1:0"


def _cohere_command_r(match: re.Match[str]) -> str:
    if match.group(0).endswith("+"):
        return "cohere.command-r-plus-v1:0"
    return "cohere.command-r-v1:0"


def _cohere_rerank(match: re.Match[str]) -> str:
    ver = match.group(1).replace(".", "-")
    return f"cohere.rerank-v{ver}:0"


def _cohere_command(match: re.Match[str]) -> str:
    if match.group(1):
        return "cohere.command-light-text-v14"
    return "cohere.command-text-v14"


_INFERENCE_RULES: list[_InferenceRule] = [
    (_ANTHROPIC_TIER_VERSION, _anthropic_tier_version),
    (_LLAMA_INSTRUCT, _llama_instruct),
    (_JAMBA, _jamba),
    (_PALMYRA, _palmyra),
    (_STABLE_DIFFUSION, _stable_diffusion),
    (_STABLE_IMAGE, _stable_image),
    (_TWELVELABS_MARENGO, _twelvelabs_marengo),
    (_TWELVELABS_PEGASUS, _twelvelabs_pegasus),
    (_COHERE_COMMAND_R, _cohere_command_r),
    (_COHERE_EMBED_EN, lambda _m: "cohere.embed-english-v3"),
    (_COHERE_EMBED_MULTI, lambda _m: "cohere.embed-multilingual-v3"),
    (_COHERE_EMBED_4, lambda _m: "cohere.embed-v4:0"),
    (_COHERE_RERANK, _cohere_rerank),
    (_COHERE_COMMAND, _cohere_command),
]


def is_legacy_service_name(name: str) -> bool:
    return clean_service_name(name) in LEGACY_SERVICE_NAMES


def build_name_lookup(catalog: dict | None) -> dict[str, str]:
    """Map normalized display names, overrides, and model_id to model_id."""
    lookup: dict[str, str] = {}
    for override_name, model_id in _load_overrides().items():
        lookup[_normalize_key(override_name)] = model_id
    if catalog:
        for model in catalog.get("models", []):
            model_id = model["model_id"]
            for name in (model.get("display_name"), model_id.split(".")[-1]):
                if name:
                    lookup[_normalize_key(name)] = model_id
            lookup[_normalize_key(model_id)] = model_id
    return lookup


def lookup_model_id(name: str, catalog: dict | None) -> str | None:
    """Resolve via overrides and catalog display names."""
    clean = clean_service_name(name)
    lookup = build_name_lookup(catalog)
    return lookup.get(_normalize_key(clean))


def infer_model_id_from_rules(name: str) -> str | None:
    """Apply provider slug rules for names not in catalog/overrides."""
    clean = clean_service_name(name)
    for pattern, builder in _INFERENCE_RULES:
        match = pattern.match(clean)
        if match:
            model_id = builder(match)
            if model_id:
                return model_id
    return None


def infer_model_id(name: str, catalog: dict | None = None) -> str | None:
    """Resolve model_id: overrides/catalog first, then provider inference rules."""
    if is_legacy_service_name(name):
        return None
    found = lookup_model_id(name, catalog)
    if found:
        return found
    return infer_model_id_from_rules(name)


def display_name_for_model_id(model_id: str) -> str:
    """Best-effort display name from overrides or model_id slug."""
    for label, mid in _load_overrides().items():
        if mid == model_id:
            return label
    slug = model_id.split(".", 1)[-1] if "." in model_id else model_id
    slug = re.sub(r"-v\d+:.*$", "", slug)
    slug = re.sub(r":.*$", "", slug)
    parts = slug.replace("-", " ").split()
    return " ".join(p.capitalize() if not re.fullmatch(r"v?\d+(\.\d+)?", p) else p for p in parts)


def provider_for_model_id(model_id: str) -> str:
    for prefix, label in _PROVIDER_FROM_PREFIX.items():
        if model_id.startswith(prefix):
            return label
    return "Unknown"
