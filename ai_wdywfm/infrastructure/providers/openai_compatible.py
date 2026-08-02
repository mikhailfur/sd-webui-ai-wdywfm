from __future__ import annotations

import copy
import json
import os
import queue
import threading
import time
from typing import Any, Callable
from urllib.parse import urlparse

import requests

from ai_wdywfm.domain.errors import ProviderError
from ai_wdywfm.infrastructure.diagnostics import (
    category_logger,
    envelope_debug_summary,
)
from ai_wdywfm.infrastructure.providers.gemma4 import (
    apply_gemma4_profile,
    is_gemma4_model,
    normalize_gemma4_content,
)


class OpenAICompatibleClient:
    def __init__(
        self, *, provider: str, base_url: str, api_key: str, timeout: float,
        request_id: str = "diagnostic",
        cancel_event: threading.Event | None = None,
    ):
        self.request_id = request_id
        self.logger = category_logger("provider.http")
        self.provider = provider
        self.base_url = _validated_url(provider, base_url)
        self.api_key = api_key.strip() or (
            os.environ.get("OPENROUTER_API_KEY", "") if provider == "OpenRouter" else ""
        )
        self.timeout = timeout
        self.cancel_event = cancel_event
        self._deadline: float | None = None

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
        thinking_budget: int = 0,
        ttl: int | None = None,
        lora_details: dict[str, dict[str, Any]] | None = None,
        fallback_lora_ids: list[str] | None = None,
        max_tool_rounds: int = 2,
        max_tool_ids: int = 8,
        schema_name: str = "prompt_suggestion_v1",
        web_search: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        max_search_calls: int = 1,
    ) -> dict[str, Any]:
        gemma4 = self.provider == "OpenRouter" and is_gemma4_model(model)
        self._deadline = time.monotonic() + self.timeout
        tool_logger = category_logger("tools")
        http_logger = category_logger("provider.http")
        clean_envelope = copy.deepcopy(envelope)
        installed = clean_envelope.get("installed_models")
        if isinstance(installed, dict):
            installed.pop("detailed_candidates", None)
            checkpoint_details = installed.get("checkpoint_details")
            if isinstance(checkpoint_details, list):
                # Checkpoint descriptions and sample prompts can be many
                # kilobytes. The first pass only needs identity/family data;
                # full LoRA cards remain available through the bounded tool.
                installed["checkpoint_details"] = [
                    {
                        key: item[key]
                        for key in ("id", "alias", "base_model", "metadata_status")
                        if key in item
                    }
                    for item in checkpoint_details
                    if isinstance(item, dict)
                ]
        content: list[dict[str, Any]] = [
            {"type": "text", "text": json.dumps(clean_envelope, ensure_ascii=False, separators=(",", ":"))}
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
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
            "stream": False,
            "temperature": 0.35,
        }
        if self.provider == "OpenRouter":
            payload["provider"] = {
                "require_parameters": True,
                "allow_fallbacks": True,
                "sort": "throughput",
            }
            payload["plugins"] = [{"id": "response-healing"}]
        elif ttl is not None:
            # LM Studio JIT-load/idle-TTL extension field: unloads the model
            # from GPU memory this many seconds after the last request, so it
            # does not keep competing with Stable Diffusion for VRAM.
            payload["ttl"] = ttl
        tools_enabled = bool(lora_details or web_search) and not gemma4
        if tools_enabled:
            payload["tools"] = []
            if lora_details:
                payload["tools"].append(_lora_details_tool(max_tool_ids))
            if web_search is not None:
                payload["tools"].append(_web_search_tool())
            payload["tool_choice"] = "auto"
        if gemma4:
            effective_system_prompt = apply_gemma4_profile(payload, system_prompt)
            payload["messages"][0]["content"] = effective_system_prompt
        # Gemma 4 repeatedly exhausted the combined allowance in hidden
        # reasoning and returned a truncated schema. Keep its fast profile
        # non-reasoning; the setting still applies to other OpenRouter models.
        _apply_thinking_budget(
            payload, self.provider, 0 if gemma4 else thinking_budget,
        )
        if gemma4:
            self.logger.info(
                "request=%s profile.gemma4 mode=fast_structured jailbreak=false reasoning_requested=%s max_tokens=%s",
                self.request_id,
                bool(payload.get("reasoning")),
                payload["max_tokens"],
            )
        if bool(lora_details or web_search) and gemma4:
            tool_logger.info(
                "request=%s tool.fallback reason=profile_without_tools",
                self.request_id,
            )
            payload = _compatibility_fallback(
                payload=payload, envelope=clean_envelope,
                lora_details=lora_details or {},
                fallback_lora_ids=fallback_lora_ids or [],
                maximum_ids=max_tool_ids, web_search=web_search,
                deadline=self._deadline,
            )
        http_logger.info(
            "request=%s completion.start provider=%s model=%s vision=%s envelope_chars=%d timeout=%ss ttl=%s thinking_budget=%s",
            self.request_id, self.provider, model, bool(image_url),
            len(content[0]["text"]), self.timeout, payload.get("ttl", "n/a"),
            max(0, int(thinking_budget or 0)),
        )
        http_logger.debug(
            "request=%s envelope.models value=%s",
            self.request_id, envelope_debug_summary(clean_envelope),
        )
        try:
            try:
                response = self._request("POST", "/chat/completions", json_body=payload)
            except ProviderError as exc:
                if tools_enabled and (
                    exc.error_category == "no_structured_output" or "HTTP 400" in str(exc)
                ):
                    tool_logger.warning(
                        "request=%s tool.fallback reason=provider_unsupported",
                        self.request_id,
                    )
                    payload = _compatibility_fallback(
                        payload=payload, envelope=clean_envelope,
                        lora_details=lora_details or {},
                        fallback_lora_ids=fallback_lora_ids or [],
                        maximum_ids=max_tool_ids, web_search=web_search,
                        deadline=self._deadline,
                    )
                    response = self._request("POST", "/chat/completions", json_body=payload)
                    tools_enabled = False
                else:
                    raise

            tool_rounds = 0
            accepted_total: set[str] = set()
            search_calls = 0
            while tools_enabled:
                try:
                    choice, message = _choice_message(response)
                except (KeyError, IndexError, TypeError):
                    break
                tool_calls = message.get("tool_calls")
                if not isinstance(tool_calls, list) or not tool_calls:
                    break
                if tool_rounds >= max(0, max_tool_rounds):
                    tool_logger.warning(
                        "request=%s tool.limit rounds=%d accepted_ids=%d",
                        self.request_id, tool_rounds, len(accepted_total),
                    )
                    payload.pop("tools", None)
                    payload.pop("tool_choice", None)
                    payload["messages"].append({
                        "role": "system",
                        "content": "Tool limit reached. Return the final JSON object now.",
                    })
                    response = self._request("POST", "/chat/completions", json_body=payload)
                    tools_enabled = False
                    break
                tool_rounds += 1
                assistant_message = {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": tool_calls,
                }
                for reasoning_field in ("reasoning", "reasoning_details"):
                    if reasoning_field in message:
                        assistant_message[reasoning_field] = message[reasoning_field]
                payload["messages"].append(assistant_message)
                round_ids = 0
                rejected_ids = 0
                for call in tool_calls:
                    call_id, function_name, arguments = _parse_tool_call(call)
                    if function_name == "get_lora_details":
                        requested = arguments.get("ids")
                        requested = requested if isinstance(requested, list) else []
                        requested = list(dict.fromkeys(
                            item for item in requested if isinstance(item, str)
                        ))
                        remaining = max(0, max_tool_ids - len(accepted_total))
                        accepted = [
                            item_id for item_id in requested
                            if item_id in (lora_details or {}) and item_id not in accepted_total
                        ][:remaining]
                        rejected = [
                            item_id for item_id in requested
                            if item_id not in (lora_details or {})
                        ]
                        accepted_total.update(accepted)
                        round_ids += len(accepted)
                        rejected_ids += len(rejected)
                        result = {
                            "loras": [(lora_details or {})[item_id] for item_id in accepted],
                            "rejected_ids": rejected,
                            "remaining_id_budget": max(0, max_tool_ids - len(accepted_total)),
                        }
                    elif function_name == "web_search":
                        if web_search is None:
                            result = {"results": [], "error": "web_search is disabled"}
                        elif search_calls >= max(0, max_search_calls):
                            result = {"results": [], "error": "web_search call limit reached"}
                        else:
                            search_calls += 1
                            try:
                                result = _run_tool_with_deadline(
                                    web_search, arguments, self._deadline,
                                )
                            except Exception as exc:
                                tool_logger.warning(
                                    "request=%s search.failed kind=%s",
                                    self.request_id, type(exc).__name__,
                                )
                                result = {"results": [], "error": "search provider unavailable"}
                    else:
                        result = {"error": "unknown tool"}
                    payload["messages"].append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                    })
                tool_logger.info(
                    "request=%s tool.round round=%d calls=%d accepted_ids=%d rejected_ids=%d total_ids=%d search_calls=%d",
                    self.request_id, tool_rounds, len(tool_calls), round_ids,
                    rejected_ids, len(accepted_total), search_calls,
                )
                response = self._request("POST", "/chat/completions", json_body=payload)
            return self._parse_completion(response, gemma4)
        finally:
            self._deadline = None

    def _parse_completion(self, response: dict[str, Any], gemma4: bool) -> dict[str, Any]:
        try:
            choice, message = _choice_message(response)
            content_value = _message_content(message)
            finish_reason = choice.get("finish_reason")
            reasoning_present = bool(message.get("reasoning") or message.get("reasoning_details"))
            self.logger.info(
                "request=%s completion.shape finish_reason=%s content_chars=%d reasoning_present=%s",
                self.request_id, finish_reason, len(content_value), reasoning_present,
            )
            _log_usage(self.logger, self.request_id, response.get("usage"))
            if finish_reason == "length":
                self.logger.warning(
                    "request=%s completion.truncated finish_reason=length",
                    self.request_id,
                )
                raise ProviderError(
                    "The LLM reached its output limit before completing the response. "
                    "Reduce the thinking budget or choose a faster structured-output model.",
                    category="invalid_response",
                )
            if finish_reason == "error":
                details, category = _completion_error(response, choice)
                self.logger.warning(
                    "request=%s completion.provider_error error_category=%s details=%s",
                    self.request_id, category, details,
                )
                raise ProviderError(
                    f"OpenRouter provider failed during generation: {details}",
                    category=category,
                )
            if finish_reason not in {None, "stop"}:
                raise ProviderError(
                    f"The LLM stopped before completing the response ({finish_reason}).",
                    category="invalid_response",
                )
            normalized = normalize_gemma4_content(content_value) if gemma4 else content_value
            parsed = json.loads(_strip_outer_fence(normalized))
            self.logger.info(
                "request=%s completion.json_ok response_chars=%d",
                self.request_id, len(content_value),
            )
            return parsed
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderError(
                "The LLM returned invalid JSON instead of a prompt suggestion.",
                category="invalid_response",
            ) from exc

    def _request(
        self, method: str, path: str, json_body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.provider == "OpenRouter":
            headers["X-OpenRouter-Title"] = "AI WDYWFM"
            headers["X-OpenRouter-Metadata"] = "enabled"
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
                "request=%s http.timeout path=%s duration=%.3fs kind=%s error_category=provider_unavailable",
                self.request_id, path, time.perf_counter() - started, type(exc).__name__,
            )
            raise ProviderError(
                f"{self.provider} timed out after {self.timeout:g} seconds.",
                category="provider_unavailable",
            ) from exc
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            details = _http_error_details(exc.response)
            category = _http_error_category(status, details)
            self.logger.warning(
                "request=%s http.error path=%s status=%s duration=%.3fs error_category=%s details=%s",
                self.request_id, path, status, time.perf_counter() - started,
                category, details or "none",
            )
            suffix = f" {details}" if details else " Check model, key, and credits."
            raise ProviderError(
                f"{self.provider} returned HTTP {status}.{suffix}",
                category=category,
            ) from exc
        except (requests.RequestException, ValueError) as exc:
            self.logger.warning(
                "request=%s http.failure path=%s duration=%.3fs kind=%s error_category=provider_unavailable",
                self.request_id, path, time.perf_counter() - started, type(exc).__name__,
            )
            raise ProviderError(
                f"Could not connect to {self.provider}.",
                category="provider_unavailable",
            ) from exc
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
        deadline_timeout = self.timeout
        if self._deadline is not None:
            deadline_timeout = max(0.001, self._deadline - time.monotonic())
        wait_deadline = time.monotonic() + deadline_timeout
        while True:
            if self.cancel_event is not None and self.cancel_event.is_set():
                self.logger.info(
                    "request=%s http.cancelled path=%s", self.request_id, path,
                )
                raise ProviderError("Request cancelled.", category="cancelled")
            remaining = wait_deadline - time.monotonic()
            if remaining <= 0:
                self.logger.warning(
                    "request=%s http.hard_timeout path=%s deadline=%ss error_category=provider_unavailable",
                    self.request_id, path, deadline_timeout,
                )
                raise ProviderError(
                    f"{self.provider} exceeded the {self.timeout:g} second total deadline.",
                    category="provider_unavailable",
                )
            try:
                succeeded, value = result.get(timeout=min(0.1, remaining))
                break
            except queue.Empty:
                continue
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


