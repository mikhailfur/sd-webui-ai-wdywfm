from __future__ import annotations

from modules import script_callbacks, scripts

from ai_wdywfm.ui.panel import build_panel
from ai_wdywfm.ui.settings import register_settings
from ai_wdywfm.infrastructure.diagnostics import get_logger


PROMPT_COMPONENTS = {}
TARGET_IDS = {
    "txt2img_prompt",
    "txt2img_neg_prompt",
    "img2img_prompt",
    "img2img_neg_prompt",
}
LOGGER = get_logger()
LOGGER.info("extension.entrypoint_loaded")


def capture_prompt_component(component, **kwargs) -> None:
    elem_id = kwargs.get("elem_id") or getattr(component, "elem_id", None)
    if elem_id in TARGET_IDS:
        PROMPT_COMPONENTS[elem_id] = component
        LOGGER.info("ui.component_captured elem_id=%s", elem_id)


class Script(scripts.Script):
    def title(self):
        return "LLM Prompt Helper"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        prefix = "img2img" if is_img2img else "txt2img"
        prompt = PROMPT_COMPONENTS.get(f"{prefix}_prompt")
        negative = PROMPT_COMPONENTS.get(f"{prefix}_neg_prompt")
        if prompt is None or negative is None:
            LOGGER.error("ui.component_capture_failed prefix=%s", prefix)
            return []
        build_panel(
            is_img2img=is_img2img,
            prompt_component=prompt,
            negative_component=negative,
        )
        return []


script_callbacks.on_after_component(capture_prompt_component)
script_callbacks.on_ui_settings(register_settings)
