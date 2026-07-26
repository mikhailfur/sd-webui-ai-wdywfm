from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class LoraSuggestion:
    id: str
    weight: float
    trigger_words: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class Recommendations:
    sampler: str | None
    scheduler: str | None
    sampling_steps: int | None
    cfg_scale: float | None
    width: int | None
    height: int | None
    denoising_strength: float | None


@dataclass(frozen=True)
class PromptSuggestion:
    schema_version: str
    prompt: str
    negative_prompt: str
    checkpoint_id: str | None
    loras: tuple[LoraSuggestion, ...]
    recommendations: Recommendations
    summary: str
    warnings: tuple[str, ...]

    def to_state(self) -> dict[str, Any]:
        value = asdict(self)
        value["valid"] = True
        return value
