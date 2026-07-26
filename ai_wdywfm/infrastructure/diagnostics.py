from __future__ import annotations

import logging
import os
import re
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOGGER_NAME = "ai_wdywfm"
_LOCK = threading.Lock()
_LOGGER: logging.Logger | None = None
_SECRET_PATTERNS = (
    re.compile(r"sk-or-v1-[A-Za-z0-9_-]+", re.IGNORECASE),
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,]+"),
    re.compile(r"(?i)(api[_ -]?key\s*[:=]\s*)[^\s,]+"),
)


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


def get_logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER
    with _LOCK:
        if _LOGGER is not None:
            return _LOGGER
        logger = logging.getLogger(LOGGER_NAME)
        logger.setLevel(logging.DEBUG if _debug_enabled() else logging.INFO)
        logger.propagate = False
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(threadName)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler.addFilter(_RedactingFilter())
        logger.addHandler(stream_handler)
        path = log_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            file_handler.addFilter(_RedactingFilter())
            logger.addHandler(file_handler)
            logger.info("logger.ready version=1 path=%s", path)
        except OSError as exc:
            logger.error(
                "logger.file_unavailable path=%s kind=%s",
                path, type(exc).__name__,
            )
        _LOGGER = logger
        return logger


def log_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "logs" / "ai-wdywfm.log"


def read_log_tail(max_lines: int = 160, max_bytes: int = 192 * 1024) -> str:
    path = log_path()
    if not path.is_file():
        return f"Log has not been created yet: {path}"
    try:
        with path.open("rb") as handle:
            size = path.stat().st_size
            handle.seek(max(0, size - max_bytes))
            raw = handle.read()
        lines = raw.decode("utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:])
    except OSError as exc:
        return f"Could not read log: {type(exc).__name__}"


def _debug_enabled() -> bool:
    if os.environ.get("WDYWFM_DEBUG", "").strip().lower() in {"1", "true", "yes"}:
        return True
    try:
        from modules import shared

        return bool(getattr(shared.opts, "wdywfm_debug_logging", False))
    except (ImportError, AttributeError):
        return False


def redact(value: str) -> str:
    result = value
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            result = pattern.sub(r"\1[REDACTED]", result)
        else:
            result = pattern.sub("[REDACTED]", result)
    return result
