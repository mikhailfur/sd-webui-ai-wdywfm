from __future__ import annotations

import email.utils
import hashlib
import os
import random
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import quote, urlparse

import requests

from ai_wdywfm.infrastructure.diagnostics import category_logger


ALLOWED_HOSTS = {"civitai.com", "civitai.red"}
_SEMAPHORE = threading.BoundedSemaphore(3)


class CivitAIError(RuntimeError):
    pass


class CivitAINotFound(CivitAIError):
    pass


class CivitAIClient:
    def __init__(
        self,
        base_url: str = "https://civitai.com/api/v1",
        token: str = "",
        *,
        timeout: float = 15,
        retries: int = 2,
        request_id: str = "metadata",
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = validated_base_url(base_url)
        self.token = (
            os.environ.get("CIVITAI_API_TOKEN")
            or os.environ.get("CIVITAI_TOKEN")
            or token
            or ""
        ).strip()
        self.timeout = max(1.0, float(timeout))
        self.retries = max(0, min(int(retries), 5))
        self.request_id = request_id
        self.sleep = sleep
        self.logger = category_logger("civitai")

    def get_version_by_hash(self, sha256: str) -> dict[str, Any] | None:
        return self._get(f"/model-versions/by-hash/{quote(sha256, safe='')}")

    def get_version(self, version_id: int) -> dict[str, Any] | None:
        return self._get(f"/model-versions/{int(version_id)}")

    def get_model(self, model_id: int) -> dict[str, Any] | None:
        return self._get(f"/models/{int(model_id)}")

    def fetch_metadata(
        self, *, sha256: str | None = None, version_id: int | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        version = None
        if sha256:
            version = self.get_version_by_hash(sha256)
        if version is None and version_id:
            version = self.get_version(version_id)
        model_id = version.get("modelId") if isinstance(version, dict) else None
        model = self.get_model(model_id) if type(model_id) is int and model_id > 0 else None
        return version, model

    def search_loras(
        self,
        query: str,
        *,
        sort: str = "Most Downloaded",
        base_model: str = "",
        nsfw: str = "None",
        page: int = 1,
        limit: int = 12,
    ) -> dict[str, Any]:
        clean_query = " ".join((query or "").split())[:300]
        params: dict[str, Any] = {
            "query": clean_query,
            "types": "LORA",
            "sort": sort,
            "nsfw": nsfw,
            "page": max(1, int(page)),
            "limit": max(1, min(int(limit), 100)),
        }
        if base_model.strip():
            params["baseModels"] = base_model.strip()[:100]
        category_logger("civitai").info(
            "request=%s recommender.search query_hash=%s query_chars=%d page=%d limit=%d nsfw=%s",
            self.request_id,
            hashlib.sha256(clean_query.encode("utf-8")).hexdigest()[:12],
            len(clean_query), params["page"], params["limit"], nsfw,
        )
        value = self._get("/models", params=params)
        return value or {"items": [], "metadata": {}}

    def _get(
        self, path: str, *, params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        headers = {"Accept": "application/json", "User-Agent": "ai-wdywfm/phase-a"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        for attempt in range(self.retries + 1):
            started = time.perf_counter()
            response = None
            try:
                with _SEMAPHORE:
                    response = requests.get(
                        f"{self.base_url}{path}", headers=headers,
                        params=params,
                        timeout=(min(5.0, self.timeout), self.timeout),
                    )
                status = response.status_code
                self.logger.info(
                    "request=%s civitai.response path=%s status=%d duration=%.3fs attempt=%d",
                    self.request_id, path, status, time.perf_counter() - started, attempt + 1,
                )
                if status == 404:
                    self.logger.info(
                        "request=%s civitai.not_found path=%s error_category=metadata_not_found",
                        self.request_id, path,
                    )
                    return None
                if status == 429 or 500 <= status <= 599:
                    if attempt < self.retries:
                        self.sleep(_retry_delay(response, attempt))
                        continue
                response.raise_for_status()
                value = response.json()
                if not _valid_response(value):
                    raise CivitAIError("CivitAI returned an unexpected JSON shape.")
                return value
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt < self.retries:
                    self.sleep(_retry_delay(response, attempt))
                    continue
                raise CivitAIError("CivitAI is unavailable; local metadata will be used.") from exc
            except requests.HTTPError as exc:
                raise CivitAIError(f"CivitAI returned HTTP {exc.response.status_code}.") from exc
            except requests.RequestException as exc:
                if attempt < self.retries:
                    self.sleep(_retry_delay(response, attempt))
                    continue
                raise CivitAIError("CivitAI transport failed; local metadata will be used.") from exc
            except ValueError as exc:
                raise CivitAIError("CivitAI returned invalid JSON.") from exc
        return None


def validated_base_url(value: str) -> str:
    candidate = (value or "").strip().rstrip("/")
    parsed = urlparse(candidate)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_HOSTS
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/api/v1"
    ):
        raise CivitAIError(
            "CivitAI URL must be https://civitai.com/api/v1 or https://civitai.red/api/v1."
        )
    return candidate


def _valid_response(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    # Schema-lite: reject generic HTML/error JSON while allowing both model and version shapes.
    return any(key in value for key in ("id", "modelId", "name", "files", "description", "items"))


def _retry_delay(response, attempt: int) -> float:
    if response is not None:
        raw = response.headers.get("Retry-After")
        if raw:
            try:
                return min(max(float(raw), 0.0), 60.0)
            except ValueError:
                try:
                    parsed = email.utils.parsedate_to_datetime(raw)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    return min(max((parsed - datetime.now(timezone.utc)).total_seconds(), 0.0), 60.0)
                except (TypeError, ValueError, OverflowError):
                    pass
    return min(0.5 * (2 ** attempt) + random.uniform(0.0, 0.25), 8.0)
