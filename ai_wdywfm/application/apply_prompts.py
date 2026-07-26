from __future__ import annotations

from typing import Any

from ai_wdywfm.domain.errors import ValidationError


def apply_prompt_fields(
    state: dict[str, Any] | None,
    current_prompt: str,
    current_negative: str,
    apply_mode: str,
) -> tuple[str, str]:
    if not state or state.get("valid") is not True:
        raise ValidationError("Generate and validate a suggestion before applying it.")
    prompt = str(state.get("prompt", ""))
    negative = str(state.get("negative_prompt", ""))
    if not prompt:
        raise ValidationError("The validated suggestion has no positive prompt.")
    if apply_mode == "Append":
        return _append(current_prompt, prompt), _append(current_negative, negative)
    return prompt, negative


def _append(current: str, addition: str) -> str:
    current, addition = current.strip(" ,"), addition.strip(" ,")
    if not current:
        return addition
    if not addition:
        return current
    return f"{current}, {addition}"
