import time
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
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(payloads), 1)
        self.assertFalse(payloads[0]["provider"]["require_parameters"])
        self.assertNotIn("top_a", payloads[0])
        self.assertNotIn("reasoning", payloads[0])
        self.assertIn("response_format", payloads[0])


if __name__ == "__main__":
    unittest.main()
