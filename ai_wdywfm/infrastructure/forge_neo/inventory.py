from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


MAX_ACTIVATION_WORDS = 24
MAX_ACTIVATION_WORD_LENGTH = 120
MAX_METADATA_BYTES = 256 * 1024
MAX_DETAILED_LORAS = 8
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def compatibility() -> tuple[bool, str]:
    try:
        import gradio
        import modules_forge  # noqa: F401
        major, minor = (int(part) for part in gradio.__version__.split(".")[:2])
        if (major, minor) < (4, 40):
            return False, f"Gradio {gradio.__version__} is older than Forge Neo's supported 4.40 runtime."
        return True, f"Forge Neo · Gradio {gradio.__version__}"
    except Exception as exc:
        return False, f"Incompatible runtime: {type(exc).__name__}"


def build_inventory(maximum_items: int = 80, query: str = "") -> dict[str, Any]:
    from modules import sd_models, shared, shared_items

    checkpoint_ids: list[str] = []
    checkpoint_summary: list[dict[str, str]] = []
    current_value = str(getattr(shared.opts, "sd_model_checkpoint", "") or "")
    current_id = None
    for key, item in sd_models.checkpoints_list.items():
        stable_id = str(key)
        checkpoint_ids.append(stable_id)
        title = str(getattr(item, "title", stable_id))
        checkpoint_summary.append({"id": stable_id, "title": title})
        names = {stable_id, title, str(getattr(item, "name", ""))}
        if current_value in names:
            current_id = stable_id

    lora_aliases: dict[str, str] = {}
    lora_triggers: dict[str, tuple[str, ...]] = {}
    lora_preferred_weights: dict[str, float] = {}
    lora_summary: list[dict[str, Any]] = []
    lora_details: list[dict[str, Any]] = []
    cache_before = _read_user_metadata_file.cache_info()
    try:
        from networks import available_networks

        for stable_id, item in available_networks.items():
            local_id = str(stable_id)
            alias = str(item.get_alias())
            lora_aliases[local_id] = alias
            user_metadata = _cached_user_metadata(str(item.filename))
            forge_metadata = item.metadata if isinstance(item.metadata, dict) else {}
            activation_words = _activation_words(user_metadata.get("activation text"))
            lora_triggers[local_id] = tuple(activation_words)
            card: dict[str, Any] = {"id": local_id, "alias": alias}
            base_model = (
                user_metadata.get("sd version")
                or forge_metadata.get("ss_base_model_version")
                or forge_metadata.get("modelspec.architecture")
            )
            if isinstance(base_model, str) and base_model.strip():
                card["base_model"] = _clean_text(base_model, 100)
            lora_summary.append(dict(card))
            if activation_words:
                card["activation_words"] = activation_words
            preferred_weight = _preferred_weight(user_metadata.get("preferred weight"))
            if preferred_weight is not None:
                card["preferred_weight"] = preferred_weight
                lora_preferred_weights[local_id] = preferred_weight
            if activation_words or "preferred_weight" in card:
                lora_details.append(card)
    except Exception:
        pass

    cache_after = _read_user_metadata_file.cache_info()
    ranked_details = _rank_lora_cards(lora_details, query)
    samplers = [str(item.name) for item in shared_items.list_samplers()]
    schedulers = [str(item) for item in shared_items.list_schedulers()]
    return {
        "current_checkpoint": current_id,
        "context": {
            "summary": {
                "checkpoints": checkpoint_summary[:maximum_items],
                "loras": lora_summary[:maximum_items],
                "truncated": len(checkpoint_summary) > maximum_items or len(lora_summary) > maximum_items,
            },
            "detailed_candidates": ranked_details[:min(MAX_DETAILED_LORAS, maximum_items)],
        },
        "constraints": {
            "allowed_checkpoint_ids": checkpoint_ids,
            "allowed_lora_ids": list(lora_aliases),
            "allowed_samplers": samplers,
            "allowed_schedulers": schedulers,
        },
        "lora_aliases": lora_aliases,
        "lora_triggers": lora_triggers,
        "lora_preferred_weights": lora_preferred_weights,
        "metadata_cache": {
            "hits": cache_after.hits - cache_before.hits,
            "misses": cache_after.misses - cache_before.misses,
            "entries": cache_after.currsize,
        },
    }


def unload_sd_checkpoint() -> bool:
    """Best-effort GPU VRAM release for the currently loaded SD/SDXL checkpoint.

    Mirrors the built-in Settings > Actions > "Unload SD checkpoint" button.
    Forge reloads the checkpoint lazily on the next txt2img/img2img run, so
    this is safe to call speculatively. Never raises; returns False if there
    was nothing to unload or the runtime does not support it.
    """
    try:
        from modules import sd_models

        current = sd_models.model_data.sd_model
        if current is None or isinstance(current, sd_models.FakeInitialModel):
            return False
        sd_models.unload_model_weights()
        return True
    except Exception:
        return False


def _cached_user_metadata(filename: str) -> dict[str, Any]:
    path = Path(filename).with_suffix(".json")
    try:
        stat = path.stat()
    except OSError:
        return {}
    if stat.st_size > MAX_METADATA_BYTES:
        return {}
    return _read_user_metadata_file(str(path), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=512)
def _read_user_metadata_file(
    path: str, mtime_ns: int, size: int,
) -> dict[str, Any]:
    del mtime_ns, size
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _rank_lora_cards(cards: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    terms = set(re.findall(r"[\w-]{3,}", (query or "").casefold()))

    def score(index_card: tuple[int, dict[str, Any]]) -> tuple[int, int]:
        index, card = index_card
        identity = f"{card.get('id', '')} {card.get('alias', '')}".casefold()
        activation = " ".join(card.get("activation_words", [])).casefold()
        identity_hits = sum(term in identity for term in terms)
        activation_hits = sum(term in activation for term in terms)
        return (identity_hits * 8 + activation_hits * 2, -index)

    indexed = list(enumerate(cards))
    indexed.sort(key=score, reverse=True)
    return [card for _, card in indexed]


def _activation_words(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    result = []
    seen = set()
    for raw in re.split(r"[,\r\n]+", value):
        word = _clean_text(raw, MAX_ACTIVATION_WORD_LENGTH)
        folded = word.casefold().replace("_", " ")
        if word and folded not in seen:
            seen.add(folded)
            result.append(word)
        if len(result) >= MAX_ACTIVATION_WORDS:
            break
    return result


def _preferred_weight(value: Any) -> float | None:
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if type(value) not in (int, float):
        return None
    result = float(value)
    return result if 0.05 <= abs(result) <= 2 else None


def _clean_text(value: str, maximum: int) -> str:
    return CONTROL_CHARS.sub(" ", value).strip()[:maximum].strip()
