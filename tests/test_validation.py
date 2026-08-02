import unittest

from ai_wdywfm.domain.errors import ValidationError
from ai_wdywfm.domain.validation import parse_suggestion, semantic_validate


def valid_payload():
    return {
        "schema_version": "1.0",
        "prompt": "portrait, <lora:ghost:1>",
        "negative_prompt": "blurry",
        "models": {
            "checkpoint_id": None,
            "loras": [
                {"id": "local", "weight": 0.8, "trigger_words": ["hero"], "reason": "style"}
            ],
        },
        "recommendations": {
            "sampler": "Euler",
            "scheduler": "Automatic",
            "sampling_steps": 24,
            "cfg_scale": 5,
            "width": 832,
            "height": 1216,
            "denoising_strength": 0.5,
        },
        "summary": "A portrait.",
        "warnings": [],
    }


class ValidationTests(unittest.TestCase):
    def test_exact_schema_rejects_extra_property(self):
        payload = valid_payload()
        payload["surprise"] = True
        with self.assertRaises(ValidationError):
            parse_suggestion(payload)

    def test_lora_weight_cannot_be_null(self):
        payload = valid_payload()
        payload["models"]["loras"][0]["weight"] = None
        with self.assertRaises(ValidationError):
            parse_suggestion(payload)

    def test_lora_weight_must_have_meaningful_nonzero_strength(self):
        for weight in (0, 0.01, -0.01):
            with self.subTest(weight=weight):
                payload = valid_payload()
                payload["models"]["loras"][0]["weight"] = weight
                with self.assertRaisesRegex(ValidationError, "meaningful non-zero"):
                    parse_suggestion(payload)

    def test_semantic_validation_removes_unknown_lora_and_normalizes_txt2img(self):
        payload = valid_payload()
        payload["prompt"] += ", <lora:hero-style:1.5>"
        suggestion = parse_suggestion(payload)
        result = semantic_validate(
            suggestion,
            mode="txt2img",
            checkpoints={"checkpoint"},
            lora_aliases={"local": "hero-style"},
            samplers={"Euler"},
            schedulers={"Automatic"},
            lora_triggers={"local": ("hero",)},
        )
        self.assertNotIn("ghost", result.prompt)
        self.assertIn("<lora:hero-style:0.8>", result.prompt)
        self.assertNotIn("<lora:hero-style:1.5>", result.prompt)
        self.assertEqual(result.prompt.count("<lora:"), 1)
        self.assertIn("hero", result.prompt)
        self.assertIsNone(result.recommendations.denoising_strength)
        self.assertGreaterEqual(len(result.warnings), 2)

    def test_repairs_hallucinated_lora_activation_word(self):
        payload = valid_payload()
        payload["models"]["loras"][0]["trigger_words"] = ["local"]
        suggestion = parse_suggestion(payload)
        result = semantic_validate(
            suggestion,
            mode="txt2img",
            checkpoints=set(),
            lora_aliases={"local": "hero-style"},
            samplers=set(),
            schedulers=set(),
            lora_triggers={"local": ("hero",)},
        )
        self.assertIn("hero", result.prompt)
        self.assertNotIn(", local,", result.prompt)
        self.assertIn("<lora:hero-style:0.8>", result.prompt)
        self.assertTrue(any("unverified activation words" in item for item in result.warnings))

    def test_uses_first_local_activation_word_when_model_omits_it(self):
        payload = valid_payload()
        payload["models"]["loras"][0]["trigger_words"] = []
        suggestion = parse_suggestion(payload)
        result = semantic_validate(
            suggestion,
            mode="txt2img",
            checkpoints=set(),
            lora_aliases={"local": "hero-style"},
            samplers=set(),
            schedulers=set(),
            lora_triggers={"local": ("canonical trigger", "optional detail")},
        )
        self.assertIn("canonical trigger", result.prompt)


if __name__ == "__main__":
    unittest.main()
