import unittest
from unittest.mock import patch

from ai_wdywfm.infrastructure.forge_neo.inventory import (
    _activation_words,
    _preferred_weight,
    _read_user_metadata_file,
)


class InventoryMetadataTests(unittest.TestCase):
    def test_activation_words_are_bounded_and_deduplicated(self):
        words = _activation_words("hero_tag, hero tag, style trigger\nsecond trigger")
        self.assertEqual(words, ["hero_tag", "style trigger", "second trigger"])

    def test_preferred_weight_accepts_bounded_numeric_metadata(self):
        self.assertEqual(_preferred_weight("0.85"), 0.85)
        self.assertIsNone(_preferred_weight(0))
        self.assertIsNone(_preferred_weight("strong"))

    def test_sidecar_metadata_is_cached_and_invalidated_by_file_change(self):
        _read_user_metadata_file.cache_clear()
        target = "C:/models/style.json"
        with patch(
            "ai_wdywfm.infrastructure.forge_neo.inventory.Path.read_text",
            return_value='{"activation text":"first"}',
        ) as read_text:
            self.assertEqual(
                _read_user_metadata_file(target, 1, 27)["activation text"], "first"
            )
            before = _read_user_metadata_file.cache_info()
            self.assertEqual(
                _read_user_metadata_file(target, 1, 27)["activation text"], "first"
            )
            after = _read_user_metadata_file.cache_info()
            self.assertEqual(after.hits, before.hits + 1)
            self.assertEqual(read_text.call_count, 1)

        with patch(
            "ai_wdywfm.infrastructure.forge_neo.inventory.Path.read_text",
            return_value='{"activation text":"second value"}',
        ):
            self.assertEqual(
                _read_user_metadata_file(target, 2, 34)["activation text"], "second value"
            )


if __name__ == "__main__":
    unittest.main()
