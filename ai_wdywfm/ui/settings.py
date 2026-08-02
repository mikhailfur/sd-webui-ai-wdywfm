from __future__ import annotations

import gradio as gr

from modules import shared


SECTION = ("ai-wdywfm", "AI WDYWFM")
VISIBLE_SETTINGS = frozenset({
    "wdywfm_default_provider",
    "wdywfm_lmstudio_url",
    "wdywfm_timeout",
    "wdywfm_timeout_lmstudio",
    "wdywfm_thinking_budget",
})


def register_settings() -> None:
    options = {
        "wdywfm_default_provider": shared.OptionInfo(
            "LM Studio",
            "Default LLM provider",
            gr.Dropdown,
            {"choices": ["LM Studio", "OpenRouter"]},
            section=SECTION,
        ),
        "wdywfm_lmstudio_url": shared.OptionInfo(
            "http://127.0.0.1:1234/v1",
            "LM Studio base URL (loopback only)",
            section=SECTION,
        ),
        "wdywfm_timeout": shared.OptionInfo(
            60,
            "OpenRouter request timeout (seconds)",
            gr.Slider,
            {"minimum": 10, "maximum": 300, "step": 5},
            section=SECTION,
        ),
        "wdywfm_timeout_lmstudio": shared.OptionInfo(
            180,
            "LM Studio request timeout (seconds, local generation is usually slower)",
            gr.Slider,
            {"minimum": 10, "maximum": 900, "step": 5},
            section=SECTION,
        ),
        "wdywfm_thinking_budget": shared.OptionInfo(
            2048,
            "Thinking budget (tokens, 0 uses the provider/model default)",
            gr.Slider,
            {"minimum": 0, "maximum": 32768, "step": 1024},
            section=SECTION,
        ),
    }
    for key, option in options.items():
        shared.opts.add_option(key, option)


def get_setting(name: str, fallback):
    if name not in VISIBLE_SETTINGS:
        return fallback
    return getattr(shared.opts, name, fallback)
