.PHONY: validate test scrape preview probe lint

lint:
	pre-commit run --all-files

validate:
	python scraper/validate.py --check-embed

test:
	pytest

scrape:
	python scraper/scrape.py

preview:
	bash scripts/preview-site.sh

probe:
	python scraper/aws_pricing_probe.py

sync-embed:
	python scraper/validate.py --sync-embed
