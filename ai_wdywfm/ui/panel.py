from __future__ import annotations

import html
import threading
import time
import uuid
from typing import Any

import gradio as gr

from ai_wdywfm.application.apply_prompts import apply_prompt_fields
from ai_wdywfm.application.generate_suggestion import generate
from ai_wdywfm.application.recommend_loras import recommend_loras
from ai_wdywfm.domain.errors import WdywfmError, error_category
from ai_wdywfm.infrastructure.forge_neo.inventory import (
    build_inventory,
    compatibility,
    unload_sd_checkpoint,
)
from ai_wdywfm.infrastructure.diagnostics import (
    category_logger,
    get_logger,
    log_path,
    read_log_tail,
)
from ai_wdywfm.infrastructure.provider_state import load_provider_state, save_provider_state
from ai_wdywfm.infrastructure.providers.openai_compatible import OpenAICompatibleClient
from ai_wdywfm.infrastructure.providers.gemma4 import is_gemma4_model
from ai_wdywfm.ui.presenters import (
    model_note,
    recommendations_html,
    summary_markdown,
    warnings_markdown,
)
from ai_wdywfm.ui.settings import get_setting


OPENROUTER_URL = "https://openrouter.ai/api/v1"
LM_STUDIO_URL = "http://127.0.0.1:1234/v1"
_ACTIVE_CANCEL_EVENTS: dict[str, threading.Event] = {}
_ACTIVE_CANCEL_LOCK = threading.Lock()


def _timeout_for(provider: str) -> float:
    if provider == "LM Studio":
        return float(get_setting("wdywfm_timeout_lmstudio", 180))
    return float(get_setting("wdywfm_timeout", 60))


def _lmstudio_ttl(provider: str) -> int | None:
    if provider != "LM Studio":
        return None
    if not bool(get_setting("wdywfm_lmstudio_auto_unload", True)):
        return None
    return int(get_setting("wdywfm_lmstudio_unload_ttl", 20))


def _maybe_unload_sdxl(provider: str, request_id: str) -> bool:
    if provider != "LM Studio":
        return False
    if not bool(get_setting("wdywfm_sdxl_auto_unload", True)):
        return False
    freed = unload_sd_checkpoint()
    if freed:
        category_logger("ui").info(
            "request=%s sdxl.unloaded reason=lmstudio_request", request_id
        )
    return freed


