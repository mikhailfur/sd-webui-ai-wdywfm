import json
import os
import struct
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from ai_wdywfm.application.enrich_metadata import MetadataEnricher
from ai_wdywfm.domain.models import ModelMetadata
from ai_wdywfm.infrastructure.civitai.client import (
    CivitAIClient,
    CivitAIError,
    validated_base_url,
)
from ai_wdywfm.infrastructure.civitai.normalizer import sanitize_html
from ai_wdywfm.infrastructure.civitai.sidecars import (
    _read_safetensors_metadata,
    read_safetensors_metadata,
    resolve_local_metadata,
)
from ai_wdywfm.infrastructure.hashing import sha256_file
from ai_wdywfm.infrastructure.storage.sqlite_cache import SQLiteMetadataCache


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "docs" / "LoRA json exmples"


class FixtureNormalizationTests(unittest.TestCase):
    def test_all_documented_fixture_pairs_normalize(self):
        expected = {
            "Yoru": (2054132, 2324610),
            "Reze": (2051871, 2322119),
            "Dot_Comics-mix s98": (1700213, 2230615),
        }
        for name, identity in expected.items():
            with self.subTest(name=name):
                metadata = resolve_local_metadata(
                    FIXTURES / f"{name}.safetensors",
                    local_id=f"lora:{name}", kind="lora", display_name=name,
                )
                self.assertEqual((metadata.civitai_model_id, metadata.civitai_version_id), identity)
                self.assertEqual(metadata.base_model, "Illustrious")
                self.assertTrue(metadata.sample_prompts)
                self.assertEqual(metadata.provenance["identity"], "sidecar")

    def test_activation_groups_are_preserved_and_deduplicated(self):
        metadata = resolve_local_metadata(
            FIXTURES / "Reze.safetensors",
            local_id="reze", kind="lora", display_name="Reze",
        )
        self.assertGreaterEqual(len(metadata.trigger_word_groups), 3)
        self.assertIn("grenade pin choker", metadata.trigger_words)
        self.assertEqual(len(metadata.trigger_words), len(set(word.casefold() for word in metadata.trigger_words)))

    def test_description_and_prompts_are_plain_text(self):
        metadata = resolve_local_metadata(
            FIXTURES / "Dot_Comics-mix s98.safetensors",
            local_id="dot", kind="lora", display_name="Dot",
        )
        self.assertTrue(metadata.description_text)
        self.assertNotIn("<", metadata.description_text)
        self.assertTrue(metadata.sample_prompts)
        self.assertNotIn("<script", sanitize_html("<p>safe</p><script>bad()</script>"))


class SafetensorsReaderTests(unittest.TestCase):
    def test_reads_only_bounded_header_metadata(self):
        _read_safetensors_metadata.cache_clear()
        header = json.dumps({"__metadata__": {"ss_base_model_version": "sdxl", "custom": "ok"}}).encode()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tiny.safetensors"
            path.write_bytes(struct.pack("<Q", len(header)) + header + b"tensor-payload")
            self.assertEqual(read_safetensors_metadata(path)["custom"], "ok")

    def test_rejects_oversized_header_without_reading_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.safetensors"
            path.write_bytes(struct.pack("<Q", 100_000_000) + b"{}")
            self.assertEqual(read_safetensors_metadata(path), {})


