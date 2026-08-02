from __future__ import annotations

import logging
import json
import os
import re
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


LOGGER_NAME = "ai_wdywfm"
_LOCK = threading.Lock()
_LOGGER: logging.Logger | None = None
_LEVELS = {"OFF": 100, "ERROR": logging.ERROR, "WARNING": logging.WARNING,
           "INFO": logging.INFO, "DEBUG": logging.DEBUG}
_SECRET_PATTERNS = (
    re.compile(r"sk-or-v1-[A-Za-z0-9_-]+", re.IGNORECASE),
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,]+"),
    re.compile(r"(?i)(api[_ -]?key\s*[:=]\s*)[^\s,]+"),
)


class _CategoryAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = kwargs.setdefault("extra", {})
        extra.setdefault("category", self.extra["category"])
        return msg, kwargs


class _RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        if isinstance(record.args, tuple):
            record.args = tuple(redact(item) if isinstance(item, str) else item for item in record.args)
        elif isinstance(record.args, dict):
            record.args = {
                key: redact(value) if isinstance(value, str) else value
                for key, value in record.args.items()
            }
        return True


class _CategoryFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        category = getattr(record, "category", "core")
        threshold = _category_level(category)
        return record.levelno >= threshold


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = redact(record.getMessage())
        value = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "category": getattr(record, "category", "core"),
            "thread": record.threadName,
            "message": message,
        }
        match = re.search(r"(?:^|\s)request=([^\s]+)", message)
        if match:
            value["request"] = match.group(1)
        if record.exc_info:
            value["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def get_logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER
    with _LOCK:
        if _LOGGER is not None:
            return _LOGGER
        logger = logging.getLogger(LOGGER_NAME)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(category)s | %(threadName)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            defaults={"category": "core"},
        )
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler.addFilter(_RedactingFilter())
        stream_handler.addFilter(_CategoryFilter())
        logger.addHandler(stream_handler)
        path = log_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
            file_handler.setFormatter(_JsonFormatter() if _jsonl_enabled() else formatter)
            file_handler.addFilter(_RedactingFilter())
            file_handler.addFilter(_CategoryFilter())
            logger.addHandler(file_handler)
            logger.info(
                "logger.ready version=2 path=%s format=%s",
                path, "jsonl" if _jsonl_enabled() else "key_value",
                extra={"category": "core"},
            )
        except OSError as exc:
            logger.error(
                "logger.file_unavailable path=%s kind=%s",
                path, type(exc).__name__,
            )
        _LOGGER = logger
        return logger


def category_logger(category: str) -> logging.LoggerAdapter:
    """Logger with a stable subsystem category used by per-category verbosity."""
    return _CategoryAdapter(get_logger(), {"category": category})


def log_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "logs" / "ai-wdywfm.log"


def read_log_tail(
    max_lines: int = 160,
    max_bytes: int = 192 * 1024,
    request_filter: str = "",
    level_filter: str = "ALL",
) -> str:
    path = log_path()
    if not path.is_file():
        return f"Log has not been created yet: {path}"
    try:
        with path.open("rb") as handle:
            size = path.stat().st_size
            handle.seek(max(0, size - max_bytes))
            raw = handle.read()
        lines = raw.decode("utf-8", errors="replace").splitlines()
        request_filter = (request_filter or "").strip()
        level_filter = (level_filter or "ALL").strip().upper()
        if request_filter:
            lines = [line for line in lines if _line_request(line) == request_filter]
        if level_filter != "ALL":
            lines = [line for line in lines if _line_level(line) == level_filter]
        return "\n".join(lines[-max_lines:])
    except OSError as exc:
        return f"Could not read log: {type(exc).__name__}"


def _debug_enabled() -> bool:
    return os.environ.get("WDYWFM_DEBUG", "").strip().lower() in {"1", "true", "yes"}


def _jsonl_enabled() -> bool:
    return os.environ.get("WDYWFM_LOG_JSONL", "").strip().lower() in {"1", "true", "yes"}


def _category_level(category: str) -> int:
    env_name = "WDYWFM_LOG_" + re.sub(r"[^A-Z0-9]+", "_", category.upper())
    value = os.environ.get(env_name)
    if not value:
        value = "DEFAULT"
    if str(value).strip().upper() == "DEFAULT":
        return logging.DEBUG if _debug_enabled() else logging.INFO
    return _LEVELS.get(str(value).strip().upper(), logging.INFO)


def _line_request(line: str) -> str:
    try:
        value = json.loads(line)
        return str(value.get("request", "")) if isinstance(value, dict) else ""
    except ValueError:
        match = re.search(r"(?:^|\s)request=([^\s]+)", line)
        return match.group(1) if match else ""


def _line_level(line: str) -> str:
    try:
        value = json.loads(line)
        return str(value.get("level", "")).upper() if isinstance(value, dict) else ""
    except ValueError:
        match = re.search(r"\|\s*(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s*\|", line)
        return match.group(1) if match else ""


def envelope_debug_summary(envelope: dict[str, Any]) -> str:
    """Return a prompt-free JSON summary of model ids actually sent to the LLM."""
    context = envelope.get("installed_models")
    context = context if isinstance(context, dict) else {}
    summary = context.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    checkpoints = summary.get("checkpoints") if isinstance(summary.get("checkpoints"), list) else []
    loras = summary.get("loras") if isinstance(summary.get("loras"), list) else []
    details = context.get("detailed_candidates")
    details = details if isinstance(details, list) else []
    value = {
        "checkpoint_ids": [item.get("id") for item in checkpoints if isinstance(item, dict)],
        "compact_lora_ids": [item.get("id") for item in loras if isinstance(item, dict)],
        "detailed_lora_ids": [item.get("id") for item in details if isinstance(item, dict)],
        "truncated": bool(summary.get("truncated")),
    }
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def redact(value: str) -> str:
    result = value
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            result = pattern.sub(r"\1[REDACTED]", result)
        else:
            result = pattern.sub("[REDACTED]", result)
    return result
