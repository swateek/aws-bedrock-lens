"""Parse AWS Bedrock pricing HTML tables."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

NAME_TO_ID: dict[str, str] = {
    "Claude 3.5 Sonnet v2": "anthropic.claude-3-5-sonnet-20241022-v2:0",
    "Claude 3.5 Sonnet": "anthropic.claude-3-5-sonnet-20240620-v1:0",
    "Claude 3.5 Haiku": "anthropic.claude-3-haiku-20240307-v1:0",
    "Claude 3 Opus": "anthropic.claude-3-opus-20240229-v1:0",
    "Llama 3 70B Instruct": "meta.llama3-70b-instruct-v1:0",
    "Llama 3.1 70B Instruct": "meta.llama3-1-70b-instruct-v1:0",
    "Llama 3.1 8B Instruct": "meta.llama3-1-8b-instruct-v1:0",
    "Mistral Large 3": "mistral.mistral-large-2407-v1:0",
    "Mistral 7B Instruct": "mistral.mistral-7b-instruct-v0:2",
    "Cohere Command R": "cohere.command-r-v1:0",
    "Cohere Embed English v3": "cohere.embed-english-v3",
    "Titan Text Embeddings v2": "amazon.titan-embed-text-v2:0",
    "Titan Image Generator v2": "amazon.titan-image-generator-v2:0",
    "Titan Image Generator v1": "amazon.titan-image-generator-v1",
    "Llama 3.1 70B": "meta.llama3-1-70b-instruct-v1:0",
    "Llama 3.1 8B": "meta.llama3-1-8b-instruct-v1:0",
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


def extract_rows(soup: BeautifulSoup) -> list[dict]:
    """Extract model pricing from tables with literal dollar amounts."""
    scraped: dict[str, dict] = {}

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
                if len(cells) >= 3 and cells[0] in (
                    "Anthropic",
                    "Meta",
                    "Amazon",
                    "Cohere",
                    "Mistral",
                ):
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

            name = normalize_name(name)
            model_id = NAME_TO_ID.get(name)
            if not model_id:
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
                scraped[model_id] = {"name": name, "pricing": entry, "unit": unit}

    return [
        {
            "model_id": mid,
            "name": data["name"],
            "pricing": data["pricing"],
            "unit": data["unit"],
        }
        for mid, data in scraped.items()
    ]
