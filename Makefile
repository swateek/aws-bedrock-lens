.PHONY: validate test scrape scrape-all sync-models price-list preview probe lint

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install -r scraper/requirements.txt

lint:
	pre-commit run --all-files

validate: $(VENV)/bin/activate
	$(PYTHON) scraper/validate.py --check-embed

test: $(VENV)/bin/activate
	$(PYTHON) -m pytest

scrape: $(VENV)/bin/activate
	$(PYTHON) scraper/scrape.py

scrape-all: $(VENV)/bin/activate
	$(MAKE) sync-models
	$(PYTHON) scraper/scrape.py

sync-models: $(VENV)/bin/activate
	$(PYTHON) scraper/sync_models.py

price-list: $(VENV)/bin/activate
	$(PYTHON) scraper/price_list.py

preview:
	bash scripts/preview-site.sh

probe: $(VENV)/bin/activate
	$(PYTHON) scraper/aws_pricing_probe.py

sync-embed: $(VENV)/bin/activate
	$(PYTHON) scraper/validate.py --sync-embed
