import copy
import json
import unittest

from ai_wdywfm.domain.errors import ProviderError
from ai_wdywfm.infrastructure.providers.openai_compatible import OpenAICompatibleClient


def _tool_response(call_id, ids):
    return {
        "choices": [{
            "finish_reason": "tool_calls",
            "message": {
                "content": None,
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": "get_lora_details",
                        "arguments": json.dumps({"ids": ids}),
                    },
                }],
            },
        }],
    }


def _final_response():
    return {
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": '{"ok":true}'},
        }],
    }


class LoraToolLoopTests(unittest.TestCase):
    def make_client(self):
        return OpenAICompatibleClient(
            provider="LM Studio",
            base_url="http://127.0.0.1:1234/v1",
            api_key="",
            timeout=2,
            request_id="tools-test",
        )

    def envelope(self):
        return {
            "installed_models": {
                "summary": {
                    "loras": [{
                        "id": "hero", "alias": "Hero",
                        "short_description": "character",
                    }],
                },
                "detailed_candidates": [{"id": "must-not-be-sent"}],
                "checkpoint_details": [{
                    "id": "checkpoint",
                    "alias": "Checkpoint",
                    "base_model": "Illustrious",
                    "metadata_status": "fresh",
                    "description": "must-not-be-sent",
                    "sample_prompts": ["must-not-be-sent"],
                    "activation_words": ["must-not-be-sent"],
                }],
            },
        }

    def test_first_request_is_compact_and_unknown_tool_id_is_rejected(self):
        client = self.make_client()
        responses = [_tool_response("call-1", ["hero", "invented"]), _final_response()]
        payloads = []

        def fake_request(method, path, json_body=None):
            payloads.append(copy.deepcopy(json_body))
            return responses.pop(0)

        client._request = fake_request
        result = client.complete(
            model="local",
            system_prompt="Return JSON.",
            envelope=self.envelope(),
            schema={"type": "object"},
            image_url=None,
            lora_details={"hero": {"id": "hero", "activation_words": ["hero trigger"]}},
            fallback_lora_ids=["hero"],
        )
        self.assertEqual(result, {"ok": True})
        first_envelope = json.loads(payloads[0]["messages"][1]["content"][0]["text"])
        self.assertNotIn("detailed_candidates", first_envelope["installed_models"])
        self.assertEqual(
            set(first_envelope["installed_models"]["summary"]["loras"][0]),
            {"id", "alias", "short_description"},
        )
        self.assertEqual(
            first_envelope["installed_models"]["checkpoint_details"],
            [{
                "id": "checkpoint",
                "alias": "Checkpoint",
                "base_model": "Illustrious",
                "metadata_status": "fresh",
            }],
        )
        tool_result = json.loads(payloads[1]["messages"][-1]["content"])
        self.assertEqual(tool_result["rejected_ids"], ["invented"])
        self.assertEqual([item["id"] for item in tool_result["loras"]], ["hero"])

    def test_tool_rounds_are_bounded_then_forced_to_final_json(self):
        client = self.make_client()
        responses = [
            _tool_response("one", ["hero"]),
            _tool_response("two", ["hero"]),
            _tool_response("three", ["hero"]),
            _final_response(),
        ]
        payloads = []

        def fake_request(method, path, json_body=None):
            payloads.append(copy.deepcopy(json_body))
            return responses.pop(0)

        client._request = fake_request
        result = client.complete(
            model="local", system_prompt="Return JSON.", envelope=self.envelope(),
            schema={"type": "object"}, image_url=None,
            lora_details={"hero": {"id": "hero"}},
            max_tool_rounds=2,
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(payloads), 4)
        self.assertNotIn("tools", payloads[-1])

    def test_unsupported_tools_fall_back_to_bounded_static_details(self):
        client = self.make_client()
        payloads = []

        def fake_request(method, path, json_body=None):
            payloads.append(copy.deepcopy(json_body))
            if len(payloads) == 1:
                raise ProviderError("tools unsupported", category="no_structured_output")
            return _final_response()

        client._request = fake_request
        result = client.complete(
            model="local", system_prompt="Return JSON.", envelope=self.envelope(),
            schema={"type": "object"}, image_url=None,
            lora_details={"hero": {"id": "hero", "description": "full"}},
            fallback_lora_ids=["hero"],
        )
        self.assertEqual(result, {"ok": True})
        fallback_envelope = json.loads(payloads[1]["messages"][1]["content"][0]["text"])
        self.assertEqual(
            fallback_envelope["installed_models"]["detailed_candidates"][0]["id"],
            "hero",
        )
        self.assertNotIn("tools", payloads[1])


if __name__ == "__main__":
    unittest.main()
