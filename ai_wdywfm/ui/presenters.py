from __future__ import annotations

import html

from ai_wdywfm.domain.models import PromptSuggestion


def summary_markdown(suggestion: PromptSuggestion) -> str:
    return html.escape(suggestion.summary) if suggestion.summary else "Suggestion validated."


def warnings_markdown(suggestion: PromptSuggestion) -> str:
    if not suggestion.warnings:
        return '<span class="wdywfm-ok">No validation warnings</span>'
    return "\n".join(f"- {html.escape(warning)}" for warning in suggestion.warnings)


def recommendations_html(suggestion: PromptSuggestion) -> str:
    rec = suggestion.recommendations
    values = [
        ("Sampler", rec.sampler),
        ("Scheduler", rec.scheduler),
        ("Steps", rec.sampling_steps),
        ("CFG", _number(rec.cfg_scale)),
        ("Canvas", _canvas(rec.width, rec.height)),
        ("Denoise", _number(rec.denoising_strength)),
    ]
    cards = "".join(
        (
            '<div class="wdywfm-rec">'
            f'<span>{html.escape(label)}</span>'
            f'<strong>{html.escape(str(value if value is not None else "—"))}</strong>'
            "</div>"
        )
        for label, value in values
    )
    return (
        '<div class="wdywfm-rec-grid">'
        f"{cards}"
        "</div>"
        '<p class="wdywfm-readonly">Read-only · generation settings are never changed.</p>'
    )


def model_note(suggestion: PromptSuggestion) -> str:
    if suggestion.loras:
        names = html.escape(", ".join(lora.id for lora in suggestion.loras))
        return f"Validated local LoRA: {names}"
    return "No LoRA selected · current checkpoint stays active"


def _number(value: float | None) -> str | None:
    return None if value is None else f"{value:g}"


def _canvas(width: int | None, height: int | None) -> str | None:
    return None if width is None or height is None else f"{width} × {height}"
