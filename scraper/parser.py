"""Parse AWS Bedrock pricing HTML tables."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

# Legacy aliases for AWS marketing page names (supplement catalog lookup).
_NAME_ALIASES: dict[str, str] = {
    "Llama 3.1 70B": "meta.llama3-1-70b-instruct-v1:0",
    "Llama 3.1 8B": "meta.llama3-1-8b-instruct-v1:0",
    "Embed 3 English": "cohere.embed-english-v3",
    "Embed 3 Multilingual": "cohere.embed-multilingual-v3",
    "Cohere Command": "cohere.command-text-v14",
    "Cohere Command - Light": "cohere.command-light-text-v14",
    "Llama 2 Chat (13B)": "meta.llama2-13b-chat-v1",
    "Llama 2 Chat (70B)": "meta.llama2-70b-chat-v1",
    "Gemma 3 12B": "google.gemma-3-12b-it",
    "Gemma 3 27B": "google.gemma-3-27b-it",
    "Gemma 3 4B": "google.gemma-3-4b-it",
    "Qwen3 32B": "qwen.qwen3-32b-v1:0",
    "Qwen3 Coder 30B A3B": "qwen.qwen3-coder-30b-a3b-v1:0",
    "Ministral 3B 3.0": "mistral.ministral-3-3b-instruct",
    "Ministral 8B 3.0": "mistral.ministral-3-8b-instruct",
    "Magistral Small 1.2": "mistral.magistral-small-2509",
    "NVIDIA Nemotron Nano 2": "nvidia.nemotron-nano-9b-v2",
    "NVIDIA Nemotron Nano 2 VL": "nvidia.nemotron-nano-12b-v2",
    "NVIDIA Nemotron 3 Nano 30B A3B": "nvidia.nemotron-nano-3-30b",
}

_SUFFIX_RE = re.compile(
    r"\s*\([^)]*(?:Public Extended Access|Effective)[^)]*\)\s*",
    re.IGNORECASE,
)
_EXTENDED_RE = re.compile(
    r"public extended access|extended access|effective \d",
    re.IGNORECASE,
)


def normalize_name(name: str) -> str:
    name = _SUFFIX_RE.sub("", name)
    return re.sub(r"\s+", " ", name).strip()


def _normalize_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def build_display_name_lookup(catalog: dict | None) -> dict[str, str]:
    """Map normalized display names to model_id from catalog + aliases."""
    lookup: dict[str, str] = {}
    if catalog:
        for model in catalog.get("models", []):
            display = model.get("display_name")
            model_id = model.get("model_id")
            if display and model_id:
                lookup[_normalize_key(display)] = model_id
    for alias_name, model_id in _NAME_ALIASES.items():
        lookup[_normalize_key(alias_name)] = model_id
    return lookup


def resolve_name_to_model_id(name: str, lookup: dict[str, str]) -> str | None:
    return lookup.get(_normalize_key(normalize_name(name)))


def parse_price(text: str) -> float | None:
    if not text or text.strip().upper() in ("N/A", "—", "-", ""):
        return None
    if "{priceOf" in text:
        return None
    match = re.search(r"\$?\s*([\d.]+)", text.replace(",", ""))
    if not match:
        return None
    return float(match.group(1))


def per_1m_to_per_1k(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value / 1000, 6)


def detect_unit(table_text: str) -> str:
    lower = table_text.lower()
    if "per image" in lower or "per generation" in lower:
        return "image"
    if "per 1,000 queries" in lower or "per 1000 queries" in lower:
        return "query"
    if "price per 1,000 queries" in lower:
        return "query"
    return "token"


def extract_rows(
    soup: BeautifulSoup,
    catalog: dict | None = None,
) -> tuple[list[dict], list[str]]:
    """Extract model pricing from tables with literal dollar amounts."""
    lookup = build_display_name_lookup(catalog)
    scraped: dict[str, dict] = {}
    unmapped: list[str] = []

    provider_headers = (
        "Anthropic",
        "Meta",
        "Amazon",
        "Cohere",
        "Mistral",
        "OpenAI",
        "DeepSeek",
        "Google",
        "AI21 Labs",
        "Stability AI",
    )

    for table in soup.find_all("table"):
        table_text = table.get_text(" ", strip=True)
        if "{priceOf" in str(table):
            continue
        unit = detect_unit(table_text)
        if unit == "query":
            continue

        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            if cells[0].startswith("**") or len(cells[0]) > 120:
                continue

            name: str | None = None
            input_raw: str | None = None
            output_raw: str | None = None

            if unit == "image":
                name = cells[0]
                prices = [c for c in cells[1:] if "$" in c]
                if not prices:
                    continue
                input_raw = prices[0]
                output_raw = prices[1] if len(prices) > 1 else None
            else:
                if len(cells) >= 3 and cells[0] in provider_headers:
                    name = cells[1]
                    price_cells = cells[3:]
                else:
                    name = cells[0]
                    price_cells = cells[1:]

                dollar_cells = [c for c in price_cells if "$" in c]
                if not dollar_cells:
                    continue
                input_raw = dollar_cells[0]
                output_raw = dollar_cells[1] if len(dollar_cells) > 1 else None

            if not name or _EXTENDED_RE.search(name):
                continue

            normalized = normalize_name(name)
            model_id = resolve_name_to_model_id(normalized, lookup)
            if not model_id:
                unmapped.append(normalized)
                continue

            input_val = parse_price(input_raw or "")
            output_val = parse_price(output_raw or "") if output_raw else None

            if unit == "image":
                entry = {
                    "standard_per_image": input_val,
                    "premium_per_image": output_val,
                }
            else:
                entry = {
                    "input_per_1k": per_1m_to_per_1k(input_val),
                    "output_per_1k": per_1m_to_per_1k(output_val),
                }

            if model_id not in scraped:
                scraped[model_id] = {"name": normalized, "pricing": entry, "unit": unit}

    rows_out = [
        {
            "model_id": mid,
            "name": data["name"],
            "pricing": data["pricing"],
            "unit": data["unit"],
        }
        for mid, data in scraped.items()
    ]
    return rows_out, unmapped
