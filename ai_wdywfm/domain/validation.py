from __future__ import annotations

import math
import re
from dataclasses import replace
from typing import Any

from .errors import ValidationError
from .models import LoraSuggestion, PromptSuggestion, Recommendations


ROOT_KEYS = {
    "schema_version", "prompt", "negative_prompt", "models",
    "recommendations", "summary", "warnings",
}
MODEL_KEYS = {"checkpoint_id", "loras"}
LORA_KEYS = {"id", "weight", "trigger_words", "reason"}
RECOMMENDATION_KEYS = {
    "sampler", "scheduler", "sampling_steps", "cfg_scale", "width", "height",
    "denoising_strength",
}
LORA_TAG = re.compile(r"<lora:([^:>]+):([+-]?(?:\d+(?:\.\d*)?|\.\d+))>", re.IGNORECASE)
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _object(value: Any, keys: set[str], path: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValidationError(f"{path} must be an object.")
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        details = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if extra:
            details.append(f"unknown {', '.join(extra)}")
        raise ValidationError(f"{path}: {'; '.join(details)}.")
    return value


def _string(value: Any, path: str, maximum: int, minimum: int = 0) -> str:
    if type(value) is not str or not minimum <= len(value) <= maximum:
        raise ValidationError(f"{path} must be a string of {minimum}–{maximum} characters.")
    if CONTROL_CHARS.search(value):
        raise ValidationError(f"{path} contains control characters.")
    return value


def _nullable_number(value: Any, path: str, low: float, high: float) -> float | None:
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValidationError(f"{path} must be null or a number from {low} to {high}.")
    return float(value)


def _number(value: Any, path: str, low: float, high: float) -> float:
    result = _nullable_number(value, path, low, high)
    if result is None:
        raise ValidationError(f"{path} must be a number from {low} to {high}.")
    return result


def _lora_weight(value: Any, path: str) -> float:
    if type(value) not in (int, float):
        raise ValidationError(
            f"{path} must be a JSON number such as 0.7, never null or a quoted string."
        )
    result = _number(value, path, -2, 2)
    if abs(result) < 0.05:
        raise ValidationError(
            f"{path} must have a meaningful non-zero magnitude from 0.05 to 2."
        )
    return result


def _nullable_integer(value: Any, path: str, low: int, high: int) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not low <= value <= high:
        raise ValidationError(f"{path} must be null or an integer from {low} to {high}.")
    return value


def parse_suggestion(payload: Any) -> PromptSuggestion:
    root = _object(payload, ROOT_KEYS, "response")
    if root["schema_version"] != "1.0":
        raise ValidationError("schema_version must be exactly 1.0.")

    models = _object(root["models"], MODEL_KEYS, "models")
    checkpoint = models["checkpoint_id"]
    if checkpoint is not None:
        checkpoint = _string(checkpoint, "models.checkpoint_id", 500, 1)

    raw_loras = models["loras"]
    if type(raw_loras) is not list or len(raw_loras) > 12:
        raise ValidationError("models.loras must be an array with at most 12 items.")
    loras = []
    for index, raw in enumerate(raw_loras):
        item = _object(raw, LORA_KEYS, f"models.loras[{index}]")
        words = item["trigger_words"]
        if type(words) is not list or len(words) > 32:
            raise ValidationError(f"models.loras[{index}].trigger_words is invalid.")
        loras.append(
            LoraSuggestion(
                id=_string(item["id"], f"models.loras[{index}].id", 500, 1),
                weight=_lora_weight(item["weight"], f"models.loras[{index}].weight"),
                trigger_words=tuple(
                    _string(word, f"models.loras[{index}].trigger_words", 200)
                    for word in words
                ),
                reason=_string(item["reason"], f"models.loras[{index}].reason", 500),
            )
        )

    raw_rec = _object(root["recommendations"], RECOMMENDATION_KEYS, "recommendations")
    recommendations = Recommendations(
        sampler=_nullable_string(raw_rec["sampler"], "recommendations.sampler"),
        scheduler=_nullable_string(raw_rec["scheduler"], "recommendations.scheduler"),
        sampling_steps=_nullable_integer(raw_rec["sampling_steps"], "recommendations.sampling_steps", 1, 150),
        cfg_scale=_nullable_number(raw_rec["cfg_scale"], "recommendations.cfg_scale", 0, 30),
        width=_nullable_integer(raw_rec["width"], "recommendations.width", 64, 2048),
        height=_nullable_integer(raw_rec["height"], "recommendations.height", 64, 2048),
        denoising_strength=_nullable_number(
            raw_rec["denoising_strength"], "recommendations.denoising_strength", 0, 1
        ),
    )
    warnings = root["warnings"]
    if type(warnings) is not list or len(warnings) > 20:
        raise ValidationError("warnings must be an array with at most 20 items.")
    return PromptSuggestion(
        schema_version="1.0",
        prompt=_string(root["prompt"], "prompt", 1900, 1),
        negative_prompt=_string(root["negative_prompt"], "negative_prompt", 1900),
        checkpoint_id=checkpoint,
        loras=tuple(loras),
        recommendations=recommendations,
        summary=_string(root["summary"], "summary", 1200),
        warnings=tuple(_string(item, "warnings[]", 500) for item in warnings),
    )


def _nullable_string(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _string(value, path, 500, 1)


def semantic_validate(
    suggestion: PromptSuggestion,
    *,
    mode: str,
    checkpoints: set[str],
    lora_aliases: dict[str, str],
    samplers: set[str],
    schedulers: set[str],
    lora_triggers: dict[str, tuple[str, ...]] | None = None,
) -> PromptSuggestion:
    warnings = list(suggestion.warnings)
    if suggestion.checkpoint_id is not None and suggestion.checkpoint_id not in checkpoints:
        raise ValidationError("The suggested checkpoint is not installed.")

    selected_aliases: dict[str, tuple[str, float, tuple[str, ...]]] = {}
    lora_triggers = lora_triggers or {}
    for lora in suggestion.loras:
        alias = lora_aliases.get(lora.id)
        if alias is None:
            raise ValidationError(f"The suggested LoRA is not installed: {lora.id}")
        available_triggers = lora_triggers.get(lora.id, ())
        canonical = {_tag_key(word): word for word in available_triggers}
        selected_triggers = []
        for word in lora.trigger_words:
            verified = canonical.get(_tag_key(word))
            if verified is None and available_triggers:
                raise ValidationError(
                    f"LoRA {lora.id} returned an activation word not present in local metadata: {word}"
                )
            if verified is not None and verified not in selected_triggers:
                selected_triggers.append(verified)
        if available_triggers and not selected_triggers:
            # The first Forge activation word is the local user's canonical
            # fallback when compact context omitted this LoRA's full card.
            selected_triggers.append(available_triggers[0])
        selected_aliases[alias.casefold()] = (
            alias, lora.weight, tuple(selected_triggers)
        )

    known_aliases = {alias.casefold() for alias in lora_aliases.values()}
    selected_alias_names = set(selected_aliases)

    def clean_tag(match: re.Match[str]) -> str:
        alias = match.group(1).strip()
        if alias.casefold() not in known_aliases:
            warnings.append(f"Removed unknown LoRA tag: {alias}")
        elif alias.casefold() not in selected_alias_names:
            warnings.append(f"Removed undeclared LoRA tag: {alias}")
        # Never trust provider-authored network syntax or weight. The verified
        # selection below is the only source of applied LoRA tags.
        return ""

    prompt = LORA_TAG.sub(clean_tag, suggestion.prompt)
    prompt = re.sub(r"\s*,\s*,+", ", ", prompt).strip(" ,")
    prompt_tags = {_tag_key(part) for part in prompt.split(",")}
    for _, _, trigger_words in selected_aliases.values():
        for word in trigger_words:
            if _tag_key(word) not in prompt_tags:
                prompt = f"{prompt}, {word}".strip(" ,")
                prompt_tags.add(_tag_key(word))
    for alias, weight, _ in selected_aliases.values():
        prompt = f"{prompt}, <lora:{alias}:{weight:g}>".strip(" ,")

    rec = suggestion.recommendations
    if rec.sampler and samplers and rec.sampler not in samplers:
        warnings.append(f"Unknown sampler recommendation ignored: {rec.sampler}")
        rec = replace(rec, sampler=None)
    if rec.scheduler and schedulers and rec.scheduler not in schedulers:
        warnings.append(f"Unknown scheduler recommendation ignored: {rec.scheduler}")
        rec = replace(rec, scheduler=None)
    if mode == "txt2img" and rec.denoising_strength is not None:
        warnings.append("Denoising strength is not applicable to txt2img and was ignored.")
        rec = replace(rec, denoising_strength=None)
    if (rec.width is not None and rec.width % 8) or (rec.height is not None and rec.height % 8):
        warnings.append("Canvas dimensions not divisible by 8 were ignored.")
        rec = replace(rec, width=None, height=None)

    return replace(
        suggestion,
        prompt=prompt,
        recommendations=rec,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _tag_key(value: str) -> str:
    return " ".join(value.casefold().replace("_", " ").split())
