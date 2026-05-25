# AWS Bedrock Lens

A static tool for comparing AWS Bedrock foundation models by pricing, capabilities, and availability. No backend — all data comes from a versioned JSON file in this repo, kept up to date by a Python scraper run via GitHub Actions.

## Features

- Browse and filter models by provider, pricing type, and search
- Select multiple models and compare side-by-side
- Highlights cheapest input/output (or standard image) prices, including ties
- Shareable comparison URLs (`?models=id1,id2`)
- Staleness warning when pricing data is older than 30 days
- Scrape coverage banner — auto vs manually curated prices

## Project structure

```
aws-bedrock-lens/
├── .github/workflows/
│   ├── ci.yml                 # schema + embed sync + tests
│   ├── deploy-pages.yml       # site root = app + data/
│   └── update-pricing.yml     # weekly scrape → PR (meaningful changes only)
├── app/
│   ├── index.html
│   ├── style.css
│   └── js/                    # constants, catalog, compare, browser, …
├── data/
│   ├── pricing.json
│   └── pricing.embed.js       # generated; must match JSON
├── docs/
│   └── PRICING_SOURCES.md     # HTML vs Price List API vs manual
├── schemas/pricing.schema.json
├── scraper/
│   ├── scrape.py
│   ├── validate.py
│   ├── aws_pricing_probe.py
│   └── tests/
├── scripts/preview-site.sh    # local production-like preview
└── Makefile
```

## Quick start

**Production-like preview** (site at `/`, paths `data/…`):

```bash
make preview
# open http://localhost:8080/
```

**Development** (open `app/` from repo):

```bash
python3 -m http.server 8080
# open http://localhost:8080/app/
```

`app/index.html` uses `<meta name="data-base" content="../data/">`; the deploy workflow patches this to `data/` for GitHub Pages.

## Data & validation

```bash
pip install -r scraper/requirements.txt
make validate   # schema + embed in sync
make test
make scrape     # fetch AWS HTML tables
```

- `meta.last_scraped_at` — updated every successful scrape
- `meta.pricing_updated_at` — only when `on_demand` prices change
- PRs open only when prices, sources, or scrape manifest change (not scrape-only dates)
- Weekly scraping (`update-pricing.yml`) runs only against `main` (scheduled + manual dispatch on `main`)

## GitHub Pages

1. Settings → Pages → **GitHub Actions** (not “deploy from branch”).
2. Pushes to `main` — `deploy-pages.yml` publishes `app/` + `data/` to the site root (other branches are not deployed).

Live URL: `https://<user>.github.io/<repo>/` (no `/app/` path).

## Pricing automation gap

Most AWS marketing-page prices are JS placeholders; HTML scrape covers a small fraction. See [docs/PRICING_SOURCES.md](docs/PRICING_SOURCES.md) for:

- **Now:** HTML scrape + manual curation
- **Next:** AWS Price List API (`AmazonBedrock`) mapper
- **Probe:** `make probe` or `python scraper/aws_pricing_probe.py`

## License

See [LICENSE](LICENSE).
