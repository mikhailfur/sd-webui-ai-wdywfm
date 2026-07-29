from __future__ import annotations

import json
import struct
from functools import lru_cache
from pathlib import Path
from typing import Any

from ai_wdywfm.domain.models import ModelMetadata
from ai_wdywfm.infrastructure.civitai.normalizer import normalize_metadata


MAX_SIDECAR_BYTES = 2 * 1024 * 1024
MAX_SAFETENSORS_HEADER_BYTES = 16 * 1024 * 1024


def resolve_local_metadata(
    model_path: str | Path,
    *,
    local_id: str,
    kind: str,
    display_name: str,
    forge_metadata: dict[str, Any] | None = None,
) -> ModelMetadata:
    path = Path(model_path)
    api_info = _read_json_candidate(path.with_suffix(".api_info.json"))
    local = _read_json_candidate(path.with_suffix(".json"))
    safe = read_safetensors_metadata(path)
    return normalize_metadata(
        local_id=local_id,
        kind=kind,
        display_name=display_name,
        local_sidecar=local,
        api_info=api_info,
        safetensors=safe,
        forge_metadata=forge_metadata,
    )


def read_safetensors_metadata(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if target.suffix.casefold() != ".safetensors":
        return {}
    try:
        stat = target.stat()
    except OSError:
        return {}
    return _read_safetensors_metadata(str(target), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=256)
def _read_safetensors_metadata(path: str, mtime_ns: int, size: int) -> dict[str, Any]:
    del mtime_ns
    if size < 10:
        return {}
    try:
        with Path(path).open("rb") as handle:
            raw_length = handle.read(8)
            if len(raw_length) != 8:
                return {}
            header_length = struct.unpack("<Q", raw_length)[0]
            if not 2 <= header_length <= MAX_SAFETENSORS_HEADER_BYTES:
                return {}
            raw = handle.read(header_length)
        header = json.loads(raw.decode("utf-8"))
        metadata = header.get("__metadata__") if isinstance(header, dict) else None
        return metadata if isinstance(metadata, dict) else {}
    except (OSError, UnicodeDecodeError, ValueError, struct.error):
        return {}


def _read_json_candidate(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except OSError:
        return {}
    if stat.st_size > MAX_SIDECAR_BYTES:
        return {}
    return _read_json(str(path), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=512)
def _read_json(path: str, mtime_ns: int, size: int) -> dict[str, Any]:
    del mtime_ns, size
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, UnicodeDecodeError, ValueError):
        return {}