class SQLiteCacheTests(unittest.TestCase):
    def test_round_trip_provenance_negative_cache_and_fingerprint_invalidation(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = SQLiteMetadataCache(Path(folder) / "cache.sqlite3")
            metadata = ModelMetadata(
                local_id="lora:test", kind="lora", display_name="Test",
                description_text="cached", provenance={"description": "civitai_cache"},
            )
            cache.upsert_local_model(metadata, fingerprint="fp1", size=1, mtime_ns=1)
            cache.put_metadata(metadata)
            entry = cache.get_metadata("lora:test")
            self.assertIsNotNone(entry)
            self.assertEqual(entry.metadata.description_text, "cached")
            self.assertFalse(entry.stale)
            cache.mark_not_found("sha256:DEAD")
            self.assertTrue(cache.is_negative_cached("sha256:DEAD"))
            cache.upsert_local_model(metadata, fingerprint="fp2", size=2, mtime_ns=2)
            self.assertIsNone(cache.get_metadata("lora:test"))

    def test_corrupt_snapshot_recovers_as_cache_miss(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = SQLiteMetadataCache(Path(folder) / "cache.sqlite3")
            metadata = ModelMetadata(local_id="bad", kind="lora", display_name="Bad")
            cache.upsert_local_model(metadata, fingerprint="fp")
            with cache._connect() as db:
                db.execute(
                    "INSERT INTO metadata_snapshots VALUES (?, ?, ?, ?)",
                    ("bad", "not-json", time.time(), time.time() + 60),
                )
            self.assertIsNone(cache.get_metadata("bad"))


class _Response:
    def __init__(self, status, payload=None, headers=None):
        self.status_code = status
        self._payload = payload if payload is not None else {"id": 1}
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError("error")
            error.response = self
            raise error


class CivitAIClientTests(unittest.TestCase):
    def test_url_allowlist_is_exact(self):
        self.assertEqual(validated_base_url("https://civitai.red/api/v1/"), "https://civitai.red/api/v1")
        for value in (
            "http://civitai.com/api/v1", "https://evil.example/api/v1",
            "https://civitai.com.evil.example/api/v1", "https://civitai.com:444/api/v1",
        ):
            with self.subTest(value=value), self.assertRaises(CivitAIError):
                validated_base_url(value)

    def test_retries_429_and_honors_retry_after(self):
        sleep = Mock()
        responses = [_Response(429, headers={"Retry-After": "0"}), _Response(200, {"id": 9})]
        with patch("ai_wdywfm.infrastructure.civitai.client.requests.get", side_effect=responses) as get:
            value = CivitAIClient(retries=2, sleep=sleep).get_model(9)
        self.assertEqual(value["id"], 9)
        self.assertEqual(get.call_count, 2)
        sleep.assert_called_once_with(0.0)

    def test_does_not_retry_non_retryable_4xx(self):
        with patch("ai_wdywfm.infrastructure.civitai.client.requests.get", return_value=_Response(401)) as get:
            with self.assertRaises(CivitAIError):
                CivitAIClient(retries=3, sleep=Mock()).get_model(1)
        self.assertEqual(get.call_count, 1)

    def test_environment_token_has_priority(self):
        with patch.dict(os.environ, {"CIVITAI_API_TOKEN": "env-token"}), patch(
            "ai_wdywfm.infrastructure.civitai.client.requests.get", return_value=_Response(200)
        ) as get:
            CivitAIClient(token="argument-token").get_model(1)
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer env-token")


class EnrichmentTests(unittest.TestCase):
    def test_cache_first_skips_hash_and_network(self):
        with tempfile.TemporaryDirectory() as folder:
            model_path = Path(folder) / "model.safetensors"
            model_path.write_bytes(b"model")
            cache = SQLiteMetadataCache(Path(folder) / "cache.sqlite3")
            local = ModelMetadata(local_id="lora:x", kind="lora", display_name="X")
            from ai_wdywfm.infrastructure.hashing import file_fingerprint
            fingerprint, size, mtime_ns = file_fingerprint(model_path, "lora")
            cache.upsert_local_model(local, fingerprint=fingerprint, size=size, mtime_ns=mtime_ns)
            cached = ModelMetadata(
                local_id="lora:x", kind="lora", display_name="X", description_text="from cache",
            )
            cache.put_metadata(cached)
            client = Mock()
            result = MetadataEnricher(cache=cache, client=client).enrich(local, model_path)
            self.assertEqual(result.status, "cached")
            self.assertEqual(result.description_text, "from cache")
            client.fetch_metadata.assert_not_called()

    def test_streaming_sha256_is_stable(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "model.bin"
            path.write_bytes(b"abc")
            self.assertEqual(
                sha256_file(path),
                "BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD",
            )


class ForgeInventoryIntegrationTests(unittest.TestCase):
    def test_local_enrichment_updates_context_without_network(self):
        import sys
        import types
        from types import SimpleNamespace

        from ai_wdywfm.infrastructure.forge_neo.inventory import build_inventory

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            model_path = root / "hero.safetensors"
            model_path.write_bytes(b"not-a-real-header")
            model_path.with_suffix(".json").write_text(
                json.dumps({
                    "modelId": 10, "modelVersionId": 20,
                    "activation text": "hero trigger", "preferred weight": 0.8,
                }), encoding="utf-8",
            )
            model_path.with_suffix(".api_info.json").write_text(
                json.dumps({
                    "id": 20, "modelId": 10, "baseModel": "Illustrious",
                    "description": "<p>Local description</p>",
                    "images": [{"meta": {"prompt": "hero trigger, portrait"}}],
                }), encoding="utf-8",
            )

            class Network:
                filename = str(model_path)
                metadata = {}

                @staticmethod
                def get_alias():
                    return "hero-alias"

            modules = types.ModuleType("modules")
            modules.sd_models = SimpleNamespace(checkpoints_list={})
            modules.shared = SimpleNamespace(opts=SimpleNamespace(sd_model_checkpoint=""))
            modules.shared_items = SimpleNamespace(
                list_samplers=lambda: [SimpleNamespace(name="Euler")],
                list_schedulers=lambda: ["Automatic"],
            )
            networks = types.ModuleType("networks")
            networks.available_networks = {"hero": Network()}
            with patch.dict(sys.modules, {"modules": modules, "networks": networks}), patch(
                "ai_wdywfm.infrastructure.civitai.client.requests.get"
            ) as get:
                inventory = build_inventory(
                    80, "hero portrait", enrich_civitai=False,
                    cache_path=root / "cache.sqlite3",
                )

            get.assert_not_called()
            card = inventory["context"]["detailed_candidates"][0]
            self.assertEqual(card["id"], "hero")
            self.assertEqual(card["description"], "Local description")
            self.assertEqual(card["metadata_status"], "local")
            self.assertEqual(inventory["lora_triggers"]["hero"], ("hero trigger",))
            self.assertEqual(inventory["lora_preferred_weights"]["hero"], 0.8)


if __name__ == "__main__":
    unittest.main()
