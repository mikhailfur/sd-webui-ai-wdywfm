from __future__ import annotations

import base64
import ctypes
import json
import os
import threading
from ctypes import wintypes
from pathlib import Path
from typing import Any


STATE_VERSION = 1
MAX_STATE_BYTES = 64 * 1024
_STATE_LOCK = threading.RLock()
OPENROUTER_URL = "https://openrouter.ai/api/v1"


def load_provider_state(path: Path | None = None) -> dict[str, Any]:
    explicit_path = path is not None
    target = path or _default_path()
    with _STATE_LOCK:
        state = _load_provider_state(target)
        if not explicit_path:
            state = _merge_legacy_secret(state)
        return state


def _load_provider_state(target: Path) -> dict[str, Any]:
    state = _empty_state()
    try:
        if not target.is_file() or target.stat().st_size > MAX_STATE_BYTES:
            return state
        raw = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("version") != STATE_VERSION:
            return state
        selected = raw.get("selected_provider")
        if selected in {"LM Studio", "OpenRouter"}:
            state["selected_provider"] = selected
        providers = raw.get("providers")
        if isinstance(providers, dict):
            for name in ("LM Studio", "OpenRouter"):
                item = providers.get(name)
                if not isinstance(item, dict):
                    continue
                model = item.get("model")
                base_url = item.get("base_url")
                if isinstance(model, str):
                    state["providers"][name]["model"] = model[:1000]
                if isinstance(base_url, str):
                    state["providers"][name]["base_url"] = base_url[:2000]
        encrypted = raw.get("openrouter_key_dpapi")
        if isinstance(encrypted, str) and encrypted:
            state["providers"]["OpenRouter"]["api_key"] = _unprotect(encrypted)
    except Exception:
        return state
    state["providers"]["OpenRouter"]["base_url"] = _normalize_openrouter_url(
        state["providers"]["OpenRouter"]["base_url"]
    )
    return state


def save_provider_state(
    provider: str,
    model: str,
    base_url: str,
    api_key: str,
    path: Path | None = None,
) -> None:
    if provider not in {"LM Studio", "OpenRouter"}:
        return
    explicit_path = path is not None
    target = path or _default_path()
    with _STATE_LOCK:
        state = _load_provider_state(target)
        if not explicit_path:
            state = _merge_legacy_secret(state)
        state["selected_provider"] = provider
        state["providers"][provider]["model"] = str(model or "")[:1000]
        saved_url = str(base_url or "")[:2000]
        state["providers"][provider]["base_url"] = (
            _normalize_openrouter_url(saved_url)
            if provider == "OpenRouter"
            else saved_url
        )
        if provider == "OpenRouter":
            # Empty/stale UI events from the second Forge panel must not erase
            # an already persisted secret.
            if api_key:
                state["providers"]["OpenRouter"]["api_key"] = str(api_key)

        serialized = {
            "version": STATE_VERSION,
            "selected_provider": state["selected_provider"],
            "providers": {
                name: {"model": item["model"], "base_url": item["base_url"]}
                for name, item in state["providers"].items()
            },
            "openrouter_key_dpapi": _protect(
                state["providers"]["OpenRouter"]["api_key"]
            ) if state["providers"]["OpenRouter"]["api_key"] else "",
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(serialized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, target)


def _empty_state() -> dict[str, Any]:
    return {
        "selected_provider": "",
        "providers": {
            "LM Studio": {"model": "", "base_url": "", "api_key": ""},
            "OpenRouter": {"model": "", "base_url": OPENROUTER_URL, "api_key": ""},
        },
    }


def _default_path() -> Path:
    extension_root = Path(__file__).resolve().parents[2]
    return extension_root / "data" / "provider_state.v1.json"


def _legacy_path() -> Path | None:
    try:
        from modules.paths_internal import data_path

        return Path(data_path) / "ai-wdywfm" / "provider_state.v1.json"
    except ImportError:
        return None


def _merge_legacy_secret(state: dict[str, Any]) -> dict[str, Any]:
    if state["providers"]["OpenRouter"]["api_key"]:
        return state
    legacy = _legacy_path()
    if legacy is None or not legacy.is_file():
        return state
    legacy_state = _load_provider_state(legacy)
    legacy_key = legacy_state["providers"]["OpenRouter"]["api_key"]
    if legacy_key:
        state["providers"]["OpenRouter"]["api_key"] = legacy_key
    return state


def _normalize_openrouter_url(value: str) -> str:
    candidate = (value or "").strip().rstrip("/")
    if candidate.startswith("https://openrouter.ai/"):
        return candidate
    return OPENROUTER_URL


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _protect(value: str) -> str:
    if os.name != "nt":
        return ""
    raw = value.encode("utf-8")
    source_buffer = ctypes.create_string_buffer(raw)
    source = _DataBlob(len(raw), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = _DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)
    ):
        raise ctypes.WinError()
    try:
        return base64.b64encode(ctypes.string_at(output.pbData, output.cbData)).decode("ascii")
    finally:
        _local_free(output.pbData)


def _unprotect(value: str) -> str:
    if os.name != "nt":
        return ""
    raw = base64.b64decode(value, validate=True)
    source_buffer = ctypes.create_string_buffer(raw)
    source = _DataBlob(len(raw), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = _DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.pbData, output.cbData).decode("utf-8")
    finally:
        _local_free(output.pbData)


def _local_free(pointer) -> None:
    kernel32 = ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    kernel32.LocalFree(ctypes.cast(pointer, ctypes.c_void_p))
