"""Extract provenance-bearing SKU facts from AWS Price List offers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from normalize_rate import CanonicalMetric, normalize_rate

OFFER_FM = "AmazonBedrockFoundationModels"
OFFER_BEDROCK = "AmazonBedrock"

DEFAULT_REGION = "us-east-1"

TierName = Literal[
    "on_demand",
    "on_demand_global",
    "batch",
    "batch_global",
    "flex",
    "priority",
    "cache",
    "cache_global",
]

# Hard-drop SKUs we never publish
_SKIP_UT = re.compile(
    r"latency|provisioned|reserved|custom-model|customization|custom model|rft|grounding",
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
    r"(?:-input-tokens|-output-tokens|-text-input-tokens|-text-output-tokens|"
    r"-cache|-batch|-flex|-priority)",
    re.IGNORECASE,
)

# Regional usagetype prefixes: USE1-, USW2-, EU-, APS1-, etc.
_UT_PREFIX = re.compile(r"^[A-Z0-9]{2,}-(.+)$")


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
            "region": self.region,
            "tier": self.tier,
        }


def classify_tier(usagetype: str) -> TierName | None:
    """Map usagetype → catalog tier, or None if the SKU should be skipped."""
    if _SKIP_UT.search(usagetype):
        return None
    lower = usagetype.lower()
    is_global = bool(re.search(r"global|cross[-_]?region", lower))
    if "cache" in lower:
        return "cache_global" if is_global else "cache"
    if "batch" in lower:
        return "batch_global" if is_global else "batch"
    if "flex" in lower:
        return "flex"
    if "priority" in lower:
        return "priority"
    if is_global:
        return "on_demand_global"
    return "on_demand"


def _cache_metric(usagetype: str) -> CanonicalMetric | None:
    lower = usagetype.lower()
    if "cache" not in lower:
        return None
    if re.search(r"1h|1-hour|write.?1h|cachewrite1h", lower):
        return "cache_write_1h"
    if re.search(r"write|cachewrite", lower):
        return "cache_write"
    if re.search(r"read|cacheread", lower):
        return "cache_read"
    # Default cache token SKUs that say "cache" + input → read
    if "input" in lower:
        return "cache_read"
    return "cache_write"


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


def _strip_ut_prefix(usagetype: str) -> str:
    m = _UT_PREFIX.match(usagetype)
    return m.group(1) if m else usagetype


def _parse_token_usagetype(usagetype: str) -> tuple[str, str] | None:
    body = _strip_ut_prefix(usagetype)
    # Drop known tier/scope suffixes before matching token tails
    for extra in ("-batch", "-flex", "-priority", "-global", "-cross-region"):
        if body.lower().endswith(extra):
            # handled via classify; keep body for key parse after removing middle tags
            break
    for suffix in _TOKEN_UT_SUFFIXES:
        for tail in ("", "-standard"):
            needle = f"-{suffix}{tail}"
            if body.lower().endswith(needle.lower()):
                # case-sensitive slice using actual length
                idx = body.lower().rfind(needle.lower())
                key = body[:idx]
                # strip trailing tier markers from key
                for marker in ("-batch", "-flex", "-priority", "-global"):
                    if key.lower().endswith(marker):
                        key = key[: -len(marker)]
                return key, suffix
    return None


def _fm_token_metric(usagetype: str) -> CanonicalMetric | None:
    lower = usagetype.lower()
    cache = _cache_metric(usagetype)
    if cache:
        return cache
    if "outputtokencount" in lower or re.search(r"output[_-]tokens", lower):
        return "output_tokens"
    if "inputtokencount" in lower or re.search(r"input[_-]tokens", lower):
        return "input_tokens"
    return None


def _product_region(attrs: dict[str, Any], fallback: str) -> str:
    code = attrs.get("regionCode") or attrs.get("location") or ""
    if isinstance(code, str) and code.strip():
        # location is sometimes a display name; prefer regionCode
        if attrs.get("regionCode"):
            return str(attrs["regionCode"]).strip()
    return fallback


def extract_fm_facts(
    index: dict[str, Any],
    *,
    region: str = DEFAULT_REGION,
    regions_allowlist: set[str] | None = None,
    warnings: list[str] | None = None,
) -> list[SkuFact]:
    """Extract facts from AmazonBedrockFoundationModels index (regional or combined)."""
    warn = warnings if warnings is not None else []
    products = index.get("products", {})
    on_demand = index.get("terms", {}).get("OnDemand", {})
    facts: list[SkuFact] = []

    for product_id, product in products.items():
        if product_id not in on_demand:
            continue
        attrs = product.get("attributes", {})
        usagetype = attrs.get("usagetype", "")
        tier = classify_tier(usagetype)
        if tier is None:
            continue
        product_region = _product_region(attrs, region)
        if regions_allowlist is not None and product_region not in regions_allowlist:
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
                region=product_region,
                tier=tier,
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
    region: str = DEFAULT_REGION,
    regions_allowlist: set[str] | None = None,
    warnings: list[str] | None = None,
) -> list[SkuFact]:
    """Extract facts from AmazonBedrock offer index (regional or combined)."""
    warn = warnings if warnings is not None else []
    products = index.get("products", {})
    on_demand = index.get("terms", {}).get("OnDemand", {})
    facts: list[SkuFact] = []

    for product_id, product in products.items():
        if product_id not in on_demand:
            continue
        attrs = product.get("attributes", {})
        ut = attrs.get("usagetype", "")
        tier = classify_tier(ut)
        if tier is None:
            continue
        product_region = _product_region(attrs, region)
        if regions_allowlist is not None and product_region not in regions_allowlist:
            continue
        dim = _price_dimension(on_demand, product_id)
        if dim is None:
            continue
        price_usd, unit, description = dim

        embedded_id = model_id_from_usagetype(ut)
        offer_key: str | None = None
        metric: CanonicalMetric | None = None

        cache_m = _cache_metric(ut)
        if cache_m:
            metric = cache_m
            parsed = _parse_token_usagetype(ut)
            if parsed:
                offer_key = parsed[0]
        elif re.search(r"T2I-1024-Standard|I2I-1024-Standard", ut):
            m = re.search(
                r"[A-Z0-9]+-(?P<k>NovaCanvas|NovaReel|TitanImageGenerator[^-]+)",
                ut,
            )
            if m:
                offer_key = m.group("k")
                metric = "image_standard"
        elif re.search(r"T2I-1024-Premium|I2I-1024-Premium", ut):
            m = re.search(r"[A-Z0-9]+-(?P<k>NovaCanvas|TitanImageGenerator[^-]+)", ut)
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
                region=product_region,
                tier=tier,
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
