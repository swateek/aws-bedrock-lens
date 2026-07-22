"""Convert Bedrock foundation model inventory into catalog model entries."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from catalog_io import empty_on_demand
from model_id_inference import display_name_for_model_id, provider_for_model_id

SNAPSHOT_PATH_NAME = "model-inventory.snapshot.json"

_IMAGE_ID_RE = re.compile(
    r"image|canvas|reel|stable-image|titan-image|nova-canvas|nova-reel",
    re.IGNORECASE,
)
_VIDEO_ID_RE = re.compile(r"ray|reel|video|t2v|i2v", re.IGNORECASE)
_RERANK_ID_RE = re.compile(r"rerank", re.IGNORECASE)
_EMBED_ID_RE = re.compile(
    r"embed|embedding|titan-embed|nova.*embed",
    re.IGNORECASE,
)


def provider_display(provider_name: str) -> str:
    return (provider_name or "Unknown").strip()


def infer_pricing_type(model_id: str, input_mods: list[str], output_mods: list[str]) -> str:
    if _RERANK_ID_RE.search(model_id):
        return "rerank"
    if _VIDEO_ID_RE.search(model_id) and not _EMBED_ID_RE.search(model_id):
        return "video"
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
                kept = existing.get("pricing_type")
                suggested = fresh["pricing_type"]
                warnings.append(
                    f"Pricing type mismatch for {model_id}: "
                    f"kept {kept}, inventory suggests {suggested}"
                )
        else:
            by_id[model_id] = fresh
            added += 1

    catalog["models"] = sorted(by_id.values(), key=lambda m: m["model_id"])
    return added, updated, warnings


def stub_catalog_entry_from_model_id(
    model_id: str,
    *,
    display_name: str | None = None,
    provider: str | None = None,
    regions: list[str] | None = None,
) -> dict[str, Any]:
    """Minimal catalog row for models discovered from Price List or HTML."""
    pricing_type = infer_pricing_type(model_id, ["TEXT"], ["TEXT"])
    label = display_name or display_name_for_model_id(model_id)
    return {
        "model_id": model_id,
        "display_name": label,
        "provider": provider or provider_for_model_id(model_id),
        "pricing_type": pricing_type,
        "pricing_source": "manual",
        "regions": sorted(regions or ["us-east-1"]),
        "on_demand": empty_on_demand(pricing_type),
        "context_window": None,
        "modalities": infer_modalities(["TEXT"], ["TEXT"]),
        "notes": None,
        "availability": "ga",
        "alternate_ids": [],
    }


def inventory_record_from_stub(entry: dict[str, Any]) -> dict[str, Any]:
    """Snapshot-shaped record for a provisioned catalog entry."""
    return {
        "modelId": entry["model_id"],
        "modelName": entry.get("display_name") or entry["model_id"],
        "providerName": entry.get("provider", "Unknown"),
        "inputModalities": ["TEXT"],
        "outputModalities": ["TEXT"]
        if entry.get("pricing_type") == "token"
        else (["IMAGE"] if entry.get("pricing_type") == "image" else ["EMBEDDING"]),
        "responseStreamingSupported": entry.get("pricing_type") == "token",
        "customizationsSupported": [],
        "inferenceTypesSupported": ["ON_DEMAND"],
        "modelLifecycle": {"status": "ACTIVE"},
        "regions": list(entry.get("regions") or ["us-east-1"]),
    }


def append_inventory_records(
    snapshot_path: Path,
    records: list[dict[str, Any]],
) -> int:
    """Append new modelId rows to the inventory snapshot (idempotent)."""
    if not records:
        return 0
    if snapshot_path.exists():
        data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    else:
        data = {"synced_at": None, "regions_scanned": ["us-east-1"], "models": []}
    existing = {m["modelId"] for m in data.get("models", [])}
    added = 0
    for record in records:
        mid = record["modelId"]
        if mid in existing:
            continue
        data.setdefault("models", []).append(record)
        existing.add(mid)
        added += 1
    if added:
        data["synced_at"] = date.today().isoformat()
        data["models"] = sorted(data["models"], key=lambda m: m["modelId"])
        snapshot_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return added


def provision_catalog_entries(
    catalog: dict,
    entries: list[dict[str, Any]],
) -> int:
    """Insert stub catalog entries; skip existing model_id."""
    by_id = {m["model_id"]: m for m in catalog.get("models", [])}
    added = 0
    for entry in entries:
        mid = entry["model_id"]
        if mid in by_id:
            continue
        by_id[mid] = entry
        added += 1
    catalog["models"] = sorted(by_id.values(), key=lambda m: m["model_id"])
    return added
