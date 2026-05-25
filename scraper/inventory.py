"""Convert Bedrock foundation model inventory into catalog model entries."""

from __future__ import annotations

import re
from typing import Any

from catalog_io import empty_on_demand

SNAPSHOT_PATH_NAME = "model-inventory.snapshot.json"

_IMAGE_ID_RE = re.compile(
    r"image|canvas|reel|stable-image|titan-image|nova-canvas|nova-reel",
    re.IGNORECASE,
)
_EMBED_ID_RE = re.compile(
    r"embed|embedding|rerank|titan-embed|nova.*embed",
    re.IGNORECASE,
)


def provider_display(provider_name: str) -> str:
    return (provider_name or "Unknown").strip()


def infer_pricing_type(model_id: str, input_mods: list[str], output_mods: list[str]) -> str:
    if _EMBED_ID_RE.search(model_id):
        return "embedding"
    if _IMAGE_ID_RE.search(model_id):
        return "image"
    outs = {m.upper() for m in output_mods or []}
    ins = {m.upper() for m in input_mods or []}
    if "EMBEDDING" in outs or (outs == {"EMBEDDING"}):
        return "embedding"
    if "IMAGE" in outs and "TEXT" not in outs:
        return "image"
    if "IMAGE" in outs and "TEXT" not in ins:
        return "image"
    return "token"


def infer_modalities(input_mods: list[str], output_mods: list[str]) -> list[str]:
    mods: set[str] = set()
    for m in (input_mods or []) + (output_mods or []):
        u = m.upper()
        if u == "TEXT":
            mods.add("text")
        elif u == "IMAGE":
            mods.add("image")
        elif u in ("EMBEDDING", "VECTOR"):
            mods.add("embedding")
    return sorted(mods) or ["text"]


def infer_availability(lifecycle: dict | None) -> str:
    if not lifecycle:
        return "ga"
    status = (lifecycle.get("status") or "").upper()
    if status in ("LEGACY", "END_OF_LIFE", "DEPRECATED"):
        return "legacy"
    if status in ("PREVIEW", "BETA"):
        return "preview"
    return "ga"


def inventory_record_to_catalog_entry(record: dict[str, Any]) -> dict[str, Any]:
    model_id = record["modelId"]
    pricing_type = infer_pricing_type(
        model_id,
        record.get("inputModalities") or [],
        record.get("outputModalities") or [],
    )
    return {
        "model_id": model_id,
        "display_name": record.get("modelName") or model_id,
        "provider": provider_display(record.get("providerName", "")),
        "pricing_type": pricing_type,
        "pricing_source": "manual",
        "regions": sorted(record.get("regions") or ["us-east-1"]),
        "on_demand": empty_on_demand(pricing_type),
        "context_window": None,
        "modalities": infer_modalities(
            record.get("inputModalities") or [],
            record.get("outputModalities") or [],
        ),
        "notes": None,
        "availability": infer_availability(record.get("modelLifecycle")),
        "alternate_ids": [],
    }


def merge_inventory_into_catalog(
    catalog: dict,
    inventory_models: list[dict[str, Any]],
) -> tuple[int, int, list[str]]:
    """Merge AWS inventory into catalog; preserve existing prices."""
    warnings: list[str] = []
    by_id = {m["model_id"]: m for m in catalog.get("models", [])}
    added = 0
    updated = 0

    for record in inventory_models:
        model_id = record["modelId"]
        fresh = inventory_record_to_catalog_entry(record)
        if model_id in by_id:
            existing = by_id[model_id]
            for key in (
                "display_name",
                "provider",
                "regions",
                "modalities",
                "availability",
            ):
                if existing.get(key) != fresh[key]:
                    existing[key] = fresh[key]
                    updated += 1
            if fresh["pricing_type"] != existing.get("pricing_type"):
                warnings.append(
                    f"Pricing type mismatch for {model_id}: "
                    f"kept {existing.get('pricing_type')}, inventory suggests {fresh['pricing_type']}"
                )
        else:
            by_id[model_id] = fresh
            added += 1

    catalog["models"] = sorted(by_id.values(), key=lambda m: m["model_id"])
    return added, updated, warnings


def fetch_inventory_from_api(regions: list[str]) -> list[dict[str, Any]]:
    import boto3

    merged: dict[str, dict[str, Any]] = {}
    for region in regions:
        client = boto3.client("bedrock", region_name=region)
        for summary in client.list_foundation_models().get("modelSummaries", []):
            model_id = summary["modelId"]
            entry = {k: v for k, v in summary.items() if k != "modelArn"}
            if model_id not in merged:
                merged[model_id] = entry
                merged[model_id]["regions"] = [region]
            elif region not in merged[model_id]["regions"]:
                merged[model_id]["regions"].append(region)
    return list(merged.values())
