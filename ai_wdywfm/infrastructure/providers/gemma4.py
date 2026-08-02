from __future__ import annotations

import re
from typing import Any

GEMMA4_MODEL = re.compile(r"(?:^|/)gemma[-_. ]?4(?:[-_.:]|$)", re.IGNORECASE)
# 1024 was too tight for the full schema (prompt + negative_prompt + models +
# recommendations + summary + warnings): real completions were hitting
# finish_reason=length around 1024 completion_tokens, truncating the JSON
# before summary/warnings and failing local validation.
GEMMA4_MAX_TOKENS = 2048


def is_gemma4_model(model: str) -> bool:
    return bool(GEMMA4_MODEL.search(model or ""))


def apply_gemma4_profile(payload: dict[str, Any], system_prompt: str) -> str:
    # OpenRouter already applies the model's native chat template. Custom
    # jailbreak, turn markers, reasoning and sampler presets made Gemma spend
    # its entire output allowance before completing a small JSON object.
    # Keep this profile intentionally close to a plain chat-completions call.
    payload["max_tokens"] = GEMMA4_MAX_TOKENS
    return system_prompt


def normalize_gemma4_content(value: str) -> str:
    result = value.strip()
    for marker in ("<channel|>", "</think>"):
        if marker in result:
            result = result.rsplit(marker, 1)[-1].strip()
    for marker in ("<|channel>final", "<|channel|>final"):
        if result.startswith(marker):
            result = result[len(marker):].strip()
    return result