def _choice_message(response: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    choice = response["choices"][0]
    message = choice["message"]
    if not isinstance(choice, dict) or not isinstance(message, dict):
        raise TypeError
    return choice, message


def _lora_details_tool(maximum_ids: int) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "get_lora_details",
            "description": (
                "Get trusted local metadata for installed LoRA ids from the compact catalog. "
                "Call only for ids that may help satisfy the user's request."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "ids": {
                        "type": "array",
                        "maxItems": max(1, int(maximum_ids)),
                        "items": {"type": "string"},
                    }
                },
                "required": ["ids"],
            },
        },
    }


def _web_search_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search trusted character-reference sources when the user's subject is a named "
                "character or franchise. Returns canonical Fandom facts plus character-category "
                "and common visual tags from Danbooru, Rule34, or e621. Use results only to improve "
                "identity, appearance, outfit, species, and franchise accuracy."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "query": {"type": "string", "maxLength": 240},
                    "character": {"type": "string", "maxLength": 120},
                    "franchise": {"type": "string", "maxLength": 120},
                    "sources": {
                        "type": "array",
                        "maxItems": 4,
                        "items": {
                            "type": "string",
                            "enum": ["danbooru", "rule34", "e621", "wiki_fandom"],
                        },
                    },
                    "fandom_wiki": {
                        "type": "string",
                        "maxLength": 160,
                        "description": "Optional allowlisted host such as chainsaw-man.fandom.com",
                    },
                },
                "required": ["query", "character", "franchise", "sources", "fandom_wiki"],
            },
        },
    }


