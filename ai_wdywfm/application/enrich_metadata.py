from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from ai_wdywfm.domain.models import ModelMetadata
from ai_wdywfm.infrastructure.civitai.client import CivitAIClient, CivitAIError
from ai_wdywfm.infrastructure.civitai.normalizer import merge_metadata, normalize_metadata
from ai_wdywfm.infrastructure.diagnostics import category_logger
from ai_wdywfm.infrastructure.hashing import file_fingerprint, sha256_file
from ai_wdywfm.infrastructure.storage.sqlite_cache import SQLiteMetadataCache


class MetadataEnricher:
    def __init__(
        self,
        *,
        cache: SQLiteMetadataCache,
        client: CivitAIClient | None,
        request_id: str = "metadata",
        cancel: threading.Event | None = None,
        workers: int = 2,
    ) -> None:
        self.cache = cache
        self.client = client
        self.request_id = request_id
        self.cancel = cancel or threading.Event()
        self.workers = max(1, min(int(workers), 3))
        self.logger = category_logger("inventory")

    def enrich_many(
        self, items: Iterable[tuple[ModelMetadata, str | Path]],
    ) -> dict[str, ModelMetadata]:
        selected = list(items)
        if not selected:
            return {}
        results: dict[str, ModelMetadata] = {}
        with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="wdywfm-metadata") as pool:
            futures = {pool.submit(self.enrich, metadata, path): metadata.local_id for metadata, path in selected}
            for future in as_completed(futures):
                local_id = futures[future]
                try:
                    results[local_id] = future.result()
                except Exception as exc:
                    self.logger.warning(
                        "request=%s metadata.item_failed id=%s kind=%s",
                        self.request_id, local_id, type(exc).__name__,
                    )
                    original = next(item for item, _ in selected if item.local_id == local_id)
                    results[local_id] = replace(original, status="offline")
        return results

    def enrich(self, local: ModelMetadata, path: str | Path) -> ModelMetadata:
        fingerprint, size, mtime_ns = file_fingerprint(path, local.kind)
        self.cache.upsert_local_model(
            local, fingerprint=fingerprint, size=size, mtime_ns=mtime_ns,
        )
        cached = self.cache.get_metadata(local.local_id)
        if cached is not None and not cached.stale:
            return replace(merge_metadata(cached.metadata, local), status="cached")

        stale = merge_metadata(cached.metadata, local) if cached is not None else local
        if self.client is None or self.cancel.is_set():
            return replace(stale, status="stale" if cached else "local")

        sha256 = local.sha256 or self.cache.stored_sha256(local.local_id, fingerprint)
        if not sha256:
            sha256 = sha256_file(path, self.cancel)
            self.cache.store_sha256(local.local_id, fingerprint, sha256)
        lookup_key = f"sha256:{sha256}" if sha256 else f"version:{local.civitai_version_id}"
        if self.cache.is_negative_cached(lookup_key):
            return replace(stale, sha256=sha256, status="local" if cached is None else "stale")

        try:
            version, model = self.client.fetch_metadata(
                sha256=sha256, version_id=local.civitai_version_id,
            )
        except CivitAIError:
            return replace(stale, sha256=sha256, status="offline")
        if version is None:
            self.cache.mark_not_found(lookup_key)
            return replace(stale, sha256=sha256, status="local" if cached is None else "stale")

        remote = normalize_metadata(
            local_id=local.local_id,
            kind=local.kind,
            display_name=local.display_name,
            version_response=version,
            model_response=model,
        )
        merged = replace(merge_metadata(remote, replace(local, sha256=sha256)), status="cached")
        self.cache.put_metadata(merged)
        return merged
