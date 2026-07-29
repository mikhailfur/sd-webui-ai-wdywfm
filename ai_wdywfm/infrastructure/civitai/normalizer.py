from __future__ import annotations

import html
import json
import re
from dataclasses import replace
from html.parser import HTMLParser
from typing import Any, Iterable

from ai_wdywfm.domain.models import ModelMetadata


MAX_DESCRIPTION_CHARS = 12_000
MAX_PROMPT_CHARS = 2_000
MAX_PROMPTS = 12
MAX_TRIGGER_WORDS = 48
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
WHITESPACE = re.compile(r"[ \t]+")


class _PlainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        del attrs
        if tag in {"script", "style"}:
            self._ignored += 1
        elif tag in {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._ignored:
            self._ignored -= 1
        elif tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored:
            self.parts.append(data)


def sanitize_html(value: Any, maximum: int = MAX_DESCRIPTION_CHARS) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parser = _PlainTextParser()
    try:
        parser.feed(value)
        text = "".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]*>", " ", value)
    text = CONTROL_CHARS.sub(" ", html.unescape(text))
    lines = [WHITESPACE.sub(" ", line).strip() for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line).strip()
    return cleaned[:maximum].strip() or None


def normalize_metadata(
    *,
    local_id: str,
    kind: str,
    display_name: str,
    local_sidecar: dict[str, Any] | None = None,
    api_info: dict[str, Any] | None = None,
    safetensors: dict[str, Any] | None = None,
    version_response: dict[str, Any] | None = None,
    model_response: dict[str, Any] | None = None,
    forge_metadata: dict[str, Any] | None = None,
) -> ModelMetadata:
    local = local_sidecar or {}
    api = api_info or {}
    safe = safetensors or {}
    version = version_response or {}
    model = model_response or {}
    forge = forge_metadata or {}
    provenance: dict[str, str] = {}

    model_id = _integer(local.get("modelId"))
    version_id = _integer(local.get("modelVersionId"))
    sha256 = _hash(local.get("sha256"))
    identity_source = "sidecar" if any((model_id, version_id, sha256)) else ""
    if model_id is None:
        model_id = _integer(api.get("modelId")) or _integer(version.get("modelId")) or _integer(model.get("id"))
        identity_source = "api_info" if _integer(api.get("modelId")) else "civitai"
    if version_id is None:
        version_id = _integer(api.get("id")) or _integer(version.get("id"))
        identity_source = identity_source or ("api_info" if _integer(api.get("id")) else "civitai")
    if sha256 is None:
        sha256 = _first_file_hash(api) or _first_file_hash(version) or _hash(
            forge.get("sha256") or forge.get("sshs_model_hash")
        )
        if sha256:
            identity_source = identity_source or ("api_info" if _first_file_hash(api) else "forge")
    if identity_source:
        provenance["identity"] = identity_source

    groups: list[list[str]] = []
    safe_triggers = _safetensors_triggers(safe)
    _add_groups(groups, safe_triggers)
    _add_groups(groups, local.get("activation text groups"))
    _add_groups(groups, local.get("activation text"))
    _add_groups(groups, api.get("trainedWords"))
    _add_groups(groups, version.get("trainedWords"))
    if groups:
        provenance["triggers"] = (
            "safetensors+local+civitai" if safe_triggers else
            "sidecar+civitai" if local.get("activation text") or local.get("activation text groups") else
            "civitai"
        )

    description = (
        sanitize_html(version.get("description"))
        or sanitize_html(api.get("description"))
        or sanitize_html(model.get("description"))
    )
    if description:
        provenance["description"] = (
            "civitai_version" if version.get("description") else
            "api_info" if api.get("description") else "civitai_model"
        )

    base_model = _text(local.get("sd version"), 120)
    base_source = "sidecar" if base_model else ""
    if not base_model:
        base_model = _text(api.get("baseModel"), 120)
        base_source = "api_info" if base_model else ""
    if not base_model:
        base_model = _text(version.get("baseModel"), 120)
        base_source = "civitai" if base_model else ""
    if not base_model:
        base_model = _text(
            forge.get("ss_base_model_version")
            or forge.get("modelspec.architecture")
            or safe.get("ss_base_model_version")
            or safe.get("modelspec.architecture"),
            120,
        )
        base_source = "forge" if base_model else ""
    if base_source:
        provenance["base_model"] = base_source

    sample_prompts, negative_prompts = _sample_prompts(api, version, model)
    if sample_prompts or negative_prompts:
        provenance["examples"] = "api_info" if api.get("images") else "civitai"
    tags = _strings(model.get("tags"), 80, 120)
    preferred_weight = _weight(
        local.get("preferred weight")
        or api.get("preferredWeight")
        or version.get("preferredWeight")
    )
    return ModelMetadata(
        local_id=local_id,
        kind=kind,
        display_name=display_name,
        base_model=base_model,
        civitai_model_id=model_id,
        civitai_version_id=version_id,
        sha256=sha256,
        trigger_word_groups=tuple(tuple(group) for group in groups),
        description_text=description,
        sample_prompts=sample_prompts,
        negative_prompts=negative_prompts,
        tags=tags,
        preferred_weight=preferred_weight,
        provenance=provenance,
    )


