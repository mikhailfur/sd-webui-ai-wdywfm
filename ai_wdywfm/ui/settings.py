from __future__ import annotations

import gradio as gr

from modules import shared


SECTION = ("ai-wdywfm", "AI WDYWFM")


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
        "wdywfm_lmstudio_model": shared.OptionInfo(
            "",
            "Default LM Studio model id",
            section=SECTION,
        ),
        "wdywfm_openrouter_model": shared.OptionInfo(
            "",
            "Default OpenRouter model id",
            section=SECTION,
        ),
        "wdywfm_timeout": shared.OptionInfo(
            60,
            "LLM request timeout (seconds)",
            gr.Slider,
            {"minimum": 10, "maximum": 300, "step": 5},
            section=SECTION,
        ),
        "wdywfm_image_max_side": shared.OptionInfo(
            1536,
            "Reference image maximum side (pixels)",
            gr.Slider,
            {"minimum": 512, "maximum": 2048, "step": 64},
            section=SECTION,
        ),
        "wdywfm_inventory_limit": shared.OptionInfo(
            80,
            "Maximum compact model entries per type sent to the LLM",
            gr.Slider,
            {"minimum": 10, "maximum": 250, "step": 10},
            section=SECTION,
        ),
        "wdywfm_debug_logging": shared.OptionInfo(
            False,
            "Enable redacted debug logging",
            section=SECTION,
        ),
    }
    for key, option in options.items():
        shared.opts.add_option(key, option)


def get_setting(name: str, fallback):
    return getattr(shared.opts, name, fallback)