def _parse_tool_call(call: Any) -> tuple[str, str, dict[str, Any]]:
    if not isinstance(call, dict):
        return "invalid-tool-call", "", {}
    call_id = str(call.get("id") or "missing-tool-call-id")
    function = call.get("function")
    if not isinstance(function, dict):
        return call_id, "", {}
    name = str(function.get("name") or "")
    arguments = function.get("arguments")
    try:
        value = json.loads(arguments) if isinstance(arguments, str) else arguments
    except ValueError:
        value = {}
    return call_id, name, value if isinstance(value, dict) else {}


def _compatibility_fallback(
    *,
    payload: dict[str, Any],
    envelope: dict[str, Any],
    lora_details: dict[str, dict[str, Any]],
    fallback_lora_ids: list[str],
    maximum_ids: int,
    web_search: Callable[[dict[str, Any]], dict[str, Any]] | None,
    deadline: float | None,
) -> dict[str, Any]:
    fallback_envelope = copy.deepcopy(envelope)
    if web_search is not None:
        intent = fallback_envelope.get("intent")
        intent = intent if isinstance(intent, dict) else {}
        query = str(intent.get("text") or "")[:240]
        try:
            fallback_envelope["web_search_results"] = _run_tool_with_deadline(
                web_search,
                {
                    "query": query,
                    "character": "",
                    "franchise": "",
                    "sources": ["danbooru", "rule34", "e621", "wiki_fandom"],
                    "fandom_wiki": "",
                },
                deadline,
            )
        except Exception:
            fallback_envelope["web_search_results"] = {
                "results": [], "error": "search provider unavailable",
            }
    return _static_lora_fallback(
        payload, fallback_envelope, lora_details, fallback_lora_ids, maximum_ids,
    )


