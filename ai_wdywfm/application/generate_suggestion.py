from __future__ import annotations

import copy
import json
import math
import threading
from pathlib import Path
from typing import Any

from ai_wdywfm.domain.errors import ValidationError
from ai_wdywfm.domain.models import PromptSuggestion
from ai_wdywfm.domain.validation import parse_suggestion, semantic_validate
from ai_wdywfm.infrastructure.images import encode_reference_image
from ai_wdywfm.infrastructure.diagnostics import category_logger
from ai_wdywfm.infrastructure.providers.openai_compatible import OpenAICompatibleClient
from ai_wdywfm.infrastructure.search import CharacterSearchService


ROOT = Path(__file__).resolve().parents[2]


def generate(
    *,
    provider: str,
    model: str,
    base_url: str,
    api_key: str,
    user_text: str,
    dialect: str,
    operation: str,
    mode: str,
    current_prompt: str,
    current_negative: str,
    image: Any,
    cloud_image_consent: bool,
    inventory: dict[str, Any],
    timeout: float,
    thinking_budget: int = 0,
    image_max_side: int,
    request_id: str,
    cancel_event: threading.Event | None = None,
    lmstudio_ttl: int | None = None,
    web_search_enabled: bool = False,
    web_search_sources: list[str] | tuple[str, ...] = (),
    web_search_timeout: float = 10,
) -> PromptSuggestion:
    if not user_text or not user_text.strip():
        raise ValidationError("Describe the image or edit you want.")
    if not model or not model.strip():
        raise ValidationError("Select or enter an LLM model.")
    if image is not None and provider == "OpenRouter" and not cloud_image_consent:
        raise ValidationError("Enable cloud image consent before sending a reference to OpenRouter.")

    schema = json.loads((ROOT / "schemas" / "prompt_suggestion.v1.json").read_text(encoding="utf-8"))
    system = (ROOT / "ai_wdywfm" / "prompts" / "system_v1.txt").read_text(encoding="utf-8")
    dialect_text = (ROOT / "ai_wdywfm" / "prompts" / f"dialect_{dialect}_v1.txt").read_text(encoding="utf-8")
    envelope = {
        "protocol_version": "2.0",
        "mode": mode,
        "intent": {
            "operation": operation.lower(),
            "text": user_text.strip(),
            "prompt_dialect": dialect,
        },
        "current_state": {
            "checkpoint": inventory.get("current_checkpoint"),
            "positive_prompt": current_prompt or "",
            "negative_prompt": current_negative or "",
        },
        "installed_models": inventory.get("context", {}),
        "constraints": inventory.get("constraints", {}),
    }
    image_url = encode_reference_image(image, image_max_side) if image is not None else None
    client = OpenAICompatibleClient(
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
        request_id=request_id,
        cancel_event=cancel_event,
    )
    search_service = (
        CharacterSearchService(
            sources=web_search_sources,
            timeout=web_search_timeout,
            request_id=request_id,
        )
        if web_search_enabled else None
    )
    payload = client.complete(
        model=model.strip(),
        system_prompt=f"{system}\n\nPROMPT DIALECT:\n{dialect_text}",
        envelope=envelope,
        schema=schema,
        image_url=image_url,
        thinking_budget=thinking_budget,
        ttl=lmstudio_ttl if provider == "LM Studio" else None,
        lora_details=inventory.get("lora_details", {}),
        fallback_lora_ids=inventory.get("lora_fallback_ids", []),
        web_search=search_service.search if search_service is not None else None,
        max_search_calls=1,
    )
    constraints = inventory.get("constraints", {})
    return _validate_payload(payload, mode, inventory, constraints, request_id=request_id)


def _validate_payload(
    payload: Any,
    mode: str,
    inventory: dict[str, Any],
    constraints: dict[str, Any],
    request_id: str = "validation",
) -> PromptSuggestion:
    normalized_payload = _normalize_lora_weights(payload, inventory, request_id=request_id)
    suggestion = parse_suggestion(normalized_payload)
    return semantic_validate(
        suggestion,
        mode=mode,
        checkpoints=set(constraints.get("allowed_checkpoint_ids", [])),
        lora_aliases=inventory.get("lora_aliases", {}),
        samplers=set(constraints.get("allowed_samplers", [])),
        schedulers=set(constraints.get("allowed_schedulers", [])),
        lora_triggers=inventory.get("lora_triggers", {}),
        request_id=request_id,
    )


def _normalize_lora_weights(
    payload: Any, inventory: dict[str, Any], *, request_id: str = "validation",
) -> Any:
    if not isinstance(payload, dict):
        return payload
    models = payload.get("models")
    raw_loras = models.get("loras") if isinstance(models, dict) else None
    if not isinstance(raw_loras, list):
        return payload

    result = copy.deepcopy(payload)
    preferred = inventory.get("lora_preferred_weights", {})
    aliases = inventory.get("lora_aliases", {})
    warnings = result.get("warnings")
    if not isinstance(warnings, list):
        warnings = None

    for item in result["models"]["loras"]:
        if not isinstance(item, dict):
            continue
        lora_id = item.get("id")
        if not isinstance(lora_id, str) or lora_id not in aliases:
            continue
        original = item.get("weight")
        parsed = _parse_weight_literal(original)
        changed = False
        if parsed is not None and 0.05 <= abs(parsed) <= 2:
            item["weight"] = parsed
            changed = type(original) is str
        elif parsed is None or parsed == 0:
            # Covers null, "", zero, and any non-numeric string (e.g. "null",
            # "default") that _parse_weight_literal could not turn into a
            # float — those used to fall through unchanged and fail schema
            # validation instead of being repaired locally.
            item["weight"] = float(preferred.get(lora_id, 0.7))
            changed = True
        if changed and warnings is not None and len(warnings) < 20:
            message = f"Normalized LoRA weight for {lora_id} to {item['weight']:g}."
            if message not in warnings:
                warnings.append(message)
        if changed:
            category_logger("validation").debug(
                "request=%s validation.changed code=lora.weight_normalized id=%s original_type=%s value=%s",
                request_id, lora_id, type(original).__name__, item["weight"],
            )
    return result


def _parse_weight_literal(value: Any) -> float | None:
    if type(value) in (int, float):
        result = float(value)
    elif isinstance(value, str):
        try:
            result = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return result if math.isfinite(result) else None
