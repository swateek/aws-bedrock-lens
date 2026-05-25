#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${ROOT}/scraper"
if [[ -x "${ROOT}/.venv/bin/python" ]]; then
  exec "${ROOT}/.venv/bin/python" "${ROOT}/scraper/validate.py" --check-embed
fi
exec python3 "${ROOT}/scraper/validate.py" --check-embed
