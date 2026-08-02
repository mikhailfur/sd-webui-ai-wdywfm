import unittest

from ai_wdywfm.infrastructure.providers.gemma4 import (
    apply_gemma4_profile,
    is_gemma4_model,
    normalize_gemma4_content,
)


class Gemma4ProfileTests(unittest.TestCase):
    def test_detects_whole_gemma4_family(self):
        self.assertTrue(is_gemma4_model("google/gemma-4-31b-it"))
        self.assertTrue(is_gemma4_model("google/gemma-4-12b-it:free"))
        self.assertFalse(is_gemma4_model("google/gemma-3-27b-it"))

    def test_applies_fast_structured_profile_without_jailbreak_or_reasoning(self):
        payload = {}
        system = apply_gemma4_profile(payload, "Schema instructions")
        self.assertEqual(system, "Schema instructions")
        self.assertEqual(payload["max_tokens"], 2048)
        self.assertNotIn("reasoning", payload)
        self.assertNotIn("stop", payload)

    def test_removes_reasoning_channel_before_final_json(self):
        value = '<|channel>thought private<channel|><|channel>final {"ok":true}'
        self.assertEqual(normalize_gemma4_content(value), '{"ok":true}')


if __name__ == "__main__":
    unittest.main()
