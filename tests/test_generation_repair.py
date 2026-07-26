import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

# The lightweight repository test interpreter does not include Pillow; this
# test never passes an image, so a minimal import stub is sufficient.
sys.modules.setdefault("PIL", SimpleNamespace(Image=SimpleNamespace()))

from ai_wdywfm.application.generate_suggestion import (
    _normalize_lora_weights,
    generate,
)
from ai_wdywfm.domain.errors import ValidationError


class FakeClient:
    responses = []
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        self.__class__.instances.append(self)

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.__class__.responses.pop(0)


class SingleRequestGenerationTests(unittest.TestCase):
    def setUp(self):
        FakeClient.responses = []
        FakeClient.instances = []

    @patch("ai_wdywfm.application.generate_suggestion.OpenAICompatibleClient", FakeClient)
    def test_invalid_response_fails_after_exactly_one_generation(self):
        FakeClient.responses = [
            {
                "schema_version": "1.0",
                "prompt": "cinematic portrait",
                "negative_prompt": "blurry",
                "models": {"checkpoint_id": None, "loras": []},
            },
        ]

        with self.assertRaisesRegex(ValidationError, "missing recommendations, summary, warnings"):
            generate(
                provider="OpenRouter",
                model="google/gemma-4-31b-it",
                base_url="https://openrouter.ai/api/v1",
                api_key="test-key",
                user_text="Make a portrait",
                dialect="auto",
                operation="Create",
                mode="txt2img",
                current_prompt="",
                current_negative="",
                image=None,
                cloud_image_consent=False,
                inventory={"constraints": {}, "lora_aliases": {}},
                timeout=120,
                image_max_side=1024,
                request_id="single-request-test",
            )

        self.assertEqual(len(FakeClient.instances), 1)
        self.assertEqual(len(FakeClient.instances[0].calls), 1)

    def test_normalizes_null_and_string_lora_weights_without_llm_retry(self):
        inventory = {
            "lora_aliases": {"local": "local-alias"},
            "lora_preferred_weights": {"local": 0.85},
        }
        for original, expected in (
            (None, 0.85), ("0.65", 0.65), (0, 0.85), ("null", 0.85), ("default", 0.85),
        ):
            with self.subTest(original=original):
                payload = {
                    "models": {"loras": [{"id": "local", "weight": original}]},
                    "warnings": [],
                }
                result = _normalize_lora_weights(payload, inventory)
                self.assertEqual(result["models"]["loras"][0]["weight"], expected)
                self.assertTrue(result["warnings"])


if __name__ == "__main__":
    unittest.main()
