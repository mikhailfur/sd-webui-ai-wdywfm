import unittest

from ai_wdywfm.application.apply_prompts import apply_prompt_fields
from ai_wdywfm.domain.errors import ValidationError


class ApplyPromptFieldsTests(unittest.TestCase):
    def test_replace_changes_exactly_two_returned_fields(self):
        before = {
            "prompt": "old",
            "negative_prompt": "old negative",
            "cfg": 7,
            "steps": 20,
            "width": 512,
        }
        state = {"valid": True, "prompt": "new", "negative_prompt": "new negative"}
        prompt, negative = apply_prompt_fields(
            state, before["prompt"], before["negative_prompt"], "Replace"
        )
        after = {**before, "prompt": prompt, "negative_prompt": negative}
        changed = {key for key in before if before[key] != after[key]}
        self.assertEqual(changed, {"prompt", "negative_prompt"})

    def test_append_is_explicit_for_both_prompts(self):
        state = {"valid": True, "prompt": "rain", "negative_prompt": "blur"}
        self.assertEqual(
            apply_prompt_fields(state, "city", "text", "Append"),
            ("city, rain", "text, blur"),
        )

    def test_unvalidated_state_cannot_apply(self):
        with self.assertRaises(ValidationError):
            apply_prompt_fields({}, "old", "old negative", "Replace")


if __name__ == "__main__":
    unittest.main()