def _run_tool_with_deadline(
    handler: Callable[[dict[str, Any]], dict[str, Any]],
    arguments: dict[str, Any],
    deadline: float | None,
) -> dict[str, Any]:
    remaining = max(0.001, deadline - time.monotonic()) if deadline is not None else 30.0
    result: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def run() -> None:
        try:
            result.put((True, handler(arguments)))
        except BaseException as exc:
            result.put((False, exc))

    worker = threading.Thread(
        target=run,
        name="wdywfm-search-tool",
        daemon=True,
    )
    worker.start()
    try:
        succeeded, value = result.get(timeout=remaining)
    except queue.Empty as exc:
        raise ProviderError(
            "The web search tool exceeded the request deadline.",
            category="provider_unavailable",
        ) from exc
    if not succeeded:
        raise value
    if not isinstance(value, dict):
        raise TypeError("Tool result must be an object.")
    return value


def _static_lora_fallback(
    payload: dict[str, Any],
    envelope: dict[str, Any],
    details: dict[str, dict[str, Any]],
    fallback_ids: list[str],
    maximum_ids: int,
) -> dict[str, Any]:
    result = copy.deepcopy(payload)
    result.pop("tools", None)
    result.pop("tool_choice", None)
    fallback_envelope = copy.deepcopy(envelope)
    context = fallback_envelope.setdefault("installed_models", {})
    if isinstance(context, dict):
        context["detailed_candidates"] = [
            details[item_id] for item_id in fallback_ids[:maximum_ids] if item_id in details
        ]
    user_content = result["messages"][1]["content"]
    if isinstance(user_content, list) and user_content:
        user_content[0]["text"] = json.dumps(
            fallback_envelope, ensure_ascii=False, separators=(",", ":")
        )
    return result