def build_panel(*, is_img2img: bool, prompt_component, negative_component) -> None:
    mode = "img2img" if is_img2img else "txt2img"
    compatible, runtime = compatibility()
    saved_state = load_provider_state()
    default_provider = saved_state["selected_provider"] or str(
        get_setting("wdywfm_default_provider", "LM Studio")
    )
    saved_provider = saved_state["providers"][default_provider]
    default_model = saved_provider["model"] or _default_model(default_provider)
    default_url = saved_provider["base_url"] or _provider_url(default_provider)
    default_api_key = saved_provider["api_key"] if default_provider == "OpenRouter" else ""
    category_logger("ui").info(
        "ui.panel_build mode=%s provider=%s model_selected=%s runtime=%s",
        mode, default_provider, bool(default_model), runtime,
    )

    def generate_for_mode(*args):
        yield from _generate(mode, *args)

    def cancel_for_mode():
        return _cancel_request(mode)

    with gr.Accordion(
        "LLM Prompt Helper · AI WDYWFM",
        open=False,
        elem_id=f"wdywfm_{mode}",
        elem_classes=["wdywfm-panel"],
    ):
        suggestion_state = gr.State({})
        active_provider_state = gr.State(default_provider)
        gr.HTML(
            (
                '<div class="wdywfm-head">'
                '<div class="wdywfm-mark" aria-hidden="true"><i></i><i></i><i></i></div>'
                '<div><span class="wdywfm-kicker">PROMPT WORKBENCH</span>'
                f"<h3>Turn an idea into a verified {mode} draft.</h3></div>"
                f'<span class="wdywfm-runtime {"is-ok" if compatible else "is-bad"}">'
                f"{runtime}</span></div>"
                '<div class="wdywfm-route" aria-label="Workflow">'
                "<span>IDEA</span><b>→</b><span>VALIDATE</span><b>→</b><span>APPLY</span>"
                "</div>"
            )
        )

        with gr.Row(equal_height=False, elem_classes=["wdywfm-workspace"]):
            with gr.Column(scale=6, min_width=360):
                request = gr.Textbox(
                    label="What do you want?",
                    placeholder=(
                        "Describe the subject, mood, composition, and what must be preserved…"
                        if is_img2img else
                        "Example: A quiet ramen shop at midnight, rain on the window, cinematic framing…"
                    ),
                    lines=5,
                    max_lines=10,
                    elem_classes=["wdywfm-request"],
                )
                with gr.Row():
                    operation = gr.Radio(
                        ["Create", "Edit"],
                        value="Edit" if is_img2img else "Create",
                        label="Intent",
                        elem_classes=["wdywfm-compact"],
                    )
                    dialect = gr.Dropdown(
                        [
                            ("Auto", "auto"),
                            ("Booru tags", "booru"),
                            ("Natural language", "natural"),
                        ],
                        value="auto",
                        label="Prompt dialect",
                    )
                reference = gr.Image(
                    label="Reference image · optional",
                    type="pil",
                    height=190,
                    sources=["upload", "clipboard"],
                    elem_classes=["wdywfm-image"],
                )
            with gr.Column(scale=5, min_width=340):
                with gr.Row():
                    provider = gr.Dropdown(
                        ["LM Studio", "OpenRouter"],
                        value=default_provider,
                        label="Provider",
                        scale=2,
                    )
                    model = gr.Dropdown(
                        choices=[],
                        value=default_model or None,
                        allow_custom_value=True,
                        label="Model id",
                        scale=4,
                    )
                    refresh_models = gr.Button(
                        "Test",
                        size="sm",
                        variant="secondary",
                        min_width=62,
                        elem_classes=["wdywfm-refresh"],
                    )
                base_url = gr.Textbox(
                    value=default_url,
                    label="Provider base URL",
                    interactive=True,
                )
                api_key = gr.Textbox(
                    value=default_api_key,
                    label="OpenRouter API key · saved securely on this PC",
                    type="password",
                    visible=default_provider == "OpenRouter",
                    placeholder="Uses OPENROUTER_API_KEY when empty",
                )
                cloud_consent = gr.Checkbox(
                    label="Allow this reference image to be sent to OpenRouter",
                    value=False,
                    visible=default_provider == "OpenRouter",
                )
                web_search_consent = gr.Checkbox(
                    label="Allow this Generate to search character references on selected sites",
                    value=False,
                    interactive=True,
                )
                web_search_sources = gr.CheckboxGroup(
                    ["danbooru", "rule34", "e621", "wiki_fandom"],
                    value=_configured_search_sources(),
                    label="Character reference sources",
                    interactive=True,
                )
                disclosure = gr.Markdown(
                    _disclosure(default_provider),
                    elem_classes=["wdywfm-disclosure"],
                )
                with gr.Row():
                    generate_button = gr.Button(
                        "Generate verified draft",
                        variant="primary",
                        interactive=compatible,
                        scale=4,
                        elem_classes=["wdywfm-generate"],
                    )
                    cancel_button = gr.Button("Cancel", variant="stop", scale=1)
                activity = gr.Markdown(
                    "Ready. No request is sent until you press Generate.",
                    elem_classes=["wdywfm-activity"],
                    elem_id=f"wdywfm_activity_{mode}",
                )

        with gr.Group(elem_classes=["wdywfm-output"]):
            with gr.Row():
                summary = gr.Markdown(
                    "Your validated draft will appear here.",
                    elem_classes=["wdywfm-summary"],
                )
                model_status = gr.Markdown("", elem_classes=["wdywfm-model-note"])
            with gr.Row(equal_height=True):
                prompt_preview = gr.Textbox(
                    label="Positive prompt preview",
                    lines=5,
                    interactive=False,
                    show_copy_button=True,
                )
                negative_preview = gr.Textbox(
                    label="Negative prompt preview",
                    lines=5,
                    interactive=False,
                    show_copy_button=True,
                )
            with gr.Row(equal_height=False):
                with gr.Column(scale=3):
                    gr.Markdown("#### Read-only recommendations")
                    recommendations = gr.HTML(
                        '<div class="wdywfm-empty">Waiting for a validated response.</div>'
                    )
                with gr.Column(scale=2):
                    gr.Markdown("#### Validation notes")
                    warnings = gr.Markdown("—")

            with gr.Row(elem_classes=["wdywfm-actions"]):
                apply_mode = gr.Radio(
                    ["Replace", "Append"],
                    value="Replace",
                    label="Apply mode",
                    scale=3,
                )
                clear_button = gr.Button("Clear draft", variant="secondary", scale=1)
                apply_button = gr.Button(
                    "Apply prompts",
                    variant="primary",
                    scale=2,
                    elem_classes=["wdywfm-apply"],
                )

        recommender_enabled = bool(get_setting("wdywfm_civitai_recommender", True))
        with gr.Accordion(
            "LoRA recommender · CivitAI · read-only",
            open=False,
            elem_classes=["wdywfm-recommender"],
        ):
            gr.Markdown(
                "Searches CivitAI independently from prompt generation. Results are links and ids only; "
                "nothing is downloaded, installed, or added to a prompt."
            )
            with gr.Row():
                recommender_query = gr.Textbox(
                    label="What LoRA are you looking for?",
                    placeholder="Example: cinematic rain, neon city, anime character…",
                    scale=4,
                    interactive=recommender_enabled,
                )
                recommender_base = gr.Textbox(
                    label="Base model · optional",
                    placeholder="Illustrious, SDXL 1.0…",
                    scale=2,
                    interactive=recommender_enabled,
                )
            with gr.Row():
                recommender_nsfw = gr.Dropdown(
                    ["None", "Soft", "Mature", "X"],
                    value=str(get_setting("wdywfm_civitai_recommender_nsfw", "None")),
                    label="NSFW filter",
                )
                recommender_page = gr.Number(value=1, precision=0, minimum=1, label="Page")
                recommender_rerank = gr.Checkbox(
                    value=False,
                    label="Use selected LLM to re-rank these results",
                )
                recommender_button = gr.Button(
                    "Find LoRA", variant="secondary", interactive=recommender_enabled,
                )
            recommender_results = gr.HTML(
                '<div class="wdywfm-empty">'
                + ("Enter a description to search CivitAI." if recommender_enabled else
                   "The recommender is disabled in AI WDYWFM settings.")
                + "</div>"
            )

        with gr.Accordion(
            "Diagnostics · sanitized log",
            open=False,
            elem_classes=["wdywfm-diagnostics"],
        ):
            gr.Markdown(
                f"Log file: `{log_path()}` · prompts, images, and API keys are excluded."
            )
            with gr.Row():
                log_request_filter = gr.Textbox(
                    label="Request id filter", placeholder="Leave empty for all requests",
                )
                log_level_filter = gr.Dropdown(
                    ["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                    value="ALL", label="Level filter (exact)",
                )
                refresh_log = gr.Button("Refresh log", variant="secondary", size="sm")
            log_view = gr.Textbox(
                value=read_log_tail(),
                label="Latest events",
                lines=12,
                max_lines=20,
                interactive=False,
                show_copy_button=True,
                elem_classes=["wdywfm-log"],
            )

        provider.change(
            fn=_change_provider,
            inputs=[provider, active_provider_state, model, base_url, api_key],
            outputs=[
                base_url, api_key, cloud_consent, disclosure, model,
                active_provider_state,
            ],
            show_progress="hidden",
        )
        refresh_models.click(
            fn=_list_models,
            inputs=[provider, base_url, api_key],
            outputs=[model, activity, log_view],
        )
        generate_event = generate_button.click(
            fn=generate_for_mode,
            inputs=[
                provider, model, base_url, api_key, request, dialect, operation,
                reference, cloud_consent, web_search_consent, web_search_sources,
                prompt_component, negative_component,
            ],
            outputs=[
                suggestion_state, prompt_preview, negative_preview, summary,
                warnings, recommendations, model_status, activity, log_view,
            ],
            _js=(
                f"(...args) => {{ const root = document.querySelector('#wdywfm_activity_{mode}'); "
                "const text = root && root.querySelector('p'); "
                "if (text) text.textContent = 'Request accepted by UI · waiting for Python…'; "
                "return args; }"
            ),
        )
        cancel_button.click(
            fn=cancel_for_mode,
            inputs=[],
            outputs=[activity],
            cancels=[generate_event],
            queue=False,
        )
        model.input(
            fn=_auto_save,
            inputs=[provider, model, base_url, api_key],
            outputs=[activity],
            show_progress="hidden",
        )
        base_url.blur(
            fn=_auto_save,
            inputs=[provider, model, base_url, api_key],
            outputs=[activity],
            show_progress="hidden",
        )
        api_key.blur(
            fn=_auto_save,
            inputs=[provider, model, base_url, api_key],
            outputs=[activity],
            show_progress="hidden",
        )
        refresh_log.click(
            fn=_filtered_log,
            inputs=[log_request_filter, log_level_filter],
            outputs=[log_view],
            show_progress="hidden",
            queue=False,
        )
        recommender_button.click(
            fn=_recommend,
            inputs=[
                recommender_query, recommender_base, recommender_nsfw,
                recommender_page, recommender_rerank,
                provider, model, base_url, api_key,
            ],
            outputs=[recommender_results],
        )
        apply_button.click(
            fn=_apply,
            inputs=[suggestion_state, prompt_component, negative_component, apply_mode],
            outputs=[prompt_component, negative_component],
        )
        clear_button.click(
            fn=_clear,
            inputs=[],
            outputs=[
                suggestion_state, prompt_preview, negative_preview, summary,
                warnings, recommendations, model_status, activity,
            ],
            show_progress="hidden",
        )


def _generate(
    mode: str,
    provider: str,
    model: str,
    base_url: str,
    api_key: str,
    request: str,
    dialect: str,
    operation: str,
    reference: Any,
    cloud_consent: bool,
    web_search_consent: bool,
    web_search_sources: list[str],
    current_prompt: str,
    current_negative: str,
):
    request_id = uuid.uuid4().hex[:12]
    cancel_event = _begin_request(mode)
    started = time.perf_counter()
    logger = category_logger("ui")
    logger.info(
        "request=%s ui.generate mode=%s provider=%s model=%s vision=%s search=%s key_present=%s request_chars=%d",
        request_id, mode, provider, model or "none", reference is not None,
        bool(web_search_consent), bool(api_key), len(request or ""),
    )
    _save_safely(provider, model, base_url, api_key)
    yield _activity_update(
        f"Request `{request_id}` · preparing local model context…"
    )
    try:
        civitai_domain = str(get_setting("wdywfm_civitai_domain", "civitai.com"))
        inventory = build_inventory(
            int(get_setting("wdywfm_inventory_limit", 80)),
            f"{request or ''} {current_prompt or ''}",
            enrich_civitai=bool(get_setting("wdywfm_civitai_enrichment", True)),
            civitai_base_url=f"https://{civitai_domain}/api/v1",
            civitai_timeout=float(get_setting("wdywfm_civitai_timeout", 15)),
            request_id=request_id,
        )
        constraints = inventory.get("constraints", {})
        metadata_cache = inventory.get("metadata_cache", {})
        category_logger("inventory").info(
            "request=%s inventory.ok checkpoints=%d loras=%d metadata_loras=%d activation_words=%d cache_hits=%d cache_misses=%d cache_entries=%d samplers=%d schedulers=%d",
            request_id,
            len(constraints.get("allowed_checkpoint_ids", [])),
            len(constraints.get("allowed_lora_ids", [])),
            sum(bool(words) for words in inventory.get("lora_triggers", {}).values()),
            sum(len(words) for words in inventory.get("lora_triggers", {}).values()),
            metadata_cache.get("hits", 0),
            metadata_cache.get("misses", 0),
            metadata_cache.get("entries", 0),
            len(constraints.get("allowed_samplers", [])),
            len(constraints.get("allowed_schedulers", [])),
        )
        sdxl_freed = _maybe_unload_sdxl(provider, request_id)
        yield _activity_update(
            f"Request `{request_id}` · "
            f"{'Gemma 4 fast profile · ' if is_gemma4_model(model or '') else ''}"
            f"{'SD checkpoint unloaded, ' if sdxl_freed else ''}"
            f"waiting for {provider} "
            f"(timeout {_timeout_for(provider):g}s)…"
        )
        suggestion = generate(
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
            user_text=request,
            dialect=dialect,
            operation=operation,
            mode=mode,
            current_prompt=current_prompt,
            current_negative=current_negative,
            image=reference,
            cloud_image_consent=cloud_consent,
            inventory=inventory,
            timeout=_timeout_for(provider),
            thinking_budget=int(get_setting("wdywfm_thinking_budget", 2048)),
            image_max_side=int(get_setting("wdywfm_image_max_side", 1536)),
            request_id=request_id,
            cancel_event=cancel_event,
            lmstudio_ttl=_lmstudio_ttl(provider),
            web_search_enabled=bool(web_search_consent),
            web_search_sources=web_search_sources or (),
            web_search_timeout=float(get_setting("wdywfm_web_search_timeout", 10)),
        )
    except WdywfmError as exc:
        logger.warning(
            "request=%s failed duration=%.3fs kind=%s error_category=%s message=%s",
            request_id, time.perf_counter() - started, type(exc).__name__,
            error_category(exc), str(exc),
        )
        gr.Warning(str(exc))
        _finish_request(mode, cancel_event)
        yield _activity_update(f"Request `{request_id}` failed: **{exc}**")
        return
    except Exception as exc:
        logger.exception(
            "request=%s crashed duration=%.3fs kind=%s error_category=internal",
            request_id, time.perf_counter() - started, type(exc).__name__,
        )
        gr.Warning(f"Internal error ({request_id}). Open Diagnostics for details.")
        _finish_request(mode, cancel_event)
        yield _activity_update(
            f"Request `{request_id}` crashed. Open **Diagnostics** and copy the log."
        )
        return
    logger.info(
        "request=%s validated duration=%.3fs prompt_chars=%d negative_chars=%d warnings=%d",
        request_id, time.perf_counter() - started, len(suggestion.prompt),
        len(suggestion.negative_prompt), len(suggestion.warnings),
    )
    _finish_request(mode, cancel_event)
    yield (
        suggestion.to_state(),
        suggestion.prompt,
        suggestion.negative_prompt,
        summary_markdown(suggestion),
        warnings_markdown(suggestion),
        recommendations_html(suggestion),
        model_note(suggestion, inventory.get("metadata_statuses", {})),
        f"Request `{request_id}` validated. Review it, then apply explicitly.",
        read_log_tail(),
    )


def _apply(state, current_prompt, current_negative, apply_mode):
    try:
        result = apply_prompt_fields(state, current_prompt or "", current_negative or "", apply_mode)
    except WdywfmError as exc:
        get_logger().warning("ui.apply_failed kind=%s", type(exc).__name__)
        raise gr.Error(str(exc)) from exc
    get_logger().info(
        "ui.apply mode=%s prompt_chars=%d negative_chars=%d",
        apply_mode, len(result[0]), len(result[1]),
    )
    gr.Info("Applied positive and negative prompts only.")
    return result


def _list_models(provider: str, base_url: str, api_key: str):
    request_id = f"test-{uuid.uuid4().hex[:8]}"
    logger = get_logger()
    logger.info(
        "request=%s ui.test_provider provider=%s key_present=%s",
        request_id, provider, bool(api_key),
    )
    try:
        client = OpenAICompatibleClient(
            provider=provider,
            base_url=base_url,
            api_key=api_key,
            timeout=min(_timeout_for(provider), 30),
            request_id=request_id,
        )
        models = client.list_models()
    except WdywfmError as exc:
        raise gr.Error(str(exc)) from exc
    value = _default_model(provider)
    if value not in models:
        value = models[0] if models else None
    return (
        gr.Dropdown(choices=models, value=value),
        f"Provider test passed · found {len(models)} models · `{request_id}`.",
        read_log_tail(),
    )


def _change_provider(
    provider: str,
    previous_provider: str,
    previous_model: str,
    previous_url: str,
    previous_key: str,
):
    get_logger().info(
        "ui.provider_change previous=%s selected=%s", previous_provider, provider
    )
    _save_safely(
        previous_provider,
        previous_model,
        previous_url,
        previous_key,
    )
    is_openrouter = provider == "OpenRouter"
    saved = load_provider_state()["providers"][provider]
    url = saved["base_url"] or _provider_url(provider)
    model = saved["model"] or _default_model(provider)
    key = saved["api_key"] if is_openrouter else ""
    _save_safely(provider, model, url, key)
    return (
        gr.Textbox(value=url, interactive=True),
        gr.Textbox(visible=is_openrouter, value=key),
        gr.Checkbox(visible=is_openrouter, value=False),
        _disclosure(provider),
        gr.Dropdown(value=model or None, choices=[]),
        provider,
    )


def _clear():
    get_logger().info("ui.draft_clear")
    return (
        {},
        "",
        "",
        "Your validated draft will appear here.",
        "—",
        '<div class="wdywfm-empty">Waiting for a validated response.</div>',
        "",
        "Draft cleared. Your Forge prompts were not changed.",
    )


def _provider_url(provider: str) -> str:
    if provider == "OpenRouter":
        return OPENROUTER_URL
    return str(get_setting("wdywfm_lmstudio_url", LM_STUDIO_URL))


def _default_model(provider: str) -> str:
    key = "wdywfm_openrouter_model" if provider == "OpenRouter" else "wdywfm_lmstudio_model"
    return str(get_setting(key, "") or "")


def _disclosure(provider: str) -> str:
    if provider == "OpenRouter":
        source = "API key, request text, compact local model names, and a consented image"
        destination = "OpenRouter"
    else:
        source = "Request text, compact local model names, and the optional image"
        destination = "your loopback LM Studio server"
    persistence = " The provider state is saved automatically; on Windows the key is protected with DPAPI."
    metadata = (
        " When CivitAI enrichment is enabled, shortlisted model hashes/ids may be sent to the selected CivitAI domain."
    )
    search = (
        " Character web search requires per-Generate consent; when enabled, "
        "the character/franchise query is sent only to the selected Danbooru, Rule34, e621, or Fandom APIs."
    )
    return (
        f"**Privacy:** {source} will be sent to {destination}. Absolute paths are excluded."
        f"{metadata}{search}{persistence}"
    )


def _auto_save(provider: str, model: str, base_url: str, api_key: str) -> str:
    if _save_safely(provider, model, base_url, api_key):
        return "Provider settings saved automatically."
    return "Could not save provider settings; generation is still available."


def _save_safely(provider: str, model: str, base_url: str, api_key: str) -> bool:
    try:
        save_provider_state(provider, model or "", base_url or "", api_key or "")
        return True
    except Exception as exc:
        get_logger().warning("state.save_failed kind=%s", type(exc).__name__)
        return False


def _activity_update(message: str):
    return (gr.skip(),) * 7 + (message, read_log_tail())


def _begin_request(mode: str) -> threading.Event:
    event = threading.Event()
    with _ACTIVE_CANCEL_LOCK:
        previous = _ACTIVE_CANCEL_EVENTS.get(mode)
        if previous is not None:
            previous.set()
        _ACTIVE_CANCEL_EVENTS[mode] = event
    return event


def _finish_request(mode: str, event: threading.Event) -> None:
    with _ACTIVE_CANCEL_LOCK:
        if _ACTIVE_CANCEL_EVENTS.get(mode) is event:
            _ACTIVE_CANCEL_EVENTS.pop(mode, None)


def _cancel_request(mode: str) -> str:
    with _ACTIVE_CANCEL_LOCK:
        event = _ACTIVE_CANCEL_EVENTS.get(mode)
        if event is not None:
            event.set()
    category_logger("ui").info(
        "ui.cancel_requested mode=%s active=%s error_category=cancelled",
        mode, event is not None,
    )
    return (
        "Cancellation requested. The previous draft was kept."
        if event is not None else
        "No active request."
    )


def _configured_search_sources() -> list[str]:
    raw = str(get_setting(
        "wdywfm_web_search_sources",
        "danbooru,rule34,e621,wiki_fandom",
    ))
    allowed = {"danbooru", "rule34", "e621", "wiki_fandom"}
    return [
        item for item in (part.strip().lower() for part in raw.split(","))
        if item in allowed
    ]


def _filtered_log(request_id: str, level: str) -> str:
    return read_log_tail(request_filter=request_id or "", level_filter=level or "ALL")


def _recommend(
    query: str,
    base_model: str,
    nsfw: str,
    page: float,
    use_rerank: bool,
    provider: str,
    model: str,
    provider_base_url: str,
    api_key: str,
) -> str:
    request_id = f"rec-{uuid.uuid4().hex[:8]}"
    domain = str(get_setting("wdywfm_civitai_domain", "civitai.com"))
    try:
        llm_client = None
        if use_rerank:
            llm_client = OpenAICompatibleClient(
                provider=provider, base_url=provider_base_url, api_key=api_key,
                timeout=_timeout_for(provider), request_id=request_id,
            )
        result = recommend_loras(
            query,
            base_url=f"https://{domain}/api/v1",
            timeout=float(get_setting("wdywfm_civitai_timeout", 15)),
            nsfw=nsfw or "None",
            base_model=base_model or "",
            page=max(1, int(page or 1)),
            limit=int(get_setting("wdywfm_civitai_recommender_limit", 12)),
            request_id=request_id,
            llm_client=llm_client,
            llm_model=model or "",
        )
    except WdywfmError as exc:
        category_logger("civitai").warning(
            "request=%s recommender.failed kind=%s error_category=%s",
            request_id, type(exc).__name__, error_category(exc),
        )
        return (
            '<div class="wdywfm-empty">CivitAI is unavailable. '
            "The main prompt workflow is unaffected.</div>"
        )
    items = result.get("items", [])
    if not items:
        return '<div class="wdywfm-empty">No matching LoRA found.</div>'
    cards = []
    for item in items:
        name = html.escape(str(item["name"]))
        creator = html.escape(str(item["creator"]))
        base = html.escape(str(item.get("base_model") or "unspecified"))
        page_url = html.escape(str(item["page_url"]), quote=True)
        preview = item.get("preview_url")
        preview_link = (
            f' · <a href="{html.escape(str(preview), quote=True)}" target="_blank" '
            'rel="noopener noreferrer">preview</a>'
            if preview else ""
        )
        cards.append(
            '<div class="wdywfm-rec-card">'
            f'<a href="{page_url}" target="_blank" rel="noopener noreferrer"><b>{name}</b></a>'
            f" · by {creator} · {base}<br>"
            f"<code>model:{item['model_id']}</code>"
            + (
                f" · <code>version:{item['version_id']}</code>"
                if item.get("version_id") is not None else ""
            )
            + preview_link
            + "</div>"
        )
    return "".join(cards)