def merge_metadata(primary: ModelMetadata, fallback: ModelMetadata) -> ModelMetadata:
    """Merge by field, preserving more specific/fresh values from ``primary``."""
    groups: list[list[str]] = []
    _add_groups(groups, primary.trigger_word_groups)
    _add_groups(groups, fallback.trigger_word_groups)
    provenance = dict(fallback.provenance)
    provenance.update(primary.provenance)
    return replace(
        primary,
        base_model=primary.base_model or fallback.base_model,
        civitai_model_id=primary.civitai_model_id or fallback.civitai_model_id,
        civitai_version_id=primary.civitai_version_id or fallback.civitai_version_id,
        sha256=primary.sha256 or fallback.sha256,
        trigger_word_groups=tuple(tuple(group) for group in groups),
        description_text=primary.description_text or fallback.description_text,
        sample_prompts=primary.sample_prompts or fallback.sample_prompts,
        negative_prompts=primary.negative_prompts or fallback.negative_prompts,
        tags=primary.tags or fallback.tags,
        preferred_weight=primary.preferred_weight or fallback.preferred_weight,
        provenance=provenance,
    )


def _add_groups(target: list[list[str]], value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str):
        candidates: Iterable[Any] = [re.split(r"[,\r\n]+", value)]
    elif isinstance(value, dict):
        candidates = value.values()
    elif isinstance(value, (list, tuple)):
        if all(isinstance(item, str) for item in value):
            candidates = value if any(re.search(r"[,\r\n]", item) for item in value) else [value]
        else:
            candidates = value
    else:
        return
    seen = {word.casefold().replace("_", " ") for group in target for word in group}
    for candidate in candidates:
        if isinstance(candidate, str):
            candidate = re.split(r"[,\r\n]+", candidate)
        if not isinstance(candidate, (list, tuple)):
            continue
        group: list[str] = []
        for raw in candidate:
            word = _text(raw, 160)
            key = word.casefold().replace("_", " ") if word else ""
            if word and key not in seen:
                seen.add(key)
                group.append(word)
            if sum(len(item) for item in target) + len(group) >= MAX_TRIGGER_WORDS:
                break
        if group:
            target.append(group)


def _safetensors_triggers(metadata: dict[str, Any]) -> list[str]:
    value = metadata.get("ss_tag_frequency")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            value = None
    if not isinstance(value, dict):
        return []
    scored: dict[str, float] = {}
    for bucket in value.values():
        if not isinstance(bucket, dict):
            continue
        for word, count in bucket.items():
            if isinstance(word, str) and type(count) in (int, float):
                scored[word] = scored.get(word, 0) + float(count)
    return [item[0] for item in sorted(scored.items(), key=lambda item: item[1], reverse=True)[:24]]


def _sample_prompts(*sources: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    prompts: list[str] = []
    negatives: list[str] = []
    seen: set[str] = set()
    for source in sources:
        images = source.get("images")
        if not isinstance(images, list):
            continue
        for image in images:
            meta = image.get("meta") if isinstance(image, dict) else None
            if not isinstance(meta, dict):
                continue
            for key, target in (("prompt", prompts), ("negativePrompt", negatives)):
                value = sanitize_html(meta.get(key), MAX_PROMPT_CHARS)
                folded = value.casefold() if value else ""
                if value and folded not in seen and len(target) < MAX_PROMPTS:
                    seen.add(folded)
                    target.append(value)
    return tuple(prompts), tuple(negatives)


def _first_file_hash(source: dict[str, Any]) -> str | None:
    files = source.get("files")
    if not isinstance(files, list):
        return None
    for item in files:
        hashes = item.get("hashes") if isinstance(item, dict) else None
        if isinstance(hashes, dict):
            value = _hash(hashes.get("SHA256") or hashes.get("sha256"))
            if value:
                return value
    return None


def _strings(value: Any, maximum_items: int, maximum_chars: int) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(text for item in value[:maximum_items] if (text := _text(item, maximum_chars)))


def _text(value: Any, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    result = CONTROL_CHARS.sub(" ", value).strip()[:maximum].strip()
    return result or None


def _integer(value: Any) -> int | None:
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    return value if type(value) is int and value > 0 else None


def _hash(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    result = value.strip().upper()
    return result if re.fullmatch(r"[A-F0-9]{8,64}", result) else None


def _weight(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if 0.05 <= abs(result) <= 2.0 else None
