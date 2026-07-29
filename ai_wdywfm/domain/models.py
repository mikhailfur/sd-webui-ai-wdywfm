from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelMetadata:
    """Provider-neutral metadata for an installed checkpoint or LoRA."""

    local_id: str
    kind: str
    display_name: str
    base_model: str | None = None
    civitai_model_id: int | None = None
    civitai_version_id: int | None = None
    sha256: str | None = None
    trigger_word_groups: tuple[tuple[str, ...], ...] = ()
    description_text: str | None = None
    sample_prompts: tuple[str, ...] = ()
    negative_prompts: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    preferred_weight: float | None = None
    provenance: dict[str, str] = field(default_factory=dict)
    status: str = "local"

    @property
    def trigger_words(self) -> tuple[str, ...]:
        return tuple(word for group in self.trigger_word_groups for word in group)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["trigger_word_groups"] = [list(group) for group in self.trigger_word_groups]
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ModelMetadata":
        allowed = set(cls.__dataclass_fields__)
        data = {key: item for key, item in value.items() if key in allowed}
        data["trigger_word_groups"] = tuple(
            tuple(str(word) for word in group)
            for group in data.get("trigger_word_groups", ())
            if isinstance(group, (list, tuple))
        )
        for name in ("sample_prompts", "negative_prompts", "tags"):
            data[name] = tuple(str(item) for item in data.get(name, ()))
        data["provenance"] = dict(data.get("provenance") or {})
        return cls(**data)


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