def _apply_thinking_budget(
    payload: dict[str, Any], provider: str, thinking_budget: int,
) -> None:
    try:
        budget = max(0, int(thinking_budget))
    except (TypeError, ValueError):
        budget = 0
    if budget == 0:
        return

    # Reasoning tokens share the completion allowance. Reserve enough room for
    # the schema-constrained prompt after the requested thinking budget.
    payload["max_tokens"] = max(int(payload.get("max_tokens") or 0), budget + 2048)
    if provider == "OpenRouter":
        payload["reasoning"] = {"max_tokens": budget, "exclude": True}
    else:
        # LM Studio 0.4.8+ OpenAI-compatible /v1/chat/completions extension.
        payload["reasoning_tokens"] = budget


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
        metadata = error.get("metadata") if isinstance(error, dict) else None
        error_type = metadata.get("error_type") if isinstance(metadata, dict) else None
        if isinstance(error_type, str) and error_type:
            clean = f"{clean} [{error_type}]"
        return clean[:400]
    except (ValueError, AttributeError):
        return ""


def _http_error_category(status: Any, details: str) -> str:
    try:
        code = int(status)
    except (TypeError, ValueError):
        return "provider_unavailable"
    if code in {401, 402, 403}:
        return "auth_credits"
    text = details.casefold()
    if code == 400 and any(
        marker in text for marker in ("tool", "function", "structured", "response_format", "json_schema")
    ):
        return "no_structured_output"
    if code == 400 and any(marker in text for marker in ("image", "vision", "modality")):
        return "no_vision"
    return "provider_unavailable"


def _completion_error(
    response: dict[str, Any], choice: dict[str, Any],
) -> tuple[str, str]:
    error = response.get("error")
    if not isinstance(error, dict):
        error = choice.get("error")
    if not isinstance(error, dict):
        return "upstream provider error", "provider_unavailable"
    message = error.get("message")
    message = " ".join(message.split())[:300] if isinstance(message, str) else "upstream provider error"
    metadata = error.get("metadata")
    error_type = metadata.get("error_type") if isinstance(metadata, dict) else None
    if isinstance(error_type, str) and error_type:
        message = f"{message} [{error_type}]"
    if error_type in {"authentication", "permission_denied", "payment_required"}:
        category = "auth_credits"
    elif error_type in {"invalid_request", "unsupported_parameter"}:
        category = "no_structured_output"
    else:
        category = "provider_unavailable"
    return message, category


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
