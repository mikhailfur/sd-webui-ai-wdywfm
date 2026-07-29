from __future__ import annotations

import re
from typing import Any

from ai_wdywfm.application.enrich_metadata import MetadataEnricher
from ai_wdywfm.domain.models import ModelMetadata
from ai_wdywfm.infrastructure.civitai.client import CivitAIClient
from ai_wdywfm.infrastructure.civitai.sidecars import resolve_local_metadata
from ai_wdywfm.infrastructure.diagnostics import get_logger
from ai_wdywfm.infrastructure.storage.sqlite_cache import SQLiteMetadataCache


MAX_DETAILED = 8


def enrich_inventory(
    inventory: dict[str, Any], *, query: str, maximum_items: int, enabled: bool,
    base_url: str, token: str, timeout: float, request_id: str, cache_path=None,
) -> dict[str, Any]:
    """Add local/cached/CivitAI metadata without making import-time network calls."""
    loras: dict[str, tuple[ModelMetadata, str]] = {}
    checkpoints: dict[str, tuple[ModelMetadata, str]] = {}
    try:
        from networks import available_networks
        for stable_id, item in available_networks.items():
            local_id = str(stable_id)
            path = str(item.filename)
            forge = item.metadata if isinstance(item.metadata, dict) else {}
            loras[local_id] = (
                resolve_local_metadata(
                    path, local_id=local_id, kind="lora", display_name=str(item.get_alias()),
                    forge_metadata=forge,
                ),
                path,
            )
    except Exception as exc:
        get_logger().debug("request=%s metadata.lora_scan_failed kind=%s", request_id, type(exc).__name__)

    try:
        from modules import sd_models
        for stable_id, item in sd_models.checkpoints_list.items():
            path = str(getattr(item, "filename", "") or "")
            if not path:
                continue
            forge = getattr(item, "metadata", {})
            checkpoints[str(stable_id)] = (
                resolve_local_metadata(
                    path, local_id=str(stable_id), kind="checkpoint",
                    display_name=str(getattr(item, "title", stable_id)),
                    forge_metadata=forge if isinstance(forge, dict) else {},
                ),
                path,
            )
    except Exception as exc:
        get_logger().debug("request=%s metadata.checkpoint_scan_failed kind=%s", request_id, type(exc).__name__)

    ranked_ids = _rank_ids(loras, query)[:min(MAX_DETAILED, maximum_items)]
    selected = [loras[item_id] for item_id in ranked_ids]
    current_id = inventory.get("current_checkpoint")
    if current_id in checkpoints:
        selected.append(checkpoints[current_id])

    sqlite_hits = sqlite_misses = 0
    if selected:
        try:
            cache = SQLiteMetadataCache(cache_path)
            for metadata, _ in selected:
                if cache.get_metadata(metadata.local_id) is None:
                    sqlite_misses += 1
                else:
                    sqlite_hits += 1
            client = CivitAIClient(
                base_url, token, timeout=timeout, request_id=request_id,
            ) if enabled else None
            results = MetadataEnricher(
                cache=cache, client=client, request_id=request_id,
            ).enrich_many(selected)
            for local_id, metadata in results.items():
                if local_id in loras:
                    loras[local_id] = (metadata, loras[local_id][1])
                elif local_id in checkpoints:
                    checkpoints[local_id] = (metadata, checkpoints[local_id][1])
        except Exception as exc:
            get_logger().warning(
                "request=%s metadata.pipeline_unavailable kind=%s", request_id, type(exc).__name__,
            )

    triggers = inventory.setdefault("lora_triggers", {})
    preferred = inventory.setdefault("lora_preferred_weights", {})
    statuses: dict[str, str] = {}
    for local_id, (metadata, _) in loras.items():
        if metadata.trigger_words:
            triggers[local_id] = metadata.trigger_words
        if metadata.preferred_weight is not None:
            preferred[local_id] = metadata.preferred_weight
        statuses[local_id] = metadata.status

    context = inventory.setdefault("context", {})
    context["detailed_candidates"] = [
        _card(loras[item_id][0]) for item_id in ranked_ids if item_id in loras
    ]
    context["checkpoint_details"] = (
        [_card(checkpoints[current_id][0])] if current_id in checkpoints else []
    )
    inventory["metadata_statuses"] = statuses
    cache_metrics = inventory.setdefault("metadata_cache", {})
    cache_metrics["sqlite_hits"] = sqlite_hits
    cache_metrics["sqlite_misses"] = sqlite_misses
    return inventory


def _rank_ids(items: dict[str, tuple[ModelMetadata, str]], query: str) -> list[str]:
    terms = set(re.findall(r"[\w-]{3,}", (query or "").casefold()))
    scored = []
    for index, (local_id, (metadata, _)) in enumerate(items.items()):
        identity = f"{local_id} {metadata.display_name}".casefold()
        content = " ".join((metadata.description_text or "", *metadata.trigger_words, *metadata.tags)).casefold()
        score = sum(term in identity for term in terms) * 8 + sum(term in content for term in terms) * 2
        scored.append((score, -index, local_id))
    scored.sort(reverse=True)
    return [item[2] for item in scored]


def _card(metadata: ModelMetadata) -> dict[str, Any]:
    card: dict[str, Any] = {
        "id": metadata.local_id, "alias": metadata.display_name,
        "metadata_status": metadata.status,
    }
    if metadata.base_model:
        card["base_model"] = metadata.base_model
    if metadata.trigger_words:
        card["activation_words"] = list(metadata.trigger_words)
    if metadata.preferred_weight is not None:
        card["preferred_weight"] = metadata.preferred_weight
    if metadata.description_text:
        card["description"] = metadata.description_text
    if metadata.sample_prompts:
        card["sample_prompts"] = list(metadata.sample_prompts)
    if metadata.tags:
        card["tags"] = list(metadata.tags)
    return card
