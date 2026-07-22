"""Golden canary rates for us-east-1 on-demand standard tier."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from catalog_io import PRICE_EPSILON

FIXTURE_PATH = Path(__file__).resolve().parent / "tests" / "fixtures" / "golden_rates.json"


def load_golden_canaries(path: Path = FIXTURE_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def validate_golden_canaries(catalog: dict, *, path: Path = FIXTURE_PATH) -> list[str]:
    """Return list of failures (empty = pass)."""
    canaries = load_golden_canaries(path)
    if not canaries:
        return []

    by_id = {m["model_id"]: m for m in catalog.get("models", [])}
    failures: list[str] = []

    for canary in canaries:
        model_id = canary["model_id"]
        model = by_id.get(model_id)
        if not model:
            failures.append(f"Canary model missing from catalog: {model_id}")
            continue
        od = model.get("on_demand") or {}
        for field, expected in canary.get("on_demand", {}).items():
            actual = od.get(field)
            if actual is None:
                failures.append(f"{model_id}.{field}: expected {expected}, got null")
                continue
            epsilon = canary.get("epsilon", PRICE_EPSILON)
            if abs(actual - expected) > epsilon:
                failures.append(f"{model_id}.{field}: expected {expected}, got {actual}")
    return failures
