# Pricing data sources

AWS Bedrock Lens publishes **on-demand list prices** mapped to Bedrock `model_id` values. The pipeline is credential-free and runs weekly in GitHub Actions.

## System of record

**AWS public Price List bulk JSON** (us-east-1) is the only automated source that writes prices:

| Offer | Module | Role |
|-------|--------|------|
| `AmazonBedrockFoundationModels` | [`scraper/price_list.py`](../scraper/price_list.py) | Primary: marketplace foundation-model token/image SKUs |
| `AmazonBedrock` | [`scraper/bedrock_offer.py`](../scraper/bedrock_offer.py) | Secondary: gap-fill for Amazon-native SKUs (Nova, Titan, mantle IDs in usagetype) |

Public index URLs (no credentials):

- `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrockFoundationModels/current/us-east-1/index.json`
- `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrock/current/us-east-1/index.json`

## Unit normalization

Rates are normalized from each SKU’s `priceDimensions.unit` (and description when `unit` is `Units`):

| Price List unit | Catalog field |
|-----------------|---------------|
| `1K tokens` | `input_per_1m` / `output_per_1m` (×1000) |
| `1M tokens` / “Million … Tokens” | `*_per_1m` (no scale) |
| `image` | `standard_per_image` / `premium_per_image` |
| `seconds` | `per_second` (`pricing_type: video`) |
| search / rerank units | `per_search_unit` (`pricing_type: rerank`) |

Implementation: [`scraper/normalize_rate.py`](../scraper/normalize_rate.py).

Unknown units are dropped with a warning — never guessed.

## Merge policy

Pipeline order in [`scraper/scrape.py`](../scraper/scrape.py):

1. Inventory snapshot merge (model metadata, not prices)
2. Price List FM discover + merge (`pricing_source: price_list`)
3. AmazonBedrock offer merge (**gap-fill only** — does not overwrite FM prices)
4. Variant price propagation (context-window suffixes inherit base)
5. Manual seeds ([`scraper/price_seeds.py`](../scraper/price_seeds.py)) — **null-fill only**
6. HTML marketing page — **QA only** (warnings on mismatch; never writes prices)

## Entity resolution

1. Bedrock `model_id` embedded in AmazonBedrock `usagetype` (preferred)
2. Explicit map: [`scraper/sku_overrides.json`](../scraper/sku_overrides.json)
3. Service name → `model_id` via catalog display names + [`scraper/model_id_inference.py`](../scraper/model_id_inference.py)
4. Amazon offer keys via [`scraper/offer_key_map.py`](../scraper/offer_key_map.py)

Fuzzy inference provisions discovery stubs only; priced rows require a resolved SKU join.

## Provenance

Auto-priced models may include `price_provenance` per field (`offer`, `usagetype`, `unit`, `product_sku`). `pricing_source` is `price_list` or `manual`.

## Quality gates

- **Golden canaries**: [`scraper/tests/fixtures/golden_rates.json`](../scraper/tests/fixtures/golden_rates.json) — checked in `scrape.py` and `validate.py`
- **HTML QA**: optional cross-check vs marketing literals
- **Coverage**: `scrape.price_coverage_pct` — never imply 100% without it

## What we do not use in CI

| Source | Status |
|--------|--------|
| HTML scrape as price writer | Removed — QA only |
| Headless browser | Not used |
| `pricing:GetProducts` (boto3) | Local probe only ([`scraper/aws_pricing_probe.py`](../scraper/aws_pricing_probe.py)) |
| Bedrock `ListFoundationModels` | Not used — committed inventory snapshot |
| `ListFoundationModelAgreementOffers` | Not used |

## Manual curation

Mark `pricing_source: "manual"` for preview models and gaps. Seeds in `price_seeds.py` fill only when Price List has no SKU.

## Regional scope

Current automation targets **us-east-1** list prices (`meta.price_list_region`). Regional dimensions are a future extension.

## Probe script

```bash
make probe
# Optional local debug with AWS creds:
python scraper/aws_pricing_probe.py --sample
```
