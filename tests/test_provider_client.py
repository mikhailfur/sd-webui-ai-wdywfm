import time
import threading
import unittest
from unittest.mock import patch

from ai_wdywfm.domain.errors import ProviderError
from ai_wdywfm.infrastructure.providers.openai_compatible import OpenAICompatibleClient


class ProviderClientTests(unittest.TestCase):
    def test_hard_deadline_bounds_total_wall_clock(self):
        client = OpenAICompatibleClient(
            provider="LM Studio",
            base_url="http://127.0.0.1:1234/v1",
            api_key="",
            timeout=0.05,
            request_id="deadline-test",
        )

        def slow_request(*args, **kwargs):
            time.sleep(0.25)
            raise AssertionError("background request should outlive the deadline")

        started = time.perf_counter()
        with patch("requests.request", side_effect=slow_request):
            with self.assertRaises(ProviderError):
                client._request("GET", "/models")
        self.assertLess(time.perf_counter() - started, 0.2)

    def test_gemma_content_channel_is_parsed_as_final_json(self):
        client = OpenAICompatibleClient(
            provider="OpenRouter",
            base_url="https://openrouter.ai/api/v1",
            api_key="test-only",
            timeout=1,
            request_id="gemma-test",
        )
        response = {
            "choices": [{
                "finish_reason": "stop",
                "message": {
                    "content": '<|channel>thought hidden<channel|><|channel>final {"ok":true}',
                    "reasoning": "hidden",
                },
            }]
        }
        captured = {}

        def fake_request(method, path, json_body=None):
            captured.update(json_body or {})
            return response

        client._request = fake_request
        result = client.complete(
            model="google/gemma-4-12b-it",
            system_prompt="Return JSON.",
            envelope={"test": True},
            schema={"type": "object"},
            image_url=None,
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(captured["temperature"], 0.35)
        self.assertEqual(captured["plugins"], [{"id": "response-healing"}])
        self.assertEqual(captured["messages"][0]["content"], "Return JSON.")
        self.assertNotIn("reasoning", captured)

    def test_gemma_uses_compatibility_routing_without_retry(self):
        client = OpenAICompatibleClient(
            provider="OpenRouter",
            base_url="https://openrouter.ai/api/v1",
            api_key="test-only",
            timeout=1,
            request_id="routing-test",
        )
        response = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": '{"ok":true}'},
            }]
        }
        payloads = []

        def fake_request(method, path, json_body=None):
            payloads.append(dict(json_body or {}))
            return response

        client._request = fake_request
        result = client.complete(
            model="google/gemma-4-31b-it",
            system_prompt="Return JSON.",
            envelope={"test": True},
            schema={"type": "object"},
            image_url=None,
            thinking_budget=2048,
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(payloads), 1)
        self.assertTrue(payloads[0]["provider"]["require_parameters"])
        self.assertTrue(payloads[0]["provider"]["allow_fallbacks"])
        self.assertEqual(payloads[0]["provider"]["sort"], "throughput")
        self.assertNotIn("top_a", payloads[0])
        self.assertNotIn("reasoning", payloads[0])
        self.assertEqual(payloads[0]["max_tokens"], 2048)
        self.assertIn("response_format", payloads[0])


    def test_lmstudio_ttl_is_forwarded_for_auto_unload(self):
        client = OpenAICompatibleClient(
            provider="LM Studio",
            base_url="http://127.0.0.1:1234/v1",
            api_key="",
            timeout=1,
            request_id="ttl-test",
        )
        response = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": '{"ok":true}'},
            }]
        }
        captured = {}

        def fake_request(method, path, json_body=None):
            captured.update(json_body or {})
            return response

        client._request = fake_request
        client.complete(
            model="local-model",
            system_prompt="Return JSON.",
            envelope={"test": True},
            schema={"type": "object"},
            image_url=None,
            ttl=20,
        )
        self.assertEqual(captured["ttl"], 20)

    def test_lmstudio_ttl_omitted_when_none(self):
        client = OpenAICompatibleClient(
            provider="LM Studio",
            base_url="http://127.0.0.1:1234/v1",
            api_key="",
            timeout=1,
            request_id="no-ttl-test",
        )
        response = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": '{"ok":true}'},
            }]
        }
        captured = {}

        def fake_request(method, path, json_body=None):
            captured.update(json_body or {})
            return response

        client._request = fake_request
        client.complete(
            model="local-model",
            system_prompt="Return JSON.",
            envelope={"test": True},
            schema={"type": "object"},
            image_url=None,
        )
        self.assertNotIn("ttl", captured)

    def test_openrouter_thinking_budget_uses_reasoning_max_tokens(self):
        client = OpenAICompatibleClient(
            provider="OpenRouter",
            base_url="https://openrouter.ai/api/v1",
            api_key="test-only",
            timeout=1,
            request_id="openrouter-thinking-test",
        )
        response = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": '{"ok":true}'},
            }]
        }
        captured = {}

        def fake_request(method, path, json_body=None):
            captured.update(json_body or {})
            return response

        client._request = fake_request
        client.complete(
            model="anthropic/test-model",
            system_prompt="Return JSON.",
            envelope={"test": True},
            schema={"type": "object"},
            image_url=None,
            thinking_budget=4096,
        )
        self.assertEqual(
            captured["reasoning"],
            {"max_tokens": 4096, "exclude": True},
        )
        self.assertEqual(captured["max_tokens"], 6144)

    def test_lmstudio_thinking_budget_uses_reasoning_tokens(self):
        client = OpenAICompatibleClient(
            provider="LM Studio",
            base_url="http://127.0.0.1:1234/v1",
            api_key="",
            timeout=1,
            request_id="lmstudio-thinking-test",
        )
        response = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": '{"ok":true}'},
            }]
        }
        captured = {}

        def fake_request(method, path, json_body=None):
            captured.update(json_body or {})
            return response

        client._request = fake_request
        client.complete(
            model="local-reasoning-model",
            system_prompt="Return JSON.",
            envelope={"test": True},
            schema={"type": "object"},
            image_url=None,
            thinking_budget=2048,
        )
        self.assertEqual(captured["reasoning_tokens"], 2048)
        self.assertNotIn("reasoning", captured)
        self.assertEqual(captured["max_tokens"], 4096)

    def test_zero_thinking_budget_uses_provider_default(self):
        client = OpenAICompatibleClient(
            provider="OpenRouter",
            base_url="https://openrouter.ai/api/v1",
            api_key="test-only",
            timeout=1,
            request_id="default-thinking-test",
        )
        response = {
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": '{"ok":true}'},
            }]
        }
        captured = {}

        def fake_request(method, path, json_body=None):
            captured.update(json_body or {})
            return response

        client._request = fake_request
        client.complete(
            model="test-model",
            system_prompt="Return JSON.",
            envelope={"test": True},
            schema={"type": "object"},
            image_url=None,
            thinking_budget=0,
        )
        self.assertNotIn("reasoning", captured)
        self.assertNotIn("reasoning_tokens", captured)

    def test_truncated_completion_is_rejected_before_schema_validation(self):
        client = OpenAICompatibleClient(
            provider="OpenRouter",
            base_url="https://openrouter.ai/api/v1",
            api_key="test-only",
            timeout=1,
            request_id="length-test",
        )
        client._request = lambda *args, **kwargs: {
            "choices": [{
                "finish_reason": "length",
                "message": {"content": '{"prompt":"incomplete"}'},
            }]
        }
        with self.assertRaisesRegex(ProviderError, "output limit"):
            client.complete(
                model="test-model",
                system_prompt="Return JSON.",
                envelope={"test": True},
                schema={"type": "object"},
                image_url=None,
            )

    def test_provider_finish_error_surfaces_typed_error(self):
        client = OpenAICompatibleClient(
            provider="OpenRouter",
            base_url="https://openrouter.ai/api/v1",
            api_key="test-only",
            timeout=1,
            request_id="provider-error-test",
        )
        client._request = lambda *args, **kwargs: {
            "error": {
                "message": "Provider overloaded",
                "metadata": {"error_type": "provider_overloaded"},
            },
            "choices": [{
                "finish_reason": "error",
                "message": {"content": "{}"},
            }],
        }
        with self.assertRaisesRegex(ProviderError, "provider_overloaded"):
            client.complete(
                model="test-model",
                system_prompt="Return JSON.",
                envelope={"test": True},
                schema={"type": "object"},
                image_url=None,
            )

    def test_cancel_event_stops_waiting_for_background_http(self):
        cancel_event = threading.Event()
        cancel_event.set()
        client = OpenAICompatibleClient(
            provider="OpenRouter",
            base_url="https://openrouter.ai/api/v1",
            api_key="test-only",
            timeout=10,
            request_id="cancel-test",
            cancel_event=cancel_event,
        )
        with patch("requests.request", side_effect=lambda *args, **kwargs: time.sleep(1)):
            started = time.perf_counter()
            with self.assertRaisesRegex(ProviderError, "cancelled"):
                client._request("POST", "/chat/completions", json_body={})
            self.assertLess(time.perf_counter() - started, 0.2)


if __name__ == "__main__":
    unittest.main()
