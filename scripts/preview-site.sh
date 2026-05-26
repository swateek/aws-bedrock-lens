#!/usr/bin/env bash
# Build _site like deploy-pages.yml and serve at http://localhost:8080/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -f app/config.js ]; then
  cp app/config.js.example app/config.js
fi

rm -rf _site
mkdir -p _site
cp -r app/* _site/
cp -r data _site/data
cp .nojekyll _site/
sed -i.bak 's|name="data-base" content="../data/"|name="data-base" content="data/"|g' _site/index.html
rm -f _site/index.html.bak

echo "Built _site — open http://localhost:8080/"
echo "Press Ctrl+C to stop."
cd _site && python3 -m http.server 8080
