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
        "wdywfm_lmstudio_auto_unload": shared.OptionInfo(
            True,
            "Automatically load/unload the LM Studio model from GPU memory",
            section=SECTION,
        ).info(
            "Recommended: on. The model is loaded on demand and unloaded shortly after each "
            "request so it does not compete with Stable Diffusion for GPU VRAM. "
            "WARNING: turning this off may reduce performance and stability if you have "
            "limited GPU VRAM, since the LLM can then stay resident in GPU memory alongside "
            "Stable Diffusion."
        ),
        "wdywfm_lmstudio_unload_ttl": shared.OptionInfo(
            20,
            "LM Studio idle TTL before auto-unload (seconds)",
            gr.Slider,
            {"minimum": 5, "maximum": 300, "step": 5},
            section=SECTION,
        ).info(
            "Only used when auto load/unload is enabled above."
        ),
        "wdywfm_sdxl_auto_unload": shared.OptionInfo(
            True,
            "Automatically unload the Stable Diffusion/SDXL checkpoint from GPU while querying LM Studio",
            section=SECTION,
        ).info(
            "Recommended: on. Frees all GPU VRAM for the local LLM while it answers; "
            "Forge reloads your checkpoint automatically the next time you press Generate. "
            "WARNING: turning this off may reduce performance and stability if you have "
            "limited GPU VRAM, since the SD/SDXL checkpoint then stays resident in GPU "
            "memory alongside the LLM."
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
