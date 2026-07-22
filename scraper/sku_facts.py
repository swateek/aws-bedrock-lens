"""Extract provenance-bearing SKU facts from AWS Price List offers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from normalize_rate import CanonicalMetric, normalize_rate

OFFER_FM = "AmazonBedrockFoundationModels"
OFFER_BEDROCK = "AmazonBedrock"

_EXCLUDED_UT = re.compile(
    r"batch|flex|priority|latency|provisioned|reserved|cache|cross-region|"
    r"custom-model|customization|rft|global|grounding",
    re.IGNORECASE,
)
_FM_EXCLUDED_UT = re.compile(
    r"batch|flex|priority|latency|provisioned|reserved|cache|global|"
    r"customization|custom model",
    re.IGNORECASE,
)

_TOKEN_UT_SUFFIXES = (
    "text-input-tokens",
    "text-output-tokens",
    "speech-input-tokens",
    "speech-output-tokens",
    "input-tokens",
    "output-tokens",
)

# Bedrock-style model_id embedded in usagetype (e.g. openai.gpt-oss-120b-...)
_MODEL_ID_IN_UT = re.compile(
    r"(?P<id>[a-z][a-z0-9]*\.[a-z0-9][a-z0-9._-]*(?:-mantle)?)"
    r"(?:-input-tokens|-output-tokens|-text-input-tokens|-text-output-tokens)",
    re.IGNORECASE,
)


@dataclass
class SkuFact:
    model_id: str | None
    offer_key: str | None
    region: str
    tier: str
    metric: CanonicalMetric
    rate_usd: float
    catalog_field: str
    source_offer: str
    product_sku: str
    usagetype: str
    unit: str
    service_name: str = ""
    provenance: dict[str, str] = field(default_factory=dict)

    def to_provenance(self) -> dict[str, str]:
        return {
            "offer": self.source_offer,
            "usagetype": self.usagetype,
            "unit": self.unit,
            "product_sku": self.product_sku,
        }


def _price_dimension(on_demand: dict, product_id: str) -> tuple[float, str, str] | None:
    for dimension in on_demand.get(product_id, {}).values():
        for price_dim in dimension.get("priceDimensions", {}).values():
            raw = price_dim.get("pricePerUnit", {}).get("USD")
            if raw is not None:
                return (
                    float(raw),
                    price_dim.get("unit") or "",
                    price_dim.get("description") or "",
                )
    return None


def model_id_from_usagetype(usagetype: str) -> str | None:
    """Extract Bedrock model_id when embedded in AmazonBedrock usagetype."""
    m = _MODEL_ID_IN_UT.search(usagetype)
    if m:
        return m.group("id").lower()
    return None


def _parse_token_usagetype(usagetype: str) -> tuple[str, str] | None:
    if not usagetype.startswith("USE1-"):
        return None
    body = usagetype[5:]
    for suffix in _TOKEN_UT_SUFFIXES:
        for tail in ("", "-standard"):
            needle = f"-{suffix}{tail}"
            if body.endswith(needle):
                key = body[: -len(needle)]
                return key, suffix
    return None


def _fm_token_metric(usagetype: str) -> CanonicalMetric | None:
    lower = usagetype.lower()
    if "outputtokencount" in lower or re.search(r"output[_-]tokens", lower):
        return "output_tokens"
    if "inputtokencount" in lower or re.search(r"input[_-]tokens", lower):
        return "input_tokens"
    return None


def _fm_is_on_demand(usagetype: str) -> bool:
    return not _FM_EXCLUDED_UT.search(usagetype)


def _br_is_on_demand(usagetype: str) -> bool:
    return not _EXCLUDED_UT.search(usagetype)


def extract_fm_facts(
    index: dict[str, Any],
    *,
    region: str = "us-east-1",
    warnings: list[str] | None = None,
) -> list[SkuFact]:
    """Extract facts from AmazonBedrockFoundationModels index."""
    warn = warnings if warnings is not None else []
    products = index.get("products", {})
    on_demand = index.get("terms", {}).get("OnDemand", {})
    facts: list[SkuFact] = []

    for product_id, product in products.items():
        if product_id not in on_demand:
            continue
        attrs = product.get("attributes", {})
        usagetype = attrs.get("usagetype", "")
        if not _fm_is_on_demand(usagetype):
            continue
        dim = _price_dimension(on_demand, product_id)
        if dim is None:
            continue
        price_usd, unit, description = dim
        metric = _fm_token_metric(usagetype)
        if metric is None:
            lower = usagetype.lower()
            if "created_image" in lower or "created-image" in lower:
                metric = "image_standard"
            elif "search_units" in lower:
                metric = "search_unit"
            elif "embed" in lower or "inputtextrequestcount" in lower:
                metric = "embedding_tokens"
            else:
                continue

        normalized = normalize_rate(unit, price_usd, description=description, metric_hint=metric)
        if normalized is None:
            warn.append(f"Unknown unit for FM SKU {product_id}: unit={unit!r}")
            continue

        facts.append(
            SkuFact(
                model_id=None,
                offer_key=None,
                region=region,
                tier="on_demand_standard",
                metric=normalized.metric,
                rate_usd=normalized.rate_usd,
                catalog_field=normalized.catalog_field,
                source_offer=OFFER_FM,
                product_sku=product_id,
                usagetype=usagetype,
                unit=unit,
                service_name=attrs.get("servicename", ""),
            )
        )
    return facts


def extract_bedrock_offer_facts(
    index: dict[str, Any],
    *,
    region: str = "us-east-1",
    warnings: list[str] | None = None,
) -> list[SkuFact]:
    """Extract facts from AmazonBedrock offer index."""
    warn = warnings if warnings is not None else []
    products = index.get("products", {})
    on_demand = index.get("terms", {}).get("OnDemand", {})
    facts: list[SkuFact] = []

    for product_id, product in products.items():
        if product_id not in on_demand:
            continue
        ut = product.get("attributes", {}).get("usagetype", "")
        if not _br_is_on_demand(ut):
            continue
        dim = _price_dimension(on_demand, product_id)
        if dim is None:
            continue
        price_usd, unit, description = dim

        embedded_id = model_id_from_usagetype(ut)
        offer_key: str | None = None
        metric: CanonicalMetric | None = None

        if "T2I-1024-Standard" in ut or "I2I-1024-Standard" in ut:
            m = re.search(r"USE1-(?P<k>NovaCanvas|NovaReel|TitanImageGenerator[^-]+)", ut)
            if m:
                offer_key = m.group("k")
                metric = "image_standard"
        elif "T2I-1024-Premium" in ut or "I2I-1024-Premium" in ut:
            m = re.search(r"USE1-(?P<k>NovaCanvas|TitanImageGenerator[^-]+)", ut)
            if m:
                offer_key = m.group("k")
                metric = "image_premium"
        elif "NovaReel-T2V" in ut or "NovaReel-I2V" in ut:
            offer_key = "NovaReel"
            metric = "image_standard"
        elif "NovaMultiModalEmbeddings-input-tokens" in ut:
            offer_key = "NovaMultiModalEmbeddings"
            metric = "embedding_tokens"
        elif "TitanEmbeddingsG1-Text-input-tokens" in ut:
            offer_key = "TitanEmbeddingsG1-Text"
            metric = "embedding_tokens"
        elif "TitanEmbeddingV2-Text-input-tokens" in ut:
            offer_key = "TitanEmbeddingV2-Text"
            metric = "embedding_tokens"
        elif "TitanEmbeddingsG1-Image-input-tokens" in ut:
            offer_key = "TitanEmbeddingsG1-Image"
            metric = "embedding_tokens"
        else:
            parsed = _parse_token_usagetype(ut)
            if parsed:
                offer_key, kind = parsed
                if "input" in kind:
                    metric = "input_tokens"
                elif "output" in kind:
                    metric = "output_tokens"

        if metric is None:
            continue

        normalized = normalize_rate(unit, price_usd, description=description, metric_hint=metric)
        if normalized is None:
            warn.append(f"Unknown unit for Bedrock SKU {product_id}: unit={unit!r}")
            continue

        facts.append(
            SkuFact(
                model_id=embedded_id,
                offer_key=offer_key,
                region=region,
                tier="on_demand_standard",
                metric=normalized.metric,
                rate_usd=normalized.rate_usd,
                catalog_field=normalized.catalog_field,
                source_offer=OFFER_BEDROCK,
                product_sku=product_id,
                usagetype=ut,
                unit=unit,
            )
        )
    return facts


def fact_provenance_dict(fact: SkuFact) -> dict[str, str]:
    return fact.to_provenance()
