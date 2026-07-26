from __future__ import annotations

import json
import os
import queue
import threading
import time
from typing import Any
from urllib.parse import urlparse

import requests

from ai_wdywfm.domain.errors import ProviderError
from ai_wdywfm.infrastructure.diagnostics import get_logger
from ai_wdywfm.infrastructure.providers.gemma4 import (
    apply_gemma4_profile,
    is_gemma4_model,
    normalize_gemma4_content,
)


class OpenAICompatibleClient:
    def __init__(
        self, *, provider: str, base_url: str, api_key: str, timeout: float,
        request_id: str = "diagnostic",
    ):
        self.request_id = request_id
        self.logger = get_logger()
        self.provider = provider
        self.base_url = _validated_url(provider, base_url)
        self.api_key = api_key.strip() or (
            os.environ.get("OPENROUTER_API_KEY", "") if provider == "OpenRouter" else ""
        )
        self.timeout = timeout

    def list_models(self) -> list[str]:
        response = self._request("GET", "/models")
        data = response.get("data")
        if not isinstance(data, list):
            raise ProviderError("Provider /models response has no model list.")
        models = sorted(
            item["id"] for item in data
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        )
        self.logger.info(
            "request=%s models.ok provider=%s count=%d",
            self.request_id, self.provider, len(models),
        )
        return models

    def complete(
        self,
        *,
        model: str,
        system_prompt: str,
        envelope: dict[str, Any],
        schema: dict[str, Any],
        image_url: str | None,
    ) -> dict[str, Any]:
        gemma4 = self.provider == "OpenRouter" and is_gemma4_model(model)
        content: list[dict[str, Any]] = [
            {"type": "text", "text": json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))}
        ]
        if image_url:
            content.append({"type": "image_url", "image_url": {"url": image_url}})
        effective_system_prompt = system_prompt
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": effective_system_prompt},
                {"role": "user", "content": content},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "prompt_suggestion_v1",
                    "strict": True,
                    "schema": schema,
                },
            },
            "stream": False,
            "temperature": 0.35,
        }
        if self.provider == "OpenRouter":
            payload["provider"] = {"require_parameters": not gemma4}
            payload["plugins"] = [{"id": "response-healing"}]
        if gemma4:
            effective_system_prompt = apply_gemma4_profile(payload, system_prompt)
            payload["messages"][0]["content"] = effective_system_prompt
            self.logger.info(
                "request=%s profile.gemma4 mode=fast_structured jailbreak=false reasoning_requested=false max_tokens=%s",
                self.request_id,
                payload["max_tokens"],
            )
        self.logger.info(
            "request=%s completion.start provider=%s model=%s vision=%s envelope_chars=%d timeout=%ss",
            self.request_id, self.provider, model, bool(image_url),
            len(content[0]["text"]), self.timeout,
        )
        response = self._request("POST", "/chat/completions", json_body=payload)
        try:
            choice = response["choices"][0]
            message = choice["message"]
            content_value = _message_content(message)
            if not isinstance(content_value, str):
                raise TypeError
            reasoning_present = bool(message.get("reasoning") or message.get("reasoning_details"))
            self.logger.info(
                "request=%s completion.shape finish_reason=%s content_chars=%d reasoning_present=%s",
                self.request_id, choice.get("finish_reason"), len(content_value), reasoning_present,
            )
            _log_usage(self.logger, self.request_id, response.get("usage"))
            if choice.get("finish_reason") == "length":
                self.logger.warning(
                    "request=%s completion.truncated finish_reason=length",
                    self.request_id,
                )
            normalized = normalize_gemma4_content(content_value) if gemma4 else content_value
            parsed = json.loads(_strip_outer_fence(normalized))
            self.logger.info(
                "request=%s completion.json_ok response_chars=%d",
                self.request_id, len(content_value),
            )
            return parsed
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderError("The LLM returned invalid JSON instead of a prompt suggestion.") from exc

    def _request(
        self, method: str, path: str, json_body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.provider == "OpenRouter":
            headers["X-OpenRouter-Title"] = "AI WDYWFM"
        started = time.perf_counter()
        self.logger.info(
            "request=%s http.start method=%s provider=%s path=%s connect_timeout=10s read_timeout=%ss",
            self.request_id, method, self.provider, path, self.timeout,
        )
        try:
            response = self._request_with_deadline(
                method, path, headers=headers, json_body=json_body
            )
            elapsed = time.perf_counter() - started
            self.logger.info(
                "request=%s http.response method=%s path=%s status=%d duration=%.3fs",
                self.request_id, method, path, response.status_code, elapsed,
            )
            response.raise_for_status()
            value = response.json()
        except requests.Timeout as exc:
            self.logger.warning(
                "request=%s http.timeout path=%s duration=%.3fs kind=%s",
                self.request_id, path, time.perf_counter() - started, type(exc).__name__,
            )
            raise ProviderError(f"{self.provider} timed out after {self.timeout:g} seconds.") from exc
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            details = _http_error_details(exc.response)
            self.logger.warning(
                "request=%s http.error path=%s status=%s duration=%.3fs details=%s",
                self.request_id, path, status, time.perf_counter() - started,
                details or "none",
            )
            suffix = f" {details}" if details else " Check model, key, and credits."
            raise ProviderError(f"{self.provider} returned HTTP {status}.{suffix}") from exc
        except (requests.RequestException, ValueError) as exc:
            self.logger.warning(
                "request=%s http.failure path=%s duration=%.3fs kind=%s",
                self.request_id, path, time.perf_counter() - started, type(exc).__name__,
            )
            raise ProviderError(f"Could not connect to {self.provider}.") from exc
        if not isinstance(value, dict):
            raise ProviderError(f"{self.provider} returned an unexpected response.")
        return value

    def _request_with_deadline(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
        json_body: dict[str, Any] | None,
    ):
        result: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

        def send() -> None:
            try:
                response = requests.request(
                    method,
                    f"{self.base_url}{path}",
                    headers=headers,
                    json=json_body,
                    timeout=(min(10, self.timeout), self.timeout),
                )
                result.put((True, response))
            except BaseException as exc:
                result.put((False, exc))

        worker = threading.Thread(
            target=send,
            name=f"wdywfm-http-{self.request_id}",
            daemon=True,
        )
        worker.start()
        try:
            succeeded, value = result.get(timeout=self.timeout)
        except queue.Empty as exc:
            self.logger.warning(
                "request=%s http.hard_timeout path=%s deadline=%ss",
                self.request_id, path, self.timeout,
            )
            raise ProviderError(
                f"{self.provider} exceeded the {self.timeout:g} second total deadline."
            ) from exc
        if not succeeded:
            raise value
        return value


def _validated_url(provider: str, value: str) -> str:
    value = (value or "").strip().rstrip("/")
    parsed = urlparse(value)
    if provider == "OpenRouter":
        if parsed.scheme != "https" or parsed.netloc != "openrouter.ai":
            raise ProviderError("OpenRouter URL must be https://openrouter.ai/api/v1.")
    else:
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ProviderError("LM Studio URL must point to the local machine.")
    return value


def _strip_outer_fence(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        first_newline = stripped.find("\n")
        if first_newline != -1:
            return stripped[first_newline + 1:-3].strip()
    return stripped


def _message_content(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    raise TypeError


def _http_error_details(response) -> str:
    if response is None:
        return ""
    try:
        payload = response.json()
        error = payload.get("error") if isinstance(payload, dict) else None
        message = error.get("message") if isinstance(error, dict) else None
        if not isinstance(message, str):
            return ""
        clean = " ".join(message.split())
        return clean[:400]
    except (ValueError, AttributeError):
        return ""


def _log_usage(logger, request_id: str, usage: Any) -> None:
    if not isinstance(usage, dict):
        return
    details = usage.get("completion_tokens_details")
    if not isinstance(details, dict):
        details = usage.get("output_tokens_details")
    reasoning_tokens = details.get("reasoning_tokens") if isinstance(details, dict) else None
    logger.info(
        "request=%s completion.usage prompt_tokens=%s completion_tokens=%s reasoning_tokens=%s total_tokens=%s",
        request_id,
        usage.get("prompt_tokens", "unknown"),
        usage.get("completion_tokens", usage.get("output_tokens", "unknown")),
        reasoning_tokens if reasoning_tokens is not None else "unknown",
        usage.get("total_tokens", "unknown"),
    )
