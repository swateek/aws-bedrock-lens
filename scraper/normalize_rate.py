"""Normalize AWS Price List units to catalog on_demand fields."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

CanonicalMetric = Literal[
    "input_tokens",
    "output_tokens",
    "image_standard",
    "image_premium",
    "video_second",
    "search_unit",
    "embedding_tokens",
]

# Maps canonical metric -> catalog on_demand field name
METRIC_TO_FIELD: dict[CanonicalMetric, str] = {
    "input_tokens": "input_per_1m",
    "output_tokens": "output_per_1m",
    "image_standard": "standard_per_image",
    "image_premium": "premium_per_image",
    "video_second": "per_second",
    "search_unit": "per_search_unit",
    "embedding_tokens": "input_per_1m",
}

_MILLION_RE = re.compile(r"million|per\s+1\s*m(?:illion)?\s+token", re.IGNORECASE)
_THOUSAND_RE = re.compile(r"per\s+1\s*k(?:\s+token)?|1k\s+token", re.IGNORECASE)


@dataclass(frozen=True)
class NormalizedRate:
    metric: CanonicalMetric
    rate_usd: float
    catalog_field: str
    source_unit: str


def normalize_token_rate(
    unit: str,
    price_usd: float,
    *,
    description: str = "",
) -> NormalizedRate | None:
    """Convert a token SKU to USD per 1M tokens."""
    unit_lower = (unit or "").strip().lower()
    desc = description or ""

    if unit_lower in ("1k tokens", "1k token"):
        return NormalizedRate(
            metric="input_tokens",
            rate_usd=round(price_usd * 1000, 6),
            catalog_field="input_per_1m",
            source_unit=unit,
        )
    if unit_lower in ("1m tokens", "1m token"):
        return NormalizedRate(
            metric="input_tokens",
            rate_usd=round(price_usd, 6),
            catalog_field="input_per_1m",
            source_unit=unit,
        )
    if unit_lower == "units":
        if _MILLION_RE.search(desc):
            return NormalizedRate(
                metric="input_tokens",
                rate_usd=round(price_usd, 6),
                catalog_field="input_per_1m",
                source_unit=unit,
            )
        if _THOUSAND_RE.search(desc):
            return NormalizedRate(
                metric="input_tokens",
                rate_usd=round(price_usd * 1000, 6),
                catalog_field="input_per_1m",
                source_unit=unit,
            )
        # Foundation Models marketplace SKUs default to per-million when unspecified
        if "token" in desc.lower():
            return NormalizedRate(
                metric="input_tokens",
                rate_usd=round(price_usd, 6),
                catalog_field="input_per_1m",
                source_unit=unit,
            )
    return None


def normalize_rate(
    unit: str,
    price_usd: float,
    *,
    description: str = "",
    metric_hint: CanonicalMetric | None = None,
) -> NormalizedRate | None:
    """Map Price List unit + USD to a catalog field and normalized rate."""
    unit_lower = (unit or "").strip().lower()
    desc = description or ""

    if metric_hint in ("input_tokens", "output_tokens", "embedding_tokens"):
        token_rate = normalize_token_rate(unit, price_usd, description=desc)
        if token_rate:
            field = METRIC_TO_FIELD[metric_hint]
            return NormalizedRate(
                metric=metric_hint,
                rate_usd=token_rate.rate_usd,
                catalog_field=field,
                source_unit=unit,
            )
        return None

    if unit_lower in ("image", "images processed", "images processed"):
        metric: CanonicalMetric = (
            "image_premium" if metric_hint == "image_premium" else "image_standard"
        )
        return NormalizedRate(
            metric=metric,
            rate_usd=round(price_usd, 6),
            catalog_field=METRIC_TO_FIELD[metric],
            source_unit=unit,
        )

    if unit_lower in ("seconds", "second", "video"):
        return NormalizedRate(
            metric="video_second",
            rate_usd=round(price_usd, 6),
            catalog_field="per_second",
            source_unit=unit,
        )

    if unit_lower in ("textunit", "requests") and metric_hint == "search_unit":
        return NormalizedRate(
            metric="search_unit",
            rate_usd=round(price_usd, 6),
            catalog_field="per_search_unit",
            source_unit=unit,
        )

    # Token metrics without explicit hint (Bedrock offer path)
    if "token" in unit_lower or unit_lower == "units":
        token_rate = normalize_token_rate(unit, price_usd, description=desc)
        if token_rate and metric_hint:
            return NormalizedRate(
                metric=metric_hint,
                rate_usd=token_rate.rate_usd,
                catalog_field=METRIC_TO_FIELD[metric_hint],
                source_unit=unit,
            )
        return token_rate

    return None
